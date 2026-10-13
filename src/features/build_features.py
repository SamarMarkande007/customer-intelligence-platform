"""
Customer-level feature builder (PRD section 9.2).

Every feature is computed ONLY from records dated on or before a per-customer `as_of` date, so the same code
supports two uses without leakage:

  * TRAINING snapshot   : as_of = 2025-09-30 for everyone, label = "churned after the snapshot"
  * CURRENT / profiling : as_of = 2026-06-30 for active customers (churn date for churned customers)

Viewing history only exists from 2025-07-01, so engagement windows are 90 days (3 x 30-day buckets).
"""
from __future__ import annotations
import numpy as np
import pandas as pd

WINDOW_DAYS = 90
SESSIONS_CAP = 8           # sessions in 90 days at/above which frequency score = 1 (fixed constant, ~p95 of customers)


def load_clean(processed_dir) -> dict:
    d = {}
    parse = {"customers": ["registration_date"],
             "subscriptions": ["subscription_start_date", "subscription_end_date", "cancellation_date"],
             "viewing_activity": ["viewing_date"], "payments": ["payment_date"],
             "support_tickets": ["ticket_date"], "customer_feedback": ["feedback_date"], "churn_labels": ["churn_date"]}
    for name in ["customers", "subscription_plans", "subscriptions", "content", "viewing_activity", "payments",
                 "support_tickets", "customer_feedback", "churn_labels"]:
        d[name] = pd.read_csv(f"{processed_dir}/{name}.csv", parse_dates=parse.get(name, []))
    return d


