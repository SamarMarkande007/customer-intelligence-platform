import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import numpy as np, pandas as pd, plotly.express as px, plotly.graph_objects as go
import streamlit as st
from app import ui, data

ui.setup("Churn Risk")
m = data.get_master(); act = m[m.active].copy()
ui.page_header("Churn Risk", "Who is likely to leave, how much revenue is at stake, and what a retention campaign is worth", "Analytics")

tiers = ["High", "Medium", "Low"]
cols = st.columns(4)
for c, t in zip(cols[:3], tiers):
    s = act[act.risk_tier == t]
    c.markdown(ui.kpi_html(f"{t} risk", f"{len(s):,}", f"{ui.money(s.monthly_price.sum())}/month · avg P(churn) {s.churn_prob_est.mean():.0%}", tone={"High": "accent", "Medium": "warn", "Low": "good"}[t]), unsafe_allow_html=True)
cols[3].markdown(ui.kpi_html("Expected monthly loss", ui.money(act.expected_loss_monthly.sum()), f"{act.expected_loss_monthly.sum() / act.monthly_price.sum():.0%} of MRR"), unsafe_allow_html=True)

a, b, c = st.columns([1, 1, 1.3])
with a, ui.card():
    ui.section("Risk tiers", "active customers")
    s = act.risk_tier.value_counts().reindex(tiers)
    fig = go.Figure(go.Pie(labels=s.index, values=s.values, hole=.65, sort=False, marker=dict(colors=[ui.RISK_COLORS[t] for t in tiers], line=dict(color="#14141B", width=3))))
    fig.add_annotation(text=f"<b>{len(act):,}</b><br><span style='font-size:11px;color:#9A9AAA'>active</span>", showarrow=False, font=dict(size=20, color="#fff")); ui.plot(ui.style_fig(fig, 300))
with b, ui.card():
    ui.section("Revenue at stake", "MRR by tier")
    s = act.groupby("risk_tier").monthly_price.sum().reindex(tiers)
    fig = go.Figure(go.Bar(x=s.index, y=s.values, marker_color=[ui.RISK_COLORS[t] for t in tiers], text=[ui.money(v) for v in s.values], textposition="outside")); fig.update_yaxes(visible=False)
    ui.plot(ui.style_fig(fig, 300, legend=False))
with c, ui.card():
    ui.section("Risk mix by segment", "share of each segment's active customers")
    g = pd.crosstab(act.segment_name, act.risk_tier, normalize="index").reindex(columns=tiers) * 100
    fig = go.Figure([go.Bar(name=t, y=g.index, x=g[t], orientation="h", marker_color=ui.RISK_COLORS[t], text=[f"{v:.0f}%" for v in g[t]], textposition="inside") for t in tiers]); fig.update_layout(barmode="stack"); fig.update_xaxes(visible=False)
    ui.plot(ui.style_fig(fig, 300))

