"""
Capability 2: retrieval-augmented answers over support tickets and customer feedback.

Design note: the 6,120 tickets contain only 32 distinct messages and the 5,046 feedback entries only 13, so we index the DISTINCT
texts (TF-IDF, no embedding model or vector database needed, runs instantly on a laptop) and compute volumes, trends and
churn/CSAT context from the raw rows at question time. This also lets every answer be filtered by country, plan or time window.
If your own data later has thousands of distinct texts, swap TfidfVectorizer for sentence-transformers behind the same `search()`.
"""
from __future__ import annotations
import re
import joblib
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel
from src.llm.llm_client import get_client, LLMError
from src.utils.config import ROOT, REFERENCE_DATE
from src.utils.data_loader import load_table, master

INDEX_PATH = ROOT / "models" / "rag_index.joblib"
RAG_SYSTEM = ("You summarise customer voice (support tickets and feedback) for a business audience. Use ONLY the context provided. "
              "Group the findings into themes, quote volumes (n=...) and note churn / satisfaction context when given. Reference themes by "
              "their IDs like [T3]. If the context does not contain the answer, say so. 4-8 sentences or a short bullet list; no speculation.")


def _docs() -> pd.DataFrame:
    t = load_table("support_tickets").dropna(subset=["ticket_description"])
    f = load_table("customer_feedback").dropna(subset=["feedback_text"])
    td = (t.groupby("ticket_description").agg(category=("issue_category", lambda s: s.mode().iloc[0]), subcategory=("issue_subcategory", lambda s: s.mode().iloc[0]))
          .reset_index().rename(columns={"ticket_description": "text"}))
    td["source"] = "ticket"
    fd = f.groupby("feedback_text").agg(category=("sentiment_label", lambda s: s.mode().iloc[0])).reset_index().rename(columns={"feedback_text": "text"})
    fd["subcategory"], fd["source"] = "", "feedback"
    d = pd.concat([td, fd], ignore_index=True)
    d["doc_id"] = [("T" if s == "ticket" else "F") + str(i) for i, s in zip(d.groupby("source").cumcount() + 1, d.source)]
    d["index_text"] = d.category + " " + d.subcategory + " " + d.text
    return d


def build_index(save: bool = True) -> dict:
    d = _docs()
    vec = TfidfVectorizer(ngram_range=(1, 2), stop_words="english", sublinear_tf=True, min_df=1)
    idx = {"docs": d, "vectorizer": vec, "matrix": vec.fit_transform(d.index_text)}
    if save:
        INDEX_PATH.parent.mkdir(exist_ok=True); joblib.dump(idx, INDEX_PATH)
    return idx


_idx = None


def get_index() -> dict:
    global _idx
    if _idx is None:
        _idx = joblib.load(INDEX_PATH) if INDEX_PATH.exists() else build_index()
    return _idx


def search(query: str, k: int = 6, source: str | None = None, min_score: float = 0.04) -> pd.DataFrame:
    idx = get_index(); d = idx["docs"]
    sims = linear_kernel(idx["vectorizer"].transform([query]), idx["matrix"]).ravel()
    out = d.assign(score=sims)
    if source:
        out = out[out.source == source]
    return out[out.score >= min_score].sort_values("score", ascending=False).head(k).reset_index(drop=True)


# ------------------------------------------------------------------ question parsing (filters)
def parse_filters(question: str) -> dict:
    q = question.lower(); f = {}
    for c in master().country.dropna().unique():
        if c.lower() in q:
            f["country"] = c; break
    for p in ["basic", "standard", "premium"]:
        if re.search(rf"\b{p}\b", q):
            f["plan_name"] = p.title(); break
    m = re.search(r"last (\d+) (day|week|month)s?", q)
    if m:
        n, unit = int(m.group(1)), m.group(2); f["days"] = n * {"day": 1, "week": 7, "month": 30}[unit]
    elif "last quarter" in q or "last 3 months" in q:
        f["days"] = 90
    elif "last month" in q:
        f["days"] = 30
    elif "this year" in q or "2026" in q:
        f["days"] = (REFERENCE_DATE - pd.Timestamp("2026-01-01")).days
    return f


def _filtered(df: pd.DataFrame, date_col: str, flt: dict) -> pd.DataFrame:
    m = master()[["customer_id", "country", "plan_name", "churned"]]
    df = df.merge(m, on="customer_id", how="left")
    if "country" in flt:
        df = df[df.country == flt["country"]]
    if "plan_name" in flt:
        df = df[df.plan_name == flt["plan_name"]]
    if "days" in flt:
        df = df[df[date_col] > REFERENCE_DATE - pd.Timedelta(days=flt["days"])]
    return df


def theme_stats(hits: pd.DataFrame, flt: dict) -> pd.DataFrame:
    t = _filtered(load_table("support_tickets"), "ticket_date", flt); f = _filtered(load_table("customer_feedback"), "feedback_date", flt)
    base = master().churned.mean(); rows = []
    for r in hits.itertuples():
        if r.source == "ticket":
            s = t[t.ticket_description == r.text]; extra = f"avg CSAT {s.customer_satisfaction_score.mean():.2f}" if s.customer_satisfaction_score.notna().any() else "CSAT n/a"
        else:
            s = f[f.feedback_text == r.text]; extra = f"avg rating {s.rating.mean():.2f}" if len(s) else "no rows"
        rows.append({"doc_id": r.doc_id, "source": r.source, "category": r.category, "subcategory": r.subcategory, "text": r.text, "score": r.score,
                     "n": len(s), "churn_rate": s.churned.mean() if len(s) else np.nan, "extra": extra})
    out = pd.DataFrame(rows); out["baseline_churn"] = base
    return out


def ask(question: str, k: int = 6) -> dict:
    flt = parse_filters(question)
    src = "ticket" if re.search(r"ticket|complain|issue|support", question, re.I) else "feedback" if re.search(r"feedback|review|rating|say about|sentiment", question, re.I) else None
    hits = search(question, k=k, source=src)
    if hits.empty:
        hits = search("billing payment streaming app account", k=k, source=src, min_score=0.0)
        note = "No close match, showing the largest general themes instead. "
    else:
        note = ""
    stats = theme_stats(hits, flt)
    ctx = "\n".join(f"[{r.doc_id}] ({r.source}; {r.category}{' / ' + r.subcategory if r.subcategory else ''}; n={r.n}; churn among authors "
                    f"{r.churn_rate:.0%} vs {r.baseline_churn:.0%} overall; {r.extra}): \"{r.text}\"" for r in stats.itertuples() if r.n > 0)
    flt_txt = ", ".join(f"{k}={v}" for k, v in flt.items()) or "none"
    fallback = note + "Top themes (filters: " + flt_txt + "):\n" + "\n".join(
        f"- [{r.doc_id}] {r.category}{' / ' + r.subcategory if r.subcategory else ''}: n={r.n}, churn {r.churn_rate:.0%}, {r.extra}" for r in stats.itertuples() if r.n > 0)
    if not ctx:
        return {"answer": "No tickets or feedback match that question and filter combination.", "themes": stats, "filters": flt, "used_llm": False}
    try:
        ans = get_client().chat(f"Question: {question}\nFilters applied: {flt_txt}\n\nContext:\n{ctx}", system=RAG_SYSTEM, temperature=0.2, max_tokens=450)
        used = True
    except LLMError:
        ans, used = fallback, False
    return {"answer": ans, "themes": stats, "filters": flt, "used_llm": used}
