import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import pandas as pd, plotly.express as px
import streamlit as st
from app import ui
from src.llm.llm_client import llm_available, get_client
from src.llm.router import Copilot, CAPABILITIES, EXAMPLES
from src.database.connection import db_available

ui.setup("AI Copilot")
ui.page_header("AI Copilot", "Ask in plain English: data questions, customer voice, risk explanations, root causes, reports and retention actions", "Customers & AI")

@st.cache_resource
def get_copilot(): return Copilot()
@st.cache_data(ttl=60, show_spinner=False)
def status(): return llm_available(), db_available()
llm_ok, db_ok = status(); copilot = get_copilot()
s1, s2, s3 = st.columns(3)
s1.markdown(ui.kpi_html("Language model", f"{get_client().provider.title()}" if llm_ok else "Offline", get_client().model if llm_ok else "add a free key to .env", tone="good" if llm_ok else "warn"), unsafe_allow_html=True)
s2.markdown(ui.kpi_html("MySQL (text-to-SQL)", "Connected" if db_ok else "Not connected", "read-only, validated queries" if db_ok else "start MySQL / check .env", tone="good" if db_ok else "warn"), unsafe_allow_html=True)
s3.markdown(ui.kpi_html("Capabilities", "6", " · ".join(["SQL", "RAG", "Explain", "Report", "Root cause", "Recommend"])), unsafe_allow_html=True)
if not llm_ok:
    ui.callout("<b>Offline mode.</b> Customer explanations, recommendations, root-cause evidence, ticket themes and reports still work with template text. <b>Text-to-SQL and AI-written narratives need a free API key</b> (GROQ_API_KEY in .env, free at console.groq.com).", "warn")

if "msgs" not in st.session_state:
    st.session_state.msgs = []

def render(res: dict):
    cap = res.get("capability_name", "")
    st.markdown(f'<div class="msg-meta">{ui.badge(cap, ui.RED)}</div>', unsafe_allow_html=True)
    st.markdown(res["answer"])
    if res.get("sql"):
        with st.expander("SQL used"): st.code(res["sql"], language="sql")
    df = res.get("data")
    if isinstance(df, pd.DataFrame) and not df.empty:
        ui.table(df.head(200))
        num = df.select_dtypes("number").columns.tolist(); oth = [c for c in df.columns if c not in num]
        if num and oth and 2 <= len(df) <= 40:
            x, y = oth[0], num[0]
            fig = px.line(df, x=x, y=y, markers=True) if any(k in x.lower() for k in ("month", "date", "year", "week")) else px.bar(df, x=x, y=y)
            fig.update_traces(marker_color=ui.RED); fig.update_traces(line_color=ui.RED, selector=dict(mode="lines+markers"))
            ui.plot(ui.style_fig(fig, 280, legend=False), key=f"c{abs(hash(res['message']))}{len(st.session_state.msgs)}")
    th = res.get("themes")
    if isinstance(th, pd.DataFrame) and not th.empty:
        with st.expander("Evidence: matched themes"):
            ui.table(th[["doc_id", "source", "category", "subcategory", "n", "churn_rate", "extra", "text"]].rename(columns={"doc_id": "ID", "churn_rate": "churn among authors"}),
                     column_config={"churn among authors": st.column_config.NumberColumn(format="percent")})
    det = res.get("detail")
    if res.get("capability") == "report" and det:
        st.download_button("⬇ Download report (Markdown)", res["answer"].encode(), "executive_report.md", "text/markdown", key=f"d{len(st.session_state.msgs)}")
    if res.get("error") and res.get("capability") == "sql":
        st.caption("⚠ " + str(res["error"]))

st.markdown("**Try one:**")
cols = st.columns(3); clicked = None
for i, ex in enumerate(EXAMPLES):
    if cols[i % 3].button(ex, key=f"ex{i}"):
        clicked = ex
if st.session_state.msgs and st.button("🗑 Clear conversation"):
    st.session_state.msgs = []; st.rerun()

for msg in st.session_state.msgs:
    with st.chat_message(msg["role"], avatar="🧑‍💼" if msg["role"] == "user" else "🤖"):
        render(msg["res"]) if msg["role"] == "assistant" else st.markdown(msg["content"])

prompt = st.chat_input("Ask anything about customers, churn, revenue, complaints…") or clicked
if prompt:
    st.session_state.msgs.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="🧑‍💼"): st.markdown(prompt)
    hist = []
    for mm in st.session_state.msgs[:-1][-4:]:
        if mm["role"] == "user": hist.append({"role": "user", "content": mm["content"]})
        elif mm["res"].get("sql"): hist.append({"role": "assistant", "content": f"```sql\n{mm['res']['sql']}\n```"})
    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("Thinking…"):
            try:
                res = copilot.chat(prompt, history=hist if hist and hist[-1]["role"] == "assistant" else None)
            except Exception as e:                      # never let one bad answer crash the page
                res = {"capability": "error", "capability_name": "Error", "message": prompt, "answer": f"Sorry, something went wrong while answering: `{type(e).__name__}: {str(e)[:200]}`. Try rephrasing the question."}
        st.session_state.msgs.append({"role": "assistant", "res": res}); render(res)
