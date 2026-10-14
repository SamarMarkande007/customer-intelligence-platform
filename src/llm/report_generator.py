"""
Capability 4: executive report. All numbers and tables are computed deterministically (so they are always correct); the LLM only writes
the executive summary and recommended actions from those numbers. Without an LLM the report still generates with a template summary.
"""
from __future__ import annotations
from datetime import date
import numpy as np
import pandas as pd
from src.llm.llm_client import get_client, LLMError
from src.utils.config import ROOT, REFERENCE_DATE
from src.utils.data_loader import master, load_table

OUT_DIR = ROOT / "reports" / "generated"
SUMMARY_SYSTEM = ("You are the head of customer analytics writing for executives. Using ONLY the metrics given, write: (1) '## Executive summary' - 4 sentences "
                  "with the headline numbers, (2) '## Recommended actions' - exactly 4 numbered, specific actions each tied to a metric. Never invent numbers. "
                  "Be candid that the churn model is modest (ROC-AUC about 0.62) and that churn dates only start in Oct 2025. No other headings.")


def collect_metrics() -> dict:
    m = master(); act = m[m.active]; ch = m[m.churned == 1]
    t = load_table("support_tickets").dropna(subset=["ticket_date"]); p = load_table("payments")
    mm = {"customers": len(m), "active": len(act), "churned": len(ch), "churn_rate": m.churned.mean(), "mrr": act.monthly_price.sum(), "arpu": act.monthly_price.mean(),
          "expected_loss_monthly": act.expected_loss_monthly.sum(), "high_risk_n": int((act.risk_tier == "High").sum()),
          "high_risk_mrr": act.loc[act.risk_tier == "High", "monthly_price"].sum(), "avg_prob": act.churn_prob_est.mean()}
    months = pd.period_range("2026-01", "2026-06", freq="M"); rows = []
    for per in months:
        s, e = per.start_time, (per + 1).start_time
        start_active = m[(m.registration_date < s) & (m.churn_date.isna() | (m.churn_date >= s))]
        c = start_active[(start_active.churn_date.notna()) & (start_active.churn_date < e)]
        rows.append({"month": str(per), "active_at_start": len(start_active), "churned": len(c), "rate": len(c) / len(start_active)})
    mm["monthly_churn"] = pd.DataFrame(rows)
    g = m.groupby("country").churned.agg(["size", "mean"]).sort_values("mean", ascending=False); mm["country_churn"] = g
    mm["reasons"] = ch.churn_reason.value_counts().head(5)
    mm["plans"] = m.groupby("plan_name").agg(customers=("churned", "size"), churn_rate=("churned", "mean"), mrr=("monthly_price", lambda s: s[m.loc[s.index, "active"]].sum()))
    mm["segments"] = m.groupby("segment_name").agg(customers=("churned", "size"), churn_rate=("churned", "mean"), avg_revenue_to_date=("clv_actual", "mean"))
    r90 = t[t.ticket_date > REFERENCE_DATE - pd.Timedelta(days=90)]; p90 = t[(t.ticket_date <= REFERENCE_DATE - pd.Timedelta(days=90)) & (t.ticket_date > REFERENCE_DATE - pd.Timedelta(days=180))]
    cats = pd.DataFrame({"last_90d": r90.issue_category.value_counts(), "prior_90d": p90.issue_category.value_counts()}).fillna(0).astype(int)
    cats["change_pct"] = (cats.last_90d / cats.prior_90d.replace(0, np.nan) - 1) * 100; mm["complaints"] = cats.sort_values("last_90d", ascending=False)
    mm["csat"] = t.customer_satisfaction_score.mean()
    pf = p[p.payment_date > p.payment_date.max() - pd.Timedelta(days=90)]; mm["failed_pay_rate_90d"] = (pf.payment_status == "Failed").mean()
    return mm


def _md_table(df: pd.DataFrame, fmt: dict) -> str:
    cols = list(df.columns); head = "| " + " | ".join([df.index.name or ""] + cols) + " |\n|" + "---|" * (len(cols) + 1) + "\n"
    body = "".join("| " + " | ".join([str(i)] + [fmt.get(c, "{}").format(v) for c, v in r.items()]) + " |\n" for i, r in df.iterrows())
    return head + body