def build_features(as_of: pd.Series, data: dict) -> pd.DataFrame:
    """as_of: Series indexed by customer_id with a Timestamp per customer. Returns one row per eligible customer."""
    as_of = as_of.rename("as_of")
    cust = data["customers"].set_index("customer_id").join(as_of, how="inner")
    cust = cust[cust.registration_date <= cust.as_of]

    # ---------------- subscriptions as of the date ----------------
    subs = data["subscriptions"].merge(as_of, left_on="customer_id", right_index=True)
    subs = subs[subs.subscription_start_date <= subs.as_of].sort_values(["customer_id", "subscription_start_date"])
    cur = subs.groupby("customer_id").tail(1).merge(data["subscription_plans"][["plan_id", "plan_name"]], on="plan_id")
    cur = cur.set_index("customer_id")[["plan_name", "monthly_price", "auto_renew"]]
    cur["auto_renew"] = cur.auto_renew.astype(int)
    plan_changes = (subs.groupby("customer_id").size() - 1).rename("plan_changes")
    f = cust.join(cur, how="inner").join(plan_changes)
    f["plan_changes"] = f.plan_changes.fillna(0).astype(int)
    f["customer_tenure_days"] = (f.as_of - f.registration_date).dt.days

    # ---------------- viewing (90-day window before as_of) ----------------
    v = data["viewing_activity"].merge(as_of, left_on="customer_id", right_index=True)
    v = v[v.viewing_date <= v.as_of].copy()
    v["days_before"] = (v.as_of - v.viewing_date).dt.days
    last_view = v.groupby("customer_id").viewing_date.max()
    w = v[v.days_before < WINDOW_DAYS].copy()
    w["bucket"] = (w.days_before // 30).clip(upper=2)
    g = w.groupby("customer_id")
    eng = pd.DataFrame({
        "sessions_90d": g.size(),
        "minutes_90d": g.watch_duration_minutes.sum(),
        "avg_completion_90d": g.completion_percentage.mean(),
        "active_days_90d": g.viewing_date.nunique(),
        "n_devices_90d": g.device_type.nunique(),
    })
    b = w.pivot_table(index="customer_id", columns="bucket", values="watch_duration_minutes", aggfunc="sum", fill_value=0)
    for k in (0, 1, 2):
        eng[f"watch_min_b{k}"] = b[k] if k in b.columns else 0
    f = f.join(eng)
    for c in ["sessions_90d", "minutes_90d", "active_days_90d", "n_devices_90d", "watch_min_b0", "watch_min_b1", "watch_min_b2"]:
        f[c] = f[c].fillna(0)
    f["avg_watch_time_per_session"] = (f.minutes_90d / f.sessions_90d.replace(0, np.nan)).fillna(0)
    f["monthly_watch_time_trend"] = (f.watch_min_b0 - f.watch_min_b2) / 2            # minutes per 30 days, slope over 3 buckets
    f["watch_change_pct_30d"] = (f.watch_min_b0 - f.watch_min_b1) / (f.watch_min_b0 + f.watch_min_b1 + 1)   # bounded -1..1
    f["login_frequency"] = f.sessions_90d / 3                                         # sessions per month
    f["days_since_last_activity"] = ((f.as_of - last_view.reindex(f.index)).dt.days).fillna(WINDOW_DAYS).clip(upper=WINDOW_DAYS)
    f["avg_completion_90d"] = f.avg_completion_90d.fillna(0)

    recency = 1 - f.days_since_last_activity / WINDOW_DAYS
    freq = (f.sessions_90d / SESSIONS_CAP).clip(upper=1)
    depth = f.avg_completion_90d / 100
    f["engagement_score"] = 100 * (0.40 * recency + 0.35 * freq + 0.25 * depth)

    # ---------------- payments ----------------
    p = data["payments"].merge(as_of, left_on="customer_id", right_index=True)
    p = p[p.payment_date <= p.as_of].copy()
    p["failed"] = (p.payment_status == "Failed").astype(int)
    p["ok_amt"] = np.where(p.payment_status == "Success", p.amount, 0.0)
    p["recent_failed"] = ((p.as_of - p.payment_date).dt.days < WINDOW_DAYS).astype(int) * p.failed
    pg = p.groupby("customer_id")
    pay = pd.DataFrame({"payment_count": pg.size(), "failed_payment_count": pg.failed.sum(),
                        "failed_payments_90d": pg.recent_failed.sum(), "customer_lifetime_value": pg.ok_amt.sum()})
    last_p = p.sort_values("payment_date").groupby("customer_id").tail(1).set_index("customer_id")
    pay["last_payment_failed"] = last_p.failed
    pay["last_payment_method"] = last_p.payment_method
    f = f.join(pay)
    for c in ["payment_count", "failed_payment_count", "failed_payments_90d", "customer_lifetime_value", "last_payment_failed"]:
        f[c] = f[c].fillna(0)
    f["last_payment_method"] = f.last_payment_method.fillna("Unknown")
    f["failed_payment_rate"] = (f.failed_payment_count / f.payment_count.replace(0, np.nan)).fillna(0)

    # ---------------- support tickets ----------------
    t = data["support_tickets"].dropna(subset=["ticket_date"]).merge(as_of, left_on="customer_id", right_index=True)
    t = t[t.ticket_date <= t.as_of].copy()
    t["recent"] = ((t.as_of - t.ticket_date).dt.days < WINDOW_DAYS).astype(int)
    t["low_csat"] = (t.customer_satisfaction_score <= 2).astype(int)
    tg = t.groupby("customer_id")
    tk = pd.DataFrame({"support_ticket_count": tg.size(), "tickets_90d": tg.recent.sum(), "low_csat_count": tg.low_csat.sum(),
                       "avg_customer_satisfaction": tg.customer_satisfaction_score.mean(),
                       "avg_resolution_hours": tg.resolution_time_hours.mean()})
    f = f.join(tk)
    for c in ["support_ticket_count", "tickets_90d", "low_csat_count"]:
        f[c] = f[c].fillna(0)
    f["has_csat"] = f.avg_customer_satisfaction.notna().astype(int)          # CSAT is structurally missing, not imputed here

    # ---------------- feedback ----------------
    fb = data["customer_feedback"].merge(as_of, left_on="customer_id", right_index=True)
    fb = fb[fb.feedback_date <= fb.as_of].copy()
    fb["neg"] = (fb.sentiment_label == "Negative").astype(int)
    fg = fb.groupby("customer_id")
    fbk = pd.DataFrame({"feedback_count": fg.size(), "avg_feedback_rating": fg.rating.mean(), "negative_feedback_count": fg.neg.sum()})
    f = f.join(fbk)
    for c in ["feedback_count", "negative_feedback_count"]:
        f[c] = f[c].fillna(0)

    f = f.drop(columns=["watch_min_b0", "watch_min_b1", "watch_min_b2", "first_name", "last_name", "state_or_region", "city",
                         "age_original", "age_was_imputed"], errors="ignore")
    return f.reset_index()


def snapshot_labels(features: pd.DataFrame, churn: pd.DataFrame) -> pd.Series:
    """1 if the customer churned AFTER the snapshot date (churn_date > as_of)."""
    m = features[["customer_id", "as_of"]].merge(churn, on="customer_id", how="left")
    return ((m.churned == 1) & (m.churn_date > m.as_of)).astype(int).values
