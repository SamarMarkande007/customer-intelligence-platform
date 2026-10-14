import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import pandas as pd
import streamlit as st
from app import ui, data
from src.llm.llm_client import llm_available
from src.llm.report_generator import generate_report
from src.utils.config import ROOT

ui.setup("Reports & Models")
ui.page_header("Reports & Models", "Generate the executive report, read the model cards, and browse the SQL answers", "Customers & AI")

t1, t2, t3, t4 = st.tabs(["Executive report", "Model cards", "SQL answers", "Data notes"])
with t1:
    c1, c2 = st.columns([1, 3])
    use_llm = c1.toggle("AI-written summary", value=llm_available(), help="Numbers and tables are always computed in code. AI only writes the summary and actions.")
    if c1.button("Generate report", type="primary"):
        with st.spinner("Computing metrics and writing the report…"):
            st.session_state.report = generate_report(use_llm=use_llm, save=True)
    rep = st.session_state.get("report")
    if rep:
        c2.success("Report ready" + (" · AI summary" if rep["used_llm"] else " · template summary") + (f" · saved to {Path(rep['path']).relative_to(ROOT)}" if rep["path"] else ""))
        c2.download_button("⬇ Download Markdown", rep["markdown"].encode(), "executive_report.md", "text/markdown")
        with ui.card(): st.markdown(rep["markdown"])
    else:
        c2.info("Click **Generate report**. Every number is computed from the data; the language model never invents figures.")

with t2:
    ch, clv = data.metrics_json("churn_model_metrics.json"), data.metrics_json("clv_model_metrics.json")
    a, b, c = st.columns(3)
    with a, ui.card():
        st.markdown("#### Churn prediction"); st.caption("Classification · notebook 04")
        if ch:
            t = ch["test_threshold_0.5"]; o = ch["test_operating_threshold"]
            st.markdown(f"**{ch['final_model']}**")
            ui.kpi_row([dict(label="ROC-AUC", value=f"{t['roc_auc']:.3f}", sub="held-out test"), dict(label="PR-AUC", value=f"{t['pr_auc']:.3f}", sub="baseline 0.24")])
            st.markdown(f"- Recall **{t['recall']:.2f}** / precision **{t['precision']:.2f}** at 0.50\n- Best business threshold **{o['threshold']:.2f}**: recall {o['recall']:.2f}, precision {o['precision']:.2f}\n- Top-decile lift **1.7×**\n- Top drivers: " + ", ".join(ch["top_features"][:4]))
        st.caption("Leakage-safe: features as of 30 Sep 2025, outcome = churn in the next 9 months. A leaky build reaches 0.71 and is not used.")
    with b, ui.card():
        st.markdown("#### Segmentation"); st.caption("K-Means · notebook 05")
        st.markdown("**K = 4**"); ui.kpi_row([dict(label="Silhouette", value="0.19", sub="weak separation"), dict(label="Stability (ARI)", value="0.999", sub="5 restarts")])
        st.markdown("- Dormant Accounts · Engaged & Well-Supported · High-Value Engaged · Budget Basic\n- Driven by activity vs dormancy, plan price, support experience\n- Churn 17% to 29% across segments")
        st.caption("Churn and CLV were not used to build clusters; they validate them.")
    with c, ui.card():
        st.markdown("#### Customer lifetime value"); st.caption("Regression · notebook 06")
        if clv:
            t = clv["test"]; st.markdown(f"**{clv['final_model']}**")
            ui.kpi_row([dict(label="R²", value=f"{t['test_R2']:.3f}", sub="held-out test"), dict(label="MAE", value=f"${t['test_MAE']:.2f}", sub=f"RMSE ${t['test_RMSE']:.2f}")])
            st.markdown(f"- Simple formula `min(tenure,15)×price` already scores R² {clv['baseline']['test_R2']:.2f}\n- Behaviour-only model: R² {clv['behaviour_only_test_r2']:.2f}")
        st.caption("Payments table holds ≤15 payments per customer, so CLV is trailing revenue, close to a billing identity. High R² is not deep insight.")
    ui.callout("<b>Honest summary:</b> the churn signal in this dataset is weak and noisy (AUC ≈ 0.62), segments are stable but overlapping, and CLV is nearly determined by plan and tenure. The value of the system is prioritisation and decision support, not individual-level certainty.", "info")

with t3:
    d = ROOT / "reports" / "sql_results"
    files = sorted(d.glob("Q*.csv")) if d.exists() else []
    if not files:
        st.info("Run `python database/run_queries.py` once to save the result of every SQL question here.")
    else:
        q = st.selectbox("Question", [f.stem for f in files], format_func=lambda s: s)
        qs = (ROOT / "database" / "sql_business_questions.sql").read_text(encoding="utf-8")
        import re
        m = re.search(rf"-- ===== {q}:([^\n]*)\n(.*?)(?=\n-- =====|\n-- ####|\Z)", qs, re.S)
        if m:
            st.markdown(f"**{q}:{m.group(1)}**")
            with st.expander("SQL"): st.code(m.group(2).strip(), language="sql")
        df = pd.read_csv(files[[f.stem for f in files].index(q)]); ui.table(df, height=380); st.caption(f"{len(df)} rows shown (saved results are capped at 2,000 rows).")

with t4:
    st.markdown("""
- **"Today" = 30 Jun 2026**, the latest date in the data. Payments stop on 31 May 2026.
- **Churn dates start 3 Oct 2025**, so earlier months show no churn by construction.
- **Payments table keeps at most 15 payments per customer**: lifetime value is trailing revenue.
- **Viewing history** covers Jul 2025 - Jun 2026 only.
- **subscriptions.monthly_price never changes within a customer**; a plan switch is the only "price change" signal.
- **Churn probabilities are calibrated** (Platt scaling on the held-out test set): the model's raw scores average ~0.5 because of class weighting, so raw scores are used for tiers and calibrated values for money.
- **Cleaning log:** every fix (duplicates, countries, devices, outliers, payment amounts, sentiment labels) is in `data/processed/data_quality_log.csv`.
""")