def generate_report(use_llm: bool = True, save: bool = True) -> dict:
    mm = collect_metrics()
    facts = (f"Customers {mm['customers']:,}; active {mm['active']:,}; churn rate {mm['churn_rate']:.1%}; MRR ${mm['mrr']:,.0f}; ARPU ${mm['arpu']:.2f}. "
             f"Expected monthly revenue lost to churn about ${mm['expected_loss_monthly']:,.0f}; {mm['high_risk_n']:,} High-risk customers carry ${mm['high_risk_mrr']:,.0f}/month. "
             f"Latest monthly churn ({mm['monthly_churn'].month.iloc[-1]}): {mm['monthly_churn'].rate.iloc[-1]:.1%}. Top churn reasons: " + ", ".join(f"{k} ({v})" for k, v in mm['reasons'].items()) + ". "
             f"Highest-churn countries: " + ", ".join(f"{k} {r['mean']:.1%}" for k, r in mm['country_churn'].head(3).iterrows()) + ". "
             f"Support CSAT {mm['csat']:.2f}/5; failed-payment rate last 90 days {mm['failed_pay_rate_90d']:.1%}. Complaints last 90d vs prior: " +
             ", ".join(f"{k} {r.last_90d} ({r.change_pct:+.0f}%)" for k, r in mm['complaints'].head(3).iterrows()) + ".")
    fb = (f"## Executive summary\n\nThe platform has {mm['active']:,} active customers generating ${mm['mrr']:,.0f} of monthly recurring revenue; overall churn is {mm['churn_rate']:.1%}. "
          f"{mm['high_risk_n']:,} customers are in the High-risk tier, carrying ${mm['high_risk_mrr']:,.0f} per month. Top churn driver: {mm['reasons'].index[0]}. "
          f"Support satisfaction averages {mm['csat']:.2f}/5.\n\n## Recommended actions\n\n1. Work the High-risk list, starting with the highest MRR.\n2. Fix payment recovery (failed-payment rate {mm['failed_pay_rate_90d']:.1%}).\n"
          f"3. Address '{mm['reasons'].index[0]}' with product or pricing options.\n4. Review the fastest-growing complaint category.")
    narrative, used = fb, False
    if use_llm:
        try:
            narrative, used = get_client().chat(facts, system=SUMMARY_SYSTEM, temperature=0.3, max_tokens=600), True
        except LLMError:
            pass
    md = f"# Executive Customer Report\n*As of {REFERENCE_DATE.date()} · generated {date.today()}*\n\n{narrative}\n\n---\n\n## Key metrics\n\n"
    md += f"| Metric | Value |\n|---|---|\n| Customers | {mm['customers']:,} |\n| Active customers | {mm['active']:,} |\n| Churn rate (all time) | {mm['churn_rate']:.1%} |\n| Monthly recurring revenue | ${mm['mrr']:,.0f} |\n"
    md += f"| ARPU | ${mm['arpu']:.2f} |\n| High-risk customers | {mm['high_risk_n']:,} (${mm['high_risk_mrr']:,.0f}/month) |\n| Expected monthly revenue lost | ${mm['expected_loss_monthly']:,.0f} |\n| Avg support CSAT | {mm['csat']:.2f} / 5 |\n\n"
    md += "## Monthly churn, 2026\n\n" + _md_table(mm["monthly_churn"].set_index("month"), {"rate": "{:.2%}"}) + "\n## Churn by plan\n\n" + _md_table(mm["plans"], {"churn_rate": "{:.1%}", "mrr": "${:,.0f}"})
    md += "\n## Segments\n\n" + _md_table(mm["segments"], {"churn_rate": "{:.1%}", "avg_revenue_to_date": "${:,.0f}"}) + "\n## Complaints by category\n\n" + _md_table(mm["complaints"], {"change_pct": "{:+.0f}%"})
    md += "\n## Top churn reasons\n\n" + "".join(f"- {k}: {v}\n" for k, v in mm["reasons"].items())
    md += "\n## Caveats\n\n- The churn model is modest (ROC-AUC about 0.62); scores prioritise, they do not predict individuals reliably.\n- Churn dates exist only from Oct 2025; payments table keeps at most 15 payments per customer; viewing data covers Jul 2025 - Jun 2026.\n"
    path = None
    if save:
        OUT_DIR.mkdir(parents=True, exist_ok=True); path = OUT_DIR / f"executive_report_{date.today()}.md"; path.write_text(md, encoding="utf-8")
    return {"markdown": md, "metrics": mm, "path": str(path) if path else None, "used_llm": used}
