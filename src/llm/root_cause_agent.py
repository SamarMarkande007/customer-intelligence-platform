"""
Capability 5: root-cause analysis. The LLM never invents statistics. A deterministic investigator runs a fixed set of statistical
comparisons (group vs everyone else), flags what is significant, and the LLM only narrates those findings.
    "Why is churn higher in South Korea?"  ->  detect group -> compare churn, churn reasons, behaviour, mix, complaints -> narrate
"""
from __future__ import annotations
import re
import numpy as np
import pandas as pd
from scipy import stats
from src.llm.llm_client import get_client, LLMError
from src.utils.data_loader import master, load_table

DIMS = {"country": "country", "plan_name": "plan_name", "acquisition_channel": "acquisition_channel", "segment_name": "segment_name",
        "customer_segment": "customer_segment", "gender": "gender", "age_group": "age_group"}
METRICS = {"failed_payment_rate": ("failed-payment rate", "{:.1%}"), "support_ticket_count": ("support tickets per customer", "{:.2f}"),
           "avg_customer_satisfaction": ("support satisfaction", "{:.2f}"), "engagement_score": ("engagement score", "{:.1f}"),
           "days_since_last_activity": ("days since last viewing", "{:.1f}"), "customer_tenure_days": ("tenure in days", "{:.0f}"),
           "monthly_price": ("monthly price", "${:.2f}"), "sessions_90d": ("sessions in 90 days", "{:.2f}"), "age": ("age", "{:.1f}")}
RCA_SYSTEM = ("You are a churn analyst. Explain the root causes using ONLY the findings provided (they come from statistical tests). Distinguish "
              "'significant' from 'suggestive' findings, never state causation as fact, and say plainly if nothing significant explains the gap. "
              "Structure: 1 sentence headline, then 3-5 bullets of the strongest evidence with numbers, then 2 suggested actions. Max 170 words.")


def detect_group(question: str):
    m = master(); q = question.lower()
    for col in ["country", "plan_name", "acquisition_channel", "segment_name", "customer_segment", "age_group"]:
        for v in sorted(m[col].dropna().unique(), key=len, reverse=True):
            if str(v).lower() in q:
                return col, v
    return None, None


def _ztest(x1, n1, x2, n2):
    p = (x1 + x2) / (n1 + n2); se = np.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    return 1.0 if se == 0 else float(2 * (1 - stats.norm.cdf(abs((x1 / n1 - x2 / n2) / se))))


def _flag(p):
    return "significant" if p < 0.01 else "suggestive" if p < 0.05 else "not significant"


