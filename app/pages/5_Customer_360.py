import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import numpy as np, pandas as pd, plotly.graph_objects as go
import streamlit as st
from app import ui, data
from src.llm.llm_client import llm_available
from src.llm.explainer import explain_customer
from src.llm.recommender import recommend
from src.utils.data_loader import load_table

ui.setup("Customer 360")
m = data.get_master()
ui.page_header("Customer 360", "One customer: profile, churn risk and why, behaviour, billing, support, and the recommended next action", "Customers & AI")

act = m[m.active].sort_values("churn_risk_score", ascending=False)
ids = list(act.customer_id) + list(m[~m.active].customer_id)
c1, c2, c3 = st.columns([2, 1, 1.4])
if "c360" not in st.session_state:
    st.session_state.c360 = ids[0]
if c2.button("⚠ Highest-risk customer"):
    st.session_state.c360 = ids[0]
if c3.button("🎲 Random active customer"):
    st.session_state.c360 = act.customer_id.sample(1).iloc[0]
cid = c1.selectbox("Customer ID (type to search)", ids, index=ids.index(st.session_state.c360), key="c360_sel")
st.session_state.c360 = cid
use_llm = st.toggle("Use AI to write the explanation and message", value=llm_available(), help="Needs a free API key in .env. Without it, clear template text is used instead.")

@st.cache_data(show_spinner=False)
def get_explain(c, llm): return explain_customer(c, use_llm=llm)
@st.cache_data(show_spinner=False)
def get_rec(c, llm): return recommend(c, use_llm=llm)

r = m[m.customer_id == cid].iloc[0]; ex = get_explain(cid, use_llm); p = ex["profile"]
first = load_table("customers").set_index("customer_id").loc[cid]
tier_col = ui.RISK_COLORS[ex["risk_tier"]]

with ui.card():
    h1, h2 = st.columns([2.2, 1])
    with h1:
        st.markdown(f"### {first.first_name} {first.last_name} &nbsp; <span style='color:#9A9AAA;font-size:.9rem'>{cid}</span>", unsafe_allow_html=True)
        st.markdown(ui.badge(ex["risk_tier"] + " risk", tier_col) + " &nbsp; " + ui.badge(p["status"], ui.GREEN if r.active else ui.GREY) + " &nbsp; " + ui.badge(p["plan"] + " plan", ui.PLAN_COLORS[p["plan"]]) + " &nbsp; " + ui.badge(r.segment_name, ui.BLUE), unsafe_allow_html=True)
        st.write("")
        ui.kpi_row([dict(label="Country", value=r.country, sub=f"{r.preferred_language} · age {int(r.age)}"), dict(label="Customer for", value=f"{p['tenure_years']} yrs", sub=f"via {r.acquisition_channel}"),
                    dict(label="Plan price", value=ui.money(r.monthly_price, 2), sub="auto-renew " + ("on" if r.auto_renew else "off")), dict(label="Revenue to date", value=ui.money(r.clv_actual), sub=f"{r.value_tier} value tier")])
    with h2:
        fig = go.Figure(go.Indicator(mode="gauge+number", value=ex["churn_probability"] * 100, number=dict(suffix="%", font=dict(size=34, color="#fff")),
                                     title=dict(text="Estimated 9-month churn probability", font=dict(size=12, color="#9A9AAA")),
                                     gauge=dict(axis=dict(range=[0, 60], tickfont=dict(size=10)), bar=dict(color=tier_col, thickness=.28), bgcolor="#1b1b26", borderwidth=0,
                                                steps=[dict(range=[0, 20], color="#17261e"), dict(range=[20, 30], color="#2b2616"), dict(range=[30, 60], color="#2d1417")],
                                                threshold=dict(line=dict(color="#fff", width=2), value=24.4))))
        ui.plot(ui.style_fig(fig, 220, legend=False, margin=(20, 20, 30, 0)))
        st.caption(f"White line = average customer (24%). Riskier than {ex['percentile_vs_active']:.0%} of active customers." if r.active else "Churned customer: score computed from data up to their exit.")

