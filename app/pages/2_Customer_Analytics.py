import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import numpy as np, pandas as pd, plotly.express as px, plotly.graph_objects as go
import streamlit as st
from app import ui, data

ui.setup("Customer Analytics")
m = data.get_master()
ui.page_header("Customer Analytics", "Slice the customer base: who they are, what they pay for and how they watch", "Analytics")

with ui.card():
    f1, f2, f3, f4, f5 = st.columns(5)
    sel_country = f1.multiselect("Country", sorted(m.country.unique()), placeholder="All countries")
    sel_plan = f2.multiselect("Plan", ["Basic", "Standard", "Premium"], placeholder="All plans")
    sel_seg = f3.multiselect("Behavioural segment", sorted(m.segment_name.dropna().unique()), placeholder="All segments")
    sel_ch = f4.multiselect("Acquisition channel", sorted(m.acquisition_channel.unique()), placeholder="All channels")
    status = f5.selectbox("Status", ["All", "Active", "Churned"])
d = m.copy()
for col, sel in [("country", sel_country), ("plan_name", sel_plan), ("segment_name", sel_seg), ("acquisition_channel", sel_ch)]:
    if sel:
        d = d[d[col].isin(sel)]
if status != "All":
    d = d[d.active == (status == "Active")]
if d.empty:
    st.warning("No customers match these filters."); st.stop()

ui.kpi_row([
    dict(label="Customers", value=f"{len(d):,}", sub=f"{len(d) / len(m):.0%} of all", tone="accent"),
    dict(label="Churn rate", value=f"{d.churned.mean():.1%}", sub=f"overall {m.churned.mean():.1%}", delta=(d.churned.mean() - m.churned.mean()) * 100, delta_fmt="{:.1f} pts", good_when_up=False),
    dict(label="Avg monthly price", value=ui.money(d.monthly_price.mean(), 2), sub="current plan"),
    dict(label="Avg tenure", value=f"{d.customer_tenure_days.mean() / 365:.1f} yrs", sub=f"median age {d.age.median():.0f}"),
    dict(label="Engagement score", value=f"{d.engagement_score.mean():.0f}/100", sub="90-day activity"),
    dict(label="Support CSAT", value=f"{d.avg_customer_satisfaction.mean():.2f}/5" if d.avg_customer_satisfaction.notna().any() else "n/a", sub=f"{d.support_ticket_count.mean():.1f} tickets / customer"),
])

t1, t2, t3 = st.tabs(["Who they are", "What they pay for", "How they watch"])
with t1:
    a, b = st.columns(2)
    with a, ui.card():
        ui.section("Customers by country", "top 12")
        s = d.country.value_counts().head(12).sort_values()
        fig = go.Figure(go.Bar(x=s.values, y=s.index, orientation="h", marker_color=ui.RED, text=s.values, textposition="outside", cliponaxis=False)); fig.update_xaxes(visible=False)
        ui.plot(ui.style_fig(fig, 380, legend=False, margin=(0, 30, 0, 0)))
    with b, ui.card():
        ui.section("Age distribution", "by gender")
        fig = px.histogram(d, x="age", color="gender", nbins=30, barmode="stack", color_discrete_sequence=ui.PALETTE); fig.update_yaxes(title=None); fig.update_xaxes(title=None)
        ui.plot(ui.style_fig(fig, 380))
    a, b = st.columns(2)
    with a, ui.card():
        ui.section("Household type", "customer segment (declared)")
        s = d.customer_segment.value_counts()
        fig = go.Figure(go.Pie(labels=s.index, values=s.values, hole=.6, marker=dict(colors=ui.PALETTE, line=dict(color="#14141B", width=3)))); ui.plot(ui.style_fig(fig, 300))
    with b, ui.card():
        ui.section("Acquisition channels", "customers and churn")
        g = d.groupby("acquisition_channel").agg(n=("churned", "size"), churn=("churned", "mean")).sort_values("n")
        fig = go.Figure(); fig.add_bar(x=g.n, y=g.index, orientation="h", marker_color="#3a3a4d", name="Customers")
        fig.add_trace(go.Scatter(x=g.churn * g.n.max() / max(g.churn.max(), .01) * .9, y=g.index, mode="markers+text", marker=dict(color=ui.RED, size=11), text=[f"{c:.0%}" for c in g.churn], textposition="middle right", name="Churn rate", hoverinfo="skip"))
        fig.update_xaxes(visible=False); ui.plot(ui.style_fig(fig, 300))