def investigate(col: str | None = None, value=None) -> dict:
    m = master(); F = []
    if col:
        g, rest = m[m[col] == value], m[m[col] != value]; label = f"{col} = {value}"
    else:
        g, rest = m[m.churned == 1], m[m.churned == 0]; label = "churned customers vs active customers"
    out = {"label": label, "n_group": len(g), "n_rest": len(rest), "findings": []}
    if col:
        cg, cr = g.churned.mean(), rest.churned.mean(); p = _ztest(g.churned.sum(), len(g), rest.churned.sum(), len(rest))
        out["headline"] = {"group_churn": float(cg), "rest_churn": float(cr), "gap_pts": float((cg - cr) * 100), "p": p, "flag": _flag(p)}
        # churn reasons among churned customers
        cg_r, cr_r = g[g.churned == 1].churn_reason.value_counts(), rest[rest.churned == 1].churn_reason.value_counts()
        ng, nr = cg_r.sum(), cr_r.sum()
        for reason in cg_r.index:
            a, b = cg_r.get(reason, 0), cr_r.get(reason, 0)
            if a < 8:
                continue
            p = _ztest(a, ng, b, nr); lift = (a / ng) / max(b / nr, 1e-9)
            F.append({"kind": "churn reason", "text": f"'{reason}' is {a / ng:.0%} of churn here vs {b / nr:.0%} elsewhere ({lift:.1f}x)", "p": p, "effect": abs(a / ng - b / nr)})
    else:
        cg_r = g.churn_reason.value_counts(normalize=True).head(3)
        F.append({"kind": "churn reason", "text": "Top reasons: " + ", ".join(f"{k} ({v:.0%})" for k, v in cg_r.items()), "p": 0.0, "effect": 1.0})
    # behaviour metrics
    for c, (name, fmt) in METRICS.items():
        a, b = g[c].dropna(), rest[c].dropna()
        if len(a) < 20 or len(b) < 20:
            continue
        t, p = stats.ttest_ind(a, b, equal_var=False); d = (a.mean() - b.mean()) / np.sqrt((a.var() + b.var()) / 2 + 1e-9)
        F.append({"kind": "behaviour", "text": f"{name}: {fmt.format(a.mean())} vs {fmt.format(b.mean())}", "p": float(p), "effect": float(abs(d))})
    # mix of plan / channel / segment
    for c in ["plan_name", "acquisition_channel", "segment_name"]:
        if c == col:
            continue
        sg, sr = g[c].value_counts(normalize=True), rest[c].value_counts(normalize=True)
        for lvl in sg.index:
            diff = sg[lvl] - sr.get(lvl, 0)
            if abs(diff) >= 0.04:
                p = _ztest((g[c] == lvl).sum(), len(g), (rest[c] == lvl).sum(), len(rest))
                F.append({"kind": "mix", "text": f"{lvl} ({c.replace('_', ' ')}) is {sg[lvl]:.0%} of this group vs {sr.get(lvl, 0):.0%} elsewhere", "p": p, "effect": abs(diff)})
    # complaint categories
    t = load_table("support_tickets").merge(m[["customer_id"] + ([col] if col else ["churned"])], on="customer_id")
    tg = t[(t[col] == value)] if col else t[t.churned == 1]; tr = t[(t[col] != value)] if col else t[t.churned == 0]
    for cat in t.issue_category.unique():
        a, b = (tg.issue_category == cat).sum(), (tr.issue_category == cat).sum()
        if len(tg) and len(tr) and abs(a / len(tg) - b / len(tr)) >= 0.03:
            p = _ztest(a, len(tg), b, len(tr)); F.append({"kind": "complaints", "text": f"{cat} tickets are {a / len(tg):.0%} of tickets vs {b / len(tr):.0%} elsewhere", "p": p, "effect": abs(a / len(tg) - b / len(tr))})
    for f in F:
        f["flag"] = _flag(f["p"])
    out["findings"] = sorted([f for f in F if f["p"] < 0.05], key=lambda f: f["p"])[:6]
    out["n_tests"] = len(F)
    return out


def analyse(question: str, use_llm: bool = True) -> dict:
    col, value = detect_group(question); inv = investigate(col, value)
    h = inv.get("headline")
    lines = []
    if h:
        lines.append(f"Churn in {inv['label']}: {h['group_churn']:.1%} (n={inv['n_group']:,}) vs {h['rest_churn']:.1%} elsewhere - gap {h['gap_pts']:+.1f} pts, {h['flag']} (p={h['p']:.3f}).")
    lines += [f"[{f['flag']}] {f['kind']}: {f['text']} (p={f['p']:.3f})" for f in inv["findings"]]
    evidence = "\n".join(lines) if lines else "No statistically significant differences were found."
    note = f"{inv['n_tests']} comparisons were tested, so 'suggestive' (p<0.05) results can occur by chance; only 'significant' (p<0.01) ones are reliable."
    fallback = evidence + "\n\n" + note
    answer, used = fallback, False
    if use_llm:
        try:
            answer, used = get_client().chat(f"Question: {question}\n\nStatistical findings:\n{evidence}\n\nNote: {note}", system=RCA_SYSTEM, temperature=0.2, max_tokens=450), True
        except LLMError:
            pass
    return {"group": (col, value), "investigation": inv, "evidence": evidence, "answer": answer, "used_llm": used}