a, b = st.columns([1.1, 1])
with a, ui.card():
    ui.section("Why this risk level", "factors vs the average customer")
    st.markdown(ex["narrative"])
    dr = (ex["drivers_up"] + ex["drivers_down"])[::-1]
    if dr:
        fig = go.Figure(go.Bar(x=[d["effect"] for d in dr], y=[d["label"] + f" ({d['customer_value']})" for d in dr], orientation="h", marker_color=[ui.RED if d["effect"] > 0 else ui.GREEN for d in dr],
                               hovertemplate="%{y}<br>effect %{x:+.2f}<extra></extra>"))
        fig.update_xaxes(title="← lowers risk · raises risk →", zeroline=True); ui.plot(ui.style_fig(fig, 300, legend=False, margin=(0, 10, 0, 0)))
    st.caption(ex["caveat"])
with b, ui.card():
    ui.section("Viewing behaviour", "watch minutes per month (data covers Jul 2025 - Jun 2026)")
    w = data.customer_monthly_watch(cid)
    fig = go.Figure(go.Bar(x=w.month, y=w.minutes, marker_color=ui.BLUE, hovertemplate="%{x|%b %Y}<br>%{y:.0f} min<extra></extra>")); fig.update_xaxes(tickformat="%b %y", title=None); fig.update_yaxes(title=None)
    ui.plot(ui.style_fig(fig, 215, legend=False, margin=(0, 0, 0, 0)))
    ui.kpi_row([dict(label="Sessions (90d)", value=f"{int(r.sessions_90d)}", sub=f"{r.days_since_last_activity:.0f} days since last"), dict(label="Engagement", value=f"{r.engagement_score:.0f}/100", sub="90-day score")])

a, b = st.columns(2)
with a, ui.card():
    ui.section("Recent payments", f"{int(r.failed_payment_count)} failed in total")
    pay = data.customer_payments(cid); pay["payment_date"] = pay.payment_date.dt.date
    ui.table(pay.rename(columns=lambda c: c.replace("_", " ").title()), height=250)
with b, ui.card():
    ui.section("Support history", f"{int(r.support_ticket_count)} tickets")
    tk = data.customer_tickets(cid); tk["ticket_date"] = tk.ticket_date.dt.date
    if tk.empty: st.info("No support tickets for this customer.")
    else: ui.table(tk.rename(columns=lambda c: c.replace("_", " ").title()), height=250)

ui.section("Recommended action", "rules decide the action; AI only writes the message")
rec = get_rec(cid, use_llm)
if "error" in rec:
    ui.callout(rec["error"], "warn")
else:
    with ui.card():
        k1, k2, k3, k4 = st.columns(4)
        k1.markdown(ui.kpi_html("Priority", rec["priority"].split(" - ")[0], rec["priority"].split(" - ")[1].capitalize(), tone="accent" if rec["priority"].startswith(("P1", "P2")) else ""), unsafe_allow_html=True)
        k2.markdown(ui.kpi_html("Channel", rec["channel"], rec["sla"]), unsafe_allow_html=True)
        k3.markdown(ui.kpi_html("Offer", rec["offer"].split(" (")[0], f"cost ≈ {ui.money(rec['offer_cost'], 2)}"), unsafe_allow_html=True)
        k4.markdown(ui.kpi_html("Expected net value", ui.money(rec["net_value"], 2), f"benefit {ui.money(rec['expected_benefit'], 2)}", tone="good" if rec["net_value"] > 0 else "warn"), unsafe_allow_html=True)
        st.markdown(f"**Action:** {rec['action']}. {rec['segment_note']}")
        if rec["tactics"]: st.markdown("**Also address:**\n" + "\n".join(f"- {t}" for t in rec["tactics"]))
        if rec["cost_downgraded"]: st.warning("The standard offer would cost more than it is expected to earn for this customer, so a no-discount nudge is recommended.")
        st.caption(rec["assumptions"])
        st.text_area("Draft message" + (" (written by AI)" if rec["used_llm"] else " (template)"), rec["message"], height=210)
