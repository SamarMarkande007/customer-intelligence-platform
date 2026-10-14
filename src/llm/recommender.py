"""
Capability 6: retention recommender. Rules decide the ACTION (so it is consistent, auditable and cost-aware); the LLM only writes the
customer-facing message. The offer is only recommended when its expected value beats its cost (same economics as notebook 04).
"""
from __future__ import annotations
from src.llm.llm_client import get_client, LLMError
from src.llm.explainer import explain_customer
from src.utils.data_loader import master, load_table

SAVE_RATE, MONTHS_SAVED = 0.30, 6          # keep in sync with notebook 04, section 7
MSG_SYSTEM = ("You write a short, warm, honest retention email for a streaming service. Max 110 words plus a subject line. Use the first name. "
              "Mention ONLY the offer described, no invented perks or deadlines, no pressure or guilt, no mention of 'churn risk' or analytics. "
              "Format exactly:\nSubject: ...\n\nBody...")

PLAYBOOK = {   # (risk, value) -> (priority, action, channel, discount %, months, sla)
    ("High", "High"):   ("P1 - priority save", "Personal outreach from a retention specialist plus a loyalty offer", "Phone / personal email", 0.25, 3, "within 48 hours"),
    ("High", "Medium"): ("P2 - targeted offer", "Targeted retention offer with a value recap", "Email + in-app banner", 0.15, 2, "within 5 days"),
    ("High", "Low"):    ("P3 - light-touch offer", "Small offer, only because the expected benefit exceeds its cost", "Email / push", 0.10, 2, "next campaign cycle"),
    ("Medium", "High"): ("P2 - proactive care", "Proactive check-in and personalised recommendations", "Email", 0.0, 0, "within 2 weeks"),
    ("Medium", "Medium"): ("P3 - engage", "Personalised content recommendations", "Email / push", 0.0, 0, "next campaign cycle"),
    ("Medium", "Low"):  ("P4 - monitor", "Include in the standard newsletter; monitor", "Email", 0.0, 0, "none"),
}
DRIVER_TACTICS = {
    "failed_payment_count": "Payment recovery: prompt to update the card, retry the payment and offer a grace period",
    "failed_payment_rate": "Payment recovery: prompt to update the card, retry the payment and offer a grace period",
    "failed_payments_90d": "Payment recovery: prompt to update the card, retry the payment and offer a grace period",
    "avg_customer_satisfaction": "Service recovery: a follow-up call on the unhappy support experience before any discount",
    "low_csat_count": "Service recovery: a follow-up call on the unhappy support experience before any discount",
    "sessions_90d": "Re-engagement: 'new for you' recommendations based on past viewing",
    "minutes_90d": "Re-engagement: 'new for you' recommendations based on past viewing",
    "days_since_last_activity": "Re-engagement: 'new for you' recommendations based on past viewing",
    "engagement_score": "Re-engagement: 'new for you' recommendations based on past viewing",
    "customer_tenure_days": "Early-life care: onboarding check-in and a how-to-get-more-from-your-plan message",
    "auto_renew": "Renewal care: a friendly value recap before the next billing date",
}


def recommend(customer_id: str, use_llm: bool = True) -> dict:
    m = master(); row = m[m.customer_id == customer_id]
    if row.empty:
        return {"error": f"Customer {customer_id} was not found."}
    r = row.iloc[0]
    if not r.active:
        return {"error": f"{customer_id} has already churned ({r.churn_reason}); use a win-back campaign rather than retention."}
    ex = explain_customer(customer_id, use_llm=False)
    risk, value = ex["risk_tier"], r.value_tier
    if risk == "Low":
        plan = ("P5 - no action", "No retention action; consider an upgrade or loyalty message" if r.plan_name != "Premium" else "No action needed", "None", 0.0, 0, "none")
    else:
        plan = PLAYBOOK[(risk, value)]
    priority, action, channel, disc, months, sla = plan
    cost = round(disc * r.monthly_price * months, 2)
    benefit = round(ex["churn_probability"] * SAVE_RATE * r.monthly_price * MONTHS_SAVED, 2)
    downgraded = False
    if cost > 0 and benefit <= cost:
        action, channel, disc, months, cost, priority, downgraded = "Offer not cost-justified for this customer: use a no-discount nudge", "Email / push", 0.0, 0, 0.0, "P3 - low-cost nudge", True
    tactics = list(dict.fromkeys(DRIVER_TACTICS[d["feature"]] for d in ex["drivers_up"] if d["feature"] in DRIVER_TACTICS))[:3]
    seg_note = {"Dormant Accounts": "Segment: dormant - lead with content, not price.", "Budget Basic Subscribers": "Segment: budget Basic - upgrade / bundle offers beat discounts.",
                "High-Value Engaged (Standard/Premium)": "Segment: high-value - fix service experience first.", "Engaged & Well-Supported": "Segment: loyal core - protect, avoid discounting."}.get(r.segment_name, "")
    offer = f"{disc:.0%} off for {months} months (cost about ${cost:.2f})" if disc else "No discount"
    rec = {"customer_id": customer_id, "risk_tier": risk, "value_tier": value, "segment": r.segment_name, "plan": r.plan_name, "priority": priority, "action": action,
           "channel": channel, "offer": offer, "sla": sla, "offer_cost": cost, "expected_benefit": benefit, "net_value": round(benefit - cost, 2),
           "tactics": tactics, "segment_note": seg_note, "cost_downgraded": downgraded, "explanation": ex, "assumptions": f"Expected benefit = P(churn) x {SAVE_RATE:.0%} save rate x ${r.monthly_price:.2f} x {MONTHS_SAVED} months."}
    first = load_table("customers").set_index("customer_id").first_name.get(customer_id, "there")
    fallback = (f"Subject: We'd love to keep you watching\n\nHi {first},\n\nThanks for being a member. " +
                (f"As a thank-you we'd like to offer you {disc:.0%} off your next {months} months. " if disc else "Here are a few titles picked for you based on what you enjoy. ") +
                "If anything about your experience hasn't been right, just reply to this email and we'll sort it out.\n\nThe Customer Care Team")
    rec["message"], rec["used_llm"] = fallback, False
    if use_llm and priority not in ("P4 - monitor", "P5 - no action"):
        try:
            rec["message"] = get_client().chat(f"First name: {first}. Plan: {r.plan_name}. Offer: {offer}. Main approach: {action}. Tone notes: {'; '.join(tactics) or 'friendly, helpful'}.",
                                               system=MSG_SYSTEM, temperature=0.4, max_tokens=300); rec["used_llm"] = True
        except LLMError:
            pass
    return rec
