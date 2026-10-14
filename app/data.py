"""Cached aggregations for the dashboard (all computed from the processed CSVs, so the app works without MySQL)."""
from __future__ import annotations
import numpy as np
import pandas as pd
import streamlit as st
from src.utils.data_loader import master, load_table
from src.utils.config import REFERENCE_DATE


@st.cache_data(show_spinner=False)
def get_master() -> pd.DataFrame:
    return master()


@st.cache_data(show_spinner=False)
def monthly_churn(start: str = "2025-07", end: str = "2026-06") -> pd.DataFrame:
    m = master(); rows = []
    for per in pd.period_range(start, end, freq="M"):
        s, e = per.start_time, (per + 1).start_time
        act = m[(m.registration_date < s) & (m.churn_date.isna() | (m.churn_date >= s))]
        c = act[act.churn_date.notna() & (act.churn_date < e)]
        rows.append({"month": per.to_timestamp(), "active_at_start": len(act), "churned": len(c), "rate": len(c) / max(len(act), 1) * 100})
    return pd.DataFrame(rows)


@st.cache_data(show_spinner=False)
def monthly_revenue() -> pd.DataFrame:
    p = load_table("payments"); s = load_table("subscriptions")[["subscription_id", "plan_id"]]; pl = load_table("subscription_plans")[["plan_id", "plan_name"]]
    d = p[p.payment_status == "Success"].merge(s, on="subscription_id").merge(pl, on="plan_id")
    d["month"] = d.payment_date.dt.to_period("M").dt.to_timestamp()
    return d.groupby(["month", "plan_name"]).amount.sum().reset_index()


@st.cache_data(show_spinner=False)
def quarterly_tickets() -> pd.DataFrame:
    t = load_table("support_tickets").dropna(subset=["ticket_date"]); t = t[t.ticket_date >= "2024-04-01"]
    t["quarter"] = t.ticket_date.dt.to_period("Q").dt.start_time
    return t.groupby(["quarter", "issue_category"]).size().reset_index(name="tickets")


@st.cache_data(show_spinner=False)
def viewing_device() -> pd.DataFrame:
    return load_table("viewing_activity").groupby(["customer_id", "device_type"]).watch_duration_minutes.sum().reset_index()


@st.cache_data(show_spinner=False)
def viewing_genre() -> pd.DataFrame:
    v = load_table("viewing_activity")[["customer_id", "content_id", "watch_duration_minutes"]].merge(load_table("content")[["content_id", "genre", "content_type"]], on="content_id")
    return v.groupby(["customer_id", "genre"]).watch_duration_minutes.sum().reset_index()


@st.cache_data(show_spinner=False)
def customer_monthly_watch(cid: str) -> pd.DataFrame:
    v = load_table("viewing_activity"); v = v[v.customer_id == cid]
    d = v.assign(month=v.viewing_date.dt.to_period("M").dt.to_timestamp()).groupby("month").agg(minutes=("watch_duration_minutes", "sum"), sessions=("viewing_id", "count")).reset_index()
    full = pd.DataFrame({"month": pd.date_range("2025-07-01", "2026-06-01", freq="MS")})
    return full.merge(d, on="month", how="left").fillna(0)


def customer_payments(cid: str, n: int = 12) -> pd.DataFrame:
    p = load_table("payments"); p = p[p.customer_id == cid].sort_values("payment_date", ascending=False).head(n)
    return p[["payment_date", "amount", "payment_method", "payment_status", "failed_payment_reason"]]


def customer_tickets(cid: str, n: int = 8) -> pd.DataFrame:
    t = load_table("support_tickets"); t = t[t.customer_id == cid].sort_values("ticket_date", ascending=False).head(n)
    return t[["ticket_date", "issue_category", "issue_subcategory", "priority", "ticket_status", "customer_satisfaction_score"]]


@st.cache_data(show_spinner=False)
def metrics_json(name: str) -> dict:
    import json
    from src.utils.config import ROOT
    p = ROOT / "reports" / name
    return json.load(open(p)) if p.exists() else {}
