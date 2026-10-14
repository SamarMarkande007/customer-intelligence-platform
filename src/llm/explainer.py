"""
Capability 3: explain WHY a customer has their churn risk, in plain language.

Contributions come straight from the logistic-regression coefficients: contribution_i = coef_i x (customer value_i - average customer value_i)
in the model's standardised space, so each number says "how much this feature pushes this customer's risk up or down versus the average
customer". Honest framing is built in: modest model (AUC ~0.62), association not causation.
"""
from __future__ import annotations
from functools import lru_cache
import numpy as np
import pandas as pd
from src.llm.llm_client import get_client, LLMError
from src.utils.data_loader import master, churn_bundle, _calibrator

LABELS = {  # feature -> (label, formatter)
    "failed_payment_count": ("failed payments", lambda v: f"{v:.0f}"),
    "failed_payment_rate": ("share of payments that failed", lambda v: f"{v:.0%}"),
    "failed_payments_90d": ("failed payments in last 90 days", lambda v: f"{v:.0f}"),
    "customer_tenure_days": ("time as a customer", lambda v: f"{v / 365:.1f} years"),
    "avg_customer_satisfaction": ("average support satisfaction", lambda v: f"{v:.1f}/5"),
    "has_csat": ("has a scored support ticket", lambda v: "yes" if v >= .5 else "no"),
    "auto_renew": ("auto-renew", lambda v: "on" if v >= .5 else "off"),
    "low_csat_count": ("low-satisfaction tickets", lambda v: f"{v:.0f}"),
    "support_ticket_count": ("support tickets", lambda v: f"{v:.0f}"),
    "tickets_90d": ("tickets in last 90 days", lambda v: f"{v:.0f}"),
    "sessions_90d": ("viewing sessions in last 90 days", lambda v: f"{v:.0f}"),
    "minutes_90d": ("watch minutes in last 90 days", lambda v: f"{v:.0f}"),
    "days_since_last_activity": ("days since last viewing", lambda v: f"{v:.0f}"),
    "engagement_score": ("engagement score", lambda v: f"{v:.0f}/100"),
    "login_frequency": ("sessions per month", lambda v: f"{v:.1f}"),
    "monthly_price": ("monthly price", lambda v: f"${v:.2f}"),
    "payment_count": ("payments on record", lambda v: f"{v:.0f}"),
    "customer_lifetime_value": ("revenue to date", lambda v: f"${v:.0f}"),
    "plan_changes": ("plan changes", lambda v: f"{v:.0f}"),
    "avg_feedback_rating": ("average feedback rating", lambda v: f"{v:.1f}/5"),
    "negative_feedback_count": ("negative feedback entries", lambda v: f"{v:.0f}"),
    "avg_watch_time_per_session": ("minutes per session", lambda v: f"{v:.0f}"),
    "watch_change_pct_30d": ("recent watch-time momentum", lambda v: f"{v:+.2f}"),
    "monthly_watch_time_trend": ("watch-time trend (min/month)", lambda v: f"{v:+.0f}"),
    "active_days_90d": ("active viewing days (90d)", lambda v: f"{v:.0f}"),
    "n_devices_90d": ("devices used", lambda v: f"{v:.0f}"),
    "avg_completion_90d": ("average completion %", lambda v: f"{v:.0f}%"),
    "avg_resolution_hours": ("average ticket resolution (hours)", lambda v: f"{v:.0f}"),
    "feedback_count": ("feedback entries", lambda v: f"{v:.0f}"),
    "age": ("age", lambda v: f"{v:.0f}"),
    "last_payment_failed": ("last payment failed", lambda v: "yes" if v >= .5 else "no"),
}
CAVEAT = "The model is a modest predictor (ROC-AUC about 0.62), so treat this as a prioritisation signal, not a verdict. Drivers are associations, not proven causes."
EXPLAIN_SYSTEM = ("You explain a customer's churn-risk score to a retention manager. Use ONLY the facts provided. Plain language, no jargon, "
                  "at most 120 words: one sentence on the risk level, then the 2-3 biggest reasons it is higher and any protective factors. "
                  "Do not claim causation, do not invent numbers, and end with one short caution that the model is modest.")


@lru_cache(maxsize=1)
def _population():
    b = churn_bundle(); pre = b["model"].named_steps["pre"]
    return pre.transform(master()[b["features"]]).mean(axis=0), list(pre.get_feature_names_out()), b


