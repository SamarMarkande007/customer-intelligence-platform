import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import joblib, numpy as np, pandas as pd, plotly.express as px, plotly.graph_objects as go
import streamlit as st
from app import ui, data
from src.utils.config import ROOT

ui.setup("Segmentation")
m = data.get_master()
ui.page_header("Customer Segments", "Four behavioural groups found with K-Means, each with its own retention playbook", "Analytics")

@st.cache_data(show_spinner=False)
def seg_meta():
    b = joblib.load(ROOT / "models" / "segmentation_model.joblib"); return b["names"], b["descriptions"]
names, desc = seg_meta()
g = m.groupby("segment_id").agg(customers=("churned", "size"), churn=("churned", "mean"), clv=("clv_actual", "mean"), price=("monthly_price", "mean"), eng=("engagement_score", "mean"),
                                csat=("avg_customer_satisfaction", "mean"), active=("active", "sum"), mrr=("monthly_price", lambda s: s[m.loc[s.index, "active"]].sum()))
colors = [ui.AMBER, ui.GREEN, ui.BLUE, ui.GREY]
cols = st.columns(len(g))
for c, (sid, r), col in zip(cols, g.iterrows(), colors):
    c.markdown(f'<div class="seg-card" style="border-top:3px solid {col}"><h4>{names[sid]}</h4><div class="d">{desc[sid]}</div>'
               f'<div class="seg-stat"><span>Customers</span><b>{int(r.customers):,} ({r.customers / len(m):.0%})</b></div><div class="seg-stat"><span>Churn rate</span><b>{r.churn:.1%}</b></div>'
               f'<div class="seg-stat"><span>Avg revenue to date</span><b>{ui.money(r.clv)}</b></div><div class="seg-stat"><span>Active MRR</span><b>{ui.money(r.mrr)}</b></div></div>', unsafe_allow_html=True)

a, b = st.columns([1.2, 1])
with a, ui.card():
    ui.section("Segment fingerprints", "how each segment differs from the average customer (standard deviations)")
    feats = {"customer_tenure_days": "Tenure", "login_frequency": "Logins / month", "avg_watch_time_per_session": "Minutes / session", "days_since_last_activity": "Days inactive",
             "monthly_price": "Price", "failed_payment_rate": "Failed payments", "support_ticket_count": "Tickets", "avg_customer_satisfaction": "Satisfaction"}
    z = (m.groupby("segment_id")[list(feats)].mean() - m[list(feats)].mean()) / m[list(feats)].std()
    fig = go.Figure()
    for (sid, r), col in zip(z.iterrows(), colors):
        v = list(r.values) + [r.values[0]]; th = list(feats.values()) + [list(feats.values())[0]]
        fig.add_trace(go.Scatterpolar(r=v, theta=th, name=names[sid], line=dict(color=col, width=2.5), fill="toself", fillcolor="rgba(%d,%d,%d,0.14)" % tuple(int(col[i:i + 2], 16) for i in (1, 3, 5)), opacity=.95))
    fig.update_layout(polar=dict(bgcolor="rgba(0,0,0,0)", radialaxis=dict(gridcolor="#2a2a38", tickfont=dict(size=9), range=[-1.4, 1.4]), angularaxis=dict(gridcolor="#2a2a38")))
    ui.plot(ui.style_fig(fig, 430))
with b, ui.card():
    ui.section("Churn vs value", "bubble = customers")
    fig = go.Figure()
    for (sid, r), col in zip(g.iterrows(), colors):
        fig.add_trace(go.Scatter(x=[r.clv], y=[r.churn * 100], mode="markers+text", name=names[sid], text=[names[sid].split(" (")[0]], textposition="top center", marker=dict(size=r.customers / 25, color=col, opacity=.85, line=dict(color="#fff", width=1.5))))
    fig.add_hline(y=m.churned.mean() * 100, line_dash="dash", line_color="#777", annotation_text="overall churn"); fig.update_xaxes(title="Average revenue to date ($)", tickprefix="$"); fig.update_yaxes(title="Churn rate (%)", ticksuffix="%")
    ui.plot(ui.style_fig(fig, 430, legend=False))

a, b = st.columns(2)
with a, ui.card():
    ui.section("Plan mix by segment")
    pm = pd.crosstab(m.segment_name, m.plan_name, normalize="index").reindex(columns=["Basic", "Standard", "Premium"]) * 100
    fig = go.Figure([go.Bar(name=p, x=pm.index, y=pm[p], marker_color=ui.PLAN_COLORS[p], text=[f"{v:.0f}%" if v > 6 else "" for v in pm[p]], textposition="inside") for p in pm.columns]); fig.update_layout(barmode="stack"); fig.update_yaxes(visible=False)
    ui.plot(ui.style_fig(fig, 320))
with b, ui.card():
    ui.section("Current risk tier by segment", "active customers")
    act = m[m.active]; rt = pd.crosstab(act.segment_name, act.risk_tier, normalize="index").reindex(columns=["High", "Medium", "Low"]) * 100
    fig = go.Figure([go.Bar(name=t, x=rt.index, y=rt[t], marker_color=ui.RISK_COLORS[t], text=[f"{v:.0f}%" for v in rt[t]], textposition="inside") for t in rt.columns]); fig.update_layout(barmode="stack"); fig.update_yaxes(visible=False)
    ui.plot(ui.style_fig(fig, 320))

ui.section("Playbook", "suggested actions per segment")
PLAY = {0: ("Re-engage, don't discount", "Automated 'new for you' recommendations and a what-you-missed email. They pay but don't watch, so they are the next cancellations."),
        1: ("Protect the loyal core", "Keep service quality high. They churn least and rate support best, so avoid blanket discounts."),
        2: ("Fix service before price", "Largest revenue pool with weak satisfaction. Proactive outreach after bad support experiences beats a discount."),
        3: ("Upgrade, don't over-invest", "Price-sensitive and low value: bundles and upgrade nudges; keep retention spend small.")}
cols = st.columns(len(g))
for c, sid, col in zip(cols, g.index, colors):
    c.markdown(f'<div class="callout" style="border-left-color:{col}"><b>{names[sid]}</b><br><b style="color:{col}">{PLAY[sid][0]}</b><br><span style="color:#aaa;font-size:.85rem">{PLAY[sid][1]}</span></div>', unsafe_allow_html=True)
ui.callout("<b>How to read this:</b> clusters are very stable (adjusted Rand index 0.999 across restarts) but only weakly separated (silhouette 0.19). They are driven by activity vs dormancy, plan price and support experience; tenure and failed payments barely differ between segments.", "info")