# ------------------------------------------------------------------ campaign simulator
ui.section("Retention campaign simulator", "whom should we contact? Ranked by expected revenue at stake (P(churn) × price)")
with ui.card():
    s1, s2, s3, s4 = st.columns(4)
    cost = s1.slider("Cost per customer contacted ($)", 1.0, 40.0, 5.0, 0.5)
    save = s2.slider("Offer success rate", 0.05, 0.60, 0.30, 0.01, format="%.2f", help="Share of would-be churners who stay because of the offer")
    months = s3.slider("Extra months a saved customer pays", 1, 12, 6)
    n_sel = s4.slider("Customers to contact", 50, len(act), 1500, 50)
    d = act.assign(benefit=act.churn_prob_est * save * act.monthly_price * months).assign(net=lambda x: x.benefit - cost).sort_values("benefit", ascending=False).reset_index(drop=True)
    d["cum_net"] = d.net.cumsum(); d["n"] = np.arange(1, len(d) + 1)
    opt = int(d.cum_net.idxmax()) + 1; chosen = d.iloc[n_sel - 1]
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Expected customers saved", f"{d.churn_prob_est.head(n_sel).sum() * save:,.0f}", help="Σ P(churn) × success rate over the contacted group")
    k2.metric("Campaign cost", ui.money(n_sel * cost)); k3.metric("Expected net value", ui.money(chosen.cum_net), delta=f"ROI {chosen.cum_net / (n_sel * cost):.1f}x")
    k4.metric("Best size for these assumptions", f"{opt:,}", help="Contact customers while expected benefit exceeds cost")
    fig = go.Figure(); fig.add_trace(go.Scatter(x=d.n, y=d.cum_net, mode="lines", line=dict(color=ui.RED, width=3), fill="tozeroy", fillcolor="rgba(229,9,20,.10)", name="Net value"))
    fig.add_trace(go.Scatter(x=[opt], y=[d.cum_net.iloc[opt - 1]], mode="markers+text", marker=dict(size=13, color=ui.GREEN), text=["optimum"], textposition="top center", name="Optimum"))
    fig.add_trace(go.Scatter(x=[n_sel], y=[chosen.cum_net], mode="markers", marker=dict(size=13, color="#fff", line=dict(color=ui.RED, width=3)), name="Your choice"))
    fig.update_xaxes(title="Customers contacted (highest expected revenue at stake first)"); fig.update_yaxes(title="Cumulative net value ($)", tickprefix="$"); ui.plot(ui.style_fig(fig, 320))
    st.caption("Probabilities are calibrated (average ≈ 24%). The model separates risk only modestly (ROC-AUC ≈ 0.62), so the simulator's value comes from cheap offers and prioritising by revenue, not from precise individual predictions.")

# ------------------------------------------------------------------ priority list
ui.section("Priority list", "active customers ranked by expected monthly revenue loss")
with ui.card():
    f1, f2, f3 = st.columns(3)
    tf = f1.multiselect("Risk tier", tiers, default=["High"]); pf = f2.multiselect("Plan", ["Basic", "Standard", "Premium"], placeholder="All plans"); cf = f3.multiselect("Country", sorted(act.country.unique()), placeholder="All countries")
    L = act[act.risk_tier.isin(tf)] if tf else act
    if pf: L = L[L.plan_name.isin(pf)]
    if cf: L = L[L.country.isin(cf)]
    L = L.sort_values("expected_loss_monthly", ascending=False).head(150)
    show = L[["customer_id", "plan_name", "segment_name", "country", "risk_tier", "churn_prob_est", "monthly_price", "expected_loss_monthly", "value_tier", "failed_payment_count", "days_since_last_activity"]].rename(columns={
        "customer_id": "Customer", "plan_name": "Plan", "segment_name": "Segment", "country": "Country", "risk_tier": "Risk", "churn_prob_est": "P(churn)", "monthly_price": "Price", "expected_loss_monthly": "Expected loss / mo",
        "value_tier": "Value tier", "failed_payment_count": "Failed pmts", "days_since_last_activity": "Days inactive"})
    ui.table(show, column_config={"P(churn)": st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=1), "Price": st.column_config.NumberColumn(format="$%.2f"),
                                  "Expected loss / mo": st.column_config.NumberColumn(format="$%.2f")}, height=420)
    st.download_button("⬇ Download this list (CSV)", show.to_csv(index=False).encode(), "priority_customers.csv", "text/csv")
    st.caption("Open the **Customer 360** page to see why a customer is on this list and what to do about it.")

with st.expander("How reliable is the risk model?"):
    mj = data.metrics_json("churn_model_metrics.json")
    if mj:
        t = mj["test_threshold_0.5"]
        st.markdown(f"**{mj['final_model']}** · test ROC-AUC **{t['roc_auc']:.3f}**, PR-AUC {t['pr_auc']:.3f}, recall {t['recall']:.2f} / precision {t['precision']:.2f} at threshold 0.5. Trained on features measured at 30 Sep 2025 to predict churn in the next 9 months (no leakage).")
    st.markdown("The top-risk decile churns at about **1.7×** the average rate. A leaky build would show ROC-AUC 0.71, but that number is not achievable in production, so it is not used. See the *Reports & Models* page for the full model card.")