with t2:
    a, b, c = st.columns(3)
    with a, ui.card():
        ui.section("Plan mix")
        s = d.plan_name.value_counts().reindex(["Basic", "Standard", "Premium"]).fillna(0)
        fig = go.Figure(go.Bar(x=s.index, y=s.values, marker_color=[ui.PLAN_COLORS[i] for i in s.index], text=[f"{v / s.sum():.0%}" for v in s.values], textposition="outside")); fig.update_yaxes(visible=False)
        ui.plot(ui.style_fig(fig, 300, legend=False))
    with b, ui.card():
        ui.section("Churn by plan")
        g = d.groupby("plan_name").churned.mean().reindex(["Basic", "Standard", "Premium"]) * 100
        fig = go.Figure(go.Bar(x=g.index, y=g.values, marker_color=ui.RED, text=[f"{v:.1f}%" for v in g.values], textposition="outside")); fig.add_hline(y=m.churned.mean() * 100, line_dash="dash", line_color="#888", annotation_text="overall")
        fig.update_yaxes(visible=False); ui.plot(ui.style_fig(fig, 300, legend=False))
    with c, ui.card():
        ui.section("Auto-renew")
        g = d.groupby(d.auto_renew.map({1: "ON", 0: "OFF"})).churned.agg(["size", "mean"])
        fig = go.Figure(go.Bar(x=g.index, y=g["mean"] * 100, marker_color=[ui.GREEN if i == "ON" else ui.AMBER for i in g.index], text=[f"{v:.1%}<br>n={n:,}" for v, n in zip(g["mean"], g["size"])], textposition="outside"))
        fig.update_yaxes(visible=False); ui.plot(ui.style_fig(fig, 300, legend=False))
    with ui.card():
        ui.section("Tenure vs churn", "customers grouped by time as a customer")
        d2 = d.assign(tenure=pd.cut(d.customer_tenure_days / 365, [-.01, .5, 1, 2, 3, 5, 10], labels=["<6 mo", "6-12 mo", "1-2 y", "2-3 y", "3-5 y", "5+ y"]))
        g = d2.groupby("tenure", observed=True).churned.agg(["size", "mean"]).reset_index()
        fig = go.Figure(); fig.add_bar(x=g.tenure.astype(str), y=g["size"], marker_color="#2f2f3f", name="Customers", yaxis="y")
        fig.add_trace(go.Scatter(x=g.tenure.astype(str), y=g["mean"] * 100, mode="lines+markers", line=dict(color=ui.RED, width=3), name="Churn %", yaxis="y2"))
        fig.update_layout(yaxis2=dict(overlaying="y", side="right", ticksuffix="%", showgrid=False)); ui.plot(ui.style_fig(fig, 300))
with t3:
    ids = set(d.customer_id)
    a, b = st.columns(2)
    with a, ui.card():
        ui.section("Watch time by device")
        vd = data.viewing_device(); vd = vd[vd.customer_id.isin(ids)].groupby("device_type").watch_duration_minutes.sum().sort_values(ascending=False)
        fig = go.Figure(go.Pie(labels=vd.index, values=vd.values, hole=.6, marker=dict(colors=ui.PALETTE, line=dict(color="#14141B", width=3)))); ui.plot(ui.style_fig(fig, 340))
    with b, ui.card():
        ui.section("Watch time by genre", "hours")
        vg = data.viewing_genre(); vg = (vg[vg.customer_id.isin(ids)].groupby("genre").watch_duration_minutes.sum() / 60).sort_values().tail(12)
        fig = go.Figure(go.Bar(x=vg.values, y=vg.index, orientation="h", marker=dict(color=vg.values, colorscale=[[0, "#4a0b10"], [1, ui.RED]]))); ui.plot(ui.style_fig(fig, 340, legend=False))
    a, b = st.columns(2)
    with a, ui.card():
        ui.section("Engagement score distribution", "0-100, last 90 days")
        fig = px.histogram(d, x="engagement_score", color=d.active.map({True: "Active", False: "Churned"}), nbins=25, barmode="overlay", opacity=.75, color_discrete_map={"Active": ui.BLUE, "Churned": ui.RED})
        fig.update_yaxes(title=None); fig.update_xaxes(title=None); ui.plot(ui.style_fig(fig, 300))
    with b, ui.card():
        ui.section("Churn by recent activity", "sessions in the 90 days before exit / today")
        d3 = d.assign(b=pd.cut(d.sessions_90d, [-1, 0, 1, 3, 6, 100], labels=["0", "1", "2-3", "4-6", "7+"]))
        g = d3.groupby("b", observed=True).churned.agg(["size", "mean"]).reset_index()
        fig = go.Figure(go.Bar(x=g.b.astype(str), y=g["mean"] * 100, marker_color=ui.RED, text=[f"{v:.0%}" for v in g["mean"]], textposition="outside")); fig.update_yaxes(visible=False); ui.plot(ui.style_fig(fig, 300, legend=False))