def _group(name: str, cats: list[str]):
    if name.startswith("num__"):
        return name[5:], None
    n = name[5:]
    for c in cats:
        if n.startswith(c + "_"):
            return c, n[len(c) + 1:]
    return n, None


def explain_customer(customer_id: str, use_llm: bool = True) -> dict:
    m = master(); row = m[m.customer_id == customer_id]
    if row.empty:
        return {"error": f"Customer {customer_id} was not found."}
    r = row.iloc[0]; mu, names, b = _population(); model = b["model"]
    X = row[b["features"]]; x = model.named_steps["pre"].transform(X)[0]
    raw = float(model.predict_proba(X)[0, 1]); prob = float(_calibrator()(np.array([raw]))[0])
    active = m[m.active]
    pct = float((active.churn_risk_score.dropna() < raw).mean()) if len(active) else np.nan
    tier_cut = b["tier_cutoffs"]; tier = "High" if raw >= tier_cut["high"] else "Medium" if raw >= tier_cut["medium"] else "Low"

    drivers = []
    lr = model.named_steps["m"]
    if hasattr(lr, "coef_"):
        contrib = (x - mu) * lr.coef_[0]; agg = {}
        for n, c in zip(names, contrib):
            f, lvl = _group(n, b["categorical"]); agg.setdefault(f, [0.0, lvl]); agg[f][0] += c
            if lvl is not None and abs(c) > abs(agg[f][0]) * 0.99:
                agg[f][1] = lvl
        for f, (c, lvl) in agg.items():
            if abs(c) < 0.02:
                continue
            if f in LABELS:
                lab, fmt = LABELS[f]; val = r[f]
                cust_txt = "not available" if pd.isna(val) else fmt(val); avg = m[f].mean(); avg_txt = None if pd.isna(avg) else fmt(avg)
            else:
                lab, cust_txt, avg_txt = f.replace("_", " "), str(r[f]), None
            drivers.append({"feature": f, "label": lab, "customer_value": cust_txt, "average_customer": avg_txt, "effect": float(c),
                            "direction": "raises risk" if c > 0 else "lowers risk"})
        drivers.sort(key=lambda d: -abs(d["effect"]))
    up = [d for d in drivers if d["effect"] > 0][:5]; down = [d for d in drivers if d["effect"] < 0][:3]

    profile = {"customer_id": customer_id, "status": "Active" if r.active else f"Churned ({r.churn_reason})", "country": r.country, "plan": r.plan_name,
               "segment": r.segment_name, "tenure_years": round(r.customer_tenure_days / 365, 1), "value_tier": r.value_tier, "revenue_to_date": float(r.clv_actual),
               "monthly_price": float(r.monthly_price)}
    facts = (f"Customer {customer_id}: {profile['plan']} plan, {profile['country']}, segment '{profile['segment']}', {profile['tenure_years']} years as a customer.\n"
             f"Risk tier: {tier} (higher than {pct:.0%} of active customers; estimated chance of leaving within ~9 months about {prob:.0%}, average customer ~24%).\n"
             "Factors raising risk: " + ("; ".join(f"{d['label']} = {d['customer_value']}" + (f" (average {d['average_customer']})" if d['average_customer'] else "") for d in up) or "none notable") + ".\n"
             "Factors lowering risk: " + ("; ".join(f"{d['label']} = {d['customer_value']}" + (f" (average {d['average_customer']})" if d['average_customer'] else "") for d in down) or "none notable") + ".")
    fallback = f"{customer_id} is in the {tier} risk tier (about {prob:.0%} estimated chance of leaving, vs ~24% for an average customer).\n" + \
               ("Risk is raised by: " + "; ".join(f"{d['label']} ({d['customer_value']})" for d in up) + ".\n" if up else "") + \
               ("Protective: " + "; ".join(f"{d['label']} ({d['customer_value']})" for d in down) + ".\n" if down else "") + CAVEAT
    narrative, used = fallback, False
    if use_llm:
        try:
            narrative, used = get_client().chat(facts, system=EXPLAIN_SYSTEM, temperature=0.2, max_tokens=300), True
        except LLMError:
            pass
    return {"profile": profile, "risk_tier": tier, "risk_score": raw, "churn_probability": prob, "percentile_vs_active": pct,
            "drivers_up": up, "drivers_down": down, "narrative": narrative, "used_llm": used, "caveat": CAVEAT}
