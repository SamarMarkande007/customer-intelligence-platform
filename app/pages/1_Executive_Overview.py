import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import numpy as np, pandas as pd, plotly.express as px, plotly.graph_objects as go
import streamlit as st
from app import ui, data

ui.setup("Executive Overview")
m = data.get_master(); act = m[m.active]
ui.page_header("Executive Overview", "Revenue, churn and risk at a glance · data as of 30 Jun 2026", "Analytics")

mc = data.monthly_churn(); last, prev = mc.rate.iloc[-1], mc.rate.iloc[-4:-1].mean()
mrr = act.monthly_price.sum(); high = act[act.risk_tier == "High"]
ui.kpi_row([
    dict(label="Active customers", value=f"{len(act):,}", sub=f"of {len(m):,} ever", tone="accent"),
    dict(label="Monthly recurring revenue", value=ui.money(mrr), sub=f"ARPU {ui.money(act.monthly_price.mean(), 2)}"),
    dict(label="Churn rate (all-time)", value=f"{m.churned.mean():.1%}", sub=f"{int(m.churned.sum()):,} cancelled", tone="warn"),
    dict(label="Churn, latest month", value=f"{last:.2f}%", sub="vs prior 3-mo avg", delta=last - prev, delta_fmt="{:.2f} pts", good_when_up=False),
    dict(label="High-risk MRR", value=ui.money(high.monthly_price.sum()), sub=f"{len(high):,} customers · {high.monthly_price.sum() / mrr:.0%} of MRR", tone="accent"),
    dict(label="Expected monthly loss", value=ui.money(act.expected_loss_monthly.sum()), sub="calibrated P(churn) × price"),
])

c1, c2 = st.columns([2, 1])
with c1, ui.card():
    ui.section("Monthly churn rate", "cancellations ÷ customers active at month start")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=mc.month, y=mc.rate, mode="lines+markers", line=dict(color=ui.RED, width=3), marker=dict(size=7), fill="tozeroy", fillcolor="rgba(229,9,20,.12)",
                             customdata=np.c_[mc.churned, mc.active_at_start], hovertemplate="%{x|%b %Y}<br><b>%{y:.2f}%</b><br>%{customdata[0]} of %{customdata[1]:,}<extra></extra>"))
    fig.update_yaxes(ticksuffix="%", rangemode="tozero"); ui.plot(ui.style_fig(fig, 310, legend=False))
    st.caption("No churn dates exist before Oct 2025, so Jul–Sep 2025 show 0% by construction (a property of the dataset, not good news).")
with c2, ui.card():
    ui.section("MRR by plan")
    pm = act.groupby("plan_name").monthly_price.sum().reindex(["Basic", "Standard", "Premium"])
    fig = go.Figure(go.Pie(labels=pm.index, values=pm.values, hole=.64, marker=dict(colors=[ui.PLAN_COLORS[p] for p in pm.index], line=dict(color="#14141B", width=3)), textinfo="percent", sort=False,
                           hovertemplate="%{label}<br>$%{value:,.0f}/month<extra></extra>"))
    fig.add_annotation(text=f"<b>{ui.money(mrr)}</b><br><span style='font-size:11px;color:#9A9AAA'>per month</span>", showarrow=False, font=dict(size=20, color="#fff"))
    ui.plot(ui.style_fig(fig, 310, legend=True))

c3, c4 = st.columns([3, 2])
with c3, ui.card():
    ui.section("Where we lose customers", "churn rate by country · bubble size = customers")
    g = m.groupby("country").agg(customers=("churned", "size"), churn=("churned", "mean")).reset_index(); g["churn_pct"] = g.churn * 100
    fig = px.scatter_geo(g, locations="country", locationmode="country names", size="customers", color="churn_pct", color_continuous_scale=["#2FBF71", "#F5A524", "#E50914"],
                         range_color=(g.churn_pct.min(), g.churn_pct.max()), size_max=34, hover_name="country", hover_data={"country": False, "customers": ":,", "churn_pct": ":.1f"})
    fig.update_geos(bgcolor="rgba(0,0,0,0)", showframe=False, showcountries=True, countrycolor="#2a2a38", landcolor="#191923", oceancolor="rgba(0,0,0,0)", showocean=True, coastlinecolor="#2a2a38", projection_type="natural earth")
    fig.update_coloraxes(colorbar=dict(title="Churn %", thickness=10, len=.7)); ui.plot(ui.style_fig(fig, 370, legend=False, margin=(0, 0, 0, 0)))
with c4, ui.card():
    ui.section("Why they leave", "top cancellation reasons")
    r = m[m.churned == 1].churn_reason.value_counts().head(8).sort_values()
    fig = go.Figure(go.Bar(x=r.values, y=r.index, orientation="h", marker=dict(color=r.values, colorscale=[[0, "#4a0b10"], [1, ui.RED]]), text=[f"{v / r.sum():.0%}" for v in r.values], textposition="outside", cliponaxis=False,
                           hovertemplate="%{y}<br>%{x} customers<extra></extra>"))
    fig.update_xaxes(visible=False); ui.plot(ui.style_fig(fig, 370, legend=False, margin=(0, 40, 0, 0)))

c5, c6 = st.columns(2)
with c5, ui.card():
    ui.section("Monthly revenue by plan", "successful payments")
    rv = data.monthly_revenue(); rv = rv[rv.month >= "2022-01-01"]
    fig = px.area(rv, x="month", y="amount", color="plan_name", color_discrete_map=ui.PLAN_COLORS, category_orders={"plan_name": ["Basic", "Standard", "Premium"]})
    fig.update_yaxes(tickprefix="$", title=None); fig.update_xaxes(title=None); ui.plot(ui.style_fig(fig, 320))
with c6, ui.card():
    ui.section("Support demand", "tickets per quarter by category")
    qt = data.quarterly_tickets()
    fig = px.bar(qt, x="quarter", y="tickets", color="issue_category", color_discrete_sequence=ui.PALETTE)
    fig.update_xaxes(title=None); fig.update_yaxes(title=None); ui.plot(ui.style_fig(fig, 320))

ui.section("What the data says")
tot = qt.groupby("quarter").tickets.sum(); seg = m.groupby("segment_name").churned.mean().sort_values()
ui.callout(f"<b>Support demand is accelerating:</b> {int(tot.iloc[-1]):,} tickets last quarter vs {int(tot.iloc[0]):,} two years ago ({tot.iloc[-1] / tot.iloc[0]:.1f}×). Billing & Payments is the largest category and has the lowest satisfaction.", "warn")
ui.callout(f"<b>The riskiest revenue is concentrated:</b> {len(high):,} High-risk customers carry {ui.money(high.monthly_price.sum())}/month ({high.monthly_price.sum() / mrr:.0%} of MRR). Working that list first is the highest-leverage retention move.")
ui.callout(f"<b>Segments differ more than countries:</b> churn ranges {seg.min():.0%} ({seg.index[0]}) to {seg.max():.0%} ({seg.index[-1]}), while country gaps are mostly within noise.", "info")
