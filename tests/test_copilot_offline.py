"""Offline tests: a fake LLM replaces Groq so everything else (validator, MySQL, RAG, explainer, recommender, RCA, report, router) is verified for real.
Run:  pytest tests -q      (needs MySQL running with data loaded for the SQL tests; they skip themselves otherwise)"""
import pandas as pd
import pytest
from src.llm import llm_client
from src.llm.schema_context import EXAMPLES
from src.llm.sql_validator import validate_sql
from src.database.connection import db_available, run_readonly
from src.llm.router import detect_intent, Copilot
from src.llm import rag, root_cause_agent
from src.llm.explainer import explain_customer
from src.llm.recommender import recommend
from src.llm.report_generator import generate_report
from src.utils.data_loader import master

needs_db = pytest.mark.skipif(not db_available(), reason="MySQL not available")
QA = dict(EXAMPLES)


@pytest.fixture(autouse=True)
def fake_llm():
    calls = {"n": 0, "script": []}

    def fake(messages, **kw):
        calls["n"] += 1
        if calls["script"]:
            return calls["script"].pop(0)
        sys_msg = messages[0]["content"] if messages and messages[0]["role"] == "system" else ""
        user = messages[-1]["content"]
        if "CANNOT_ANSWER" in sys_msg:
            q = user.split("\n")[0]
            return f"```sql\n{QA[q]}\n```" if q in QA else "CANNOT_ANSWER: not a data question"
        return "MOCK NARRATIVE"
    llm_client.set_llm_override(fake)
    yield calls
    llm_client.set_llm_override(None)


@needs_db
@pytest.mark.parametrize("q,sql", EXAMPLES)
def test_few_shot_examples_are_valid_and_run(q, sql):
    v = validate_sql(sql); assert v.ok, v.reason
    assert len(run_readonly(v.sql)) > 0


@needs_db
def test_text_to_sql_happy_path():
    r = Copilot().chat("How many active customers are there in each country?")
    assert r["capability"] == "sql" and not r["error"] and len(r["data"]) == 20 and r["answer"] == "MOCK NARRATIVE"


@needs_db
def test_self_repair_after_sql_error(fake_llm):
    fake_llm["script"] = ["```sql\nSELECT nonexistent_col FROM customers\n```", f"```sql\n{EXAMPLES[3][1]}\n```"]
    r = Copilot().sql.ask("top reasons")
    assert r["attempts"] == 2 and not r["error"] and len(r["data"]) == 5


@needs_db
def test_dangerous_sql_is_rejected_then_repaired(fake_llm):
    fake_llm["script"] = ["```sql\nDROP TABLE customers\n```", f"```sql\n{EXAMPLES[0][1]}\n```"]
    r = Copilot().sql.ask("anything")
    assert r["attempts"] == 2 and len(r["data"]) == 20
    assert run_readonly("SELECT COUNT(*) AS n FROM customers").n.iloc[0] == 8000


@needs_db
def test_gives_up_gracefully(fake_llm):
    fake_llm["script"] = ["```sql\nDROP TABLE customers\n```"] * 3
    r = Copilot().sql.ask("anything")
    assert r["data"].empty and "wasn't able" in r["answer"]


def test_cannot_answer():
    r = Copilot().sql.ask("What is the weather today?")
    assert "can't answer" in r["answer"]


@pytest.mark.parametrize("msg,intent", [
    ("Explain the churn risk of CUST000123", "explain"), ("what should we do to retain CUST000123", "recommend"),
    ("Why is churn higher in South Korea?", "root_cause"), ("What are customers saying about billing?", "rag"),
    ("Generate the executive report", "report"), ("How many active customers by country", "sql"), ("Top 5 churn reasons", "sql"),
    ("what is the root cause of churn on the basic plan", "root_cause"), ("complaints about streaming quality", "rag")])
def test_router(msg, intent):
    assert detect_intent(msg) == intent


def test_rag_and_filters():
    r = rag.ask("What are customers complaining about in South Korea in the last 6 months?")
    assert r["filters"] == {"country": "South Korea", "days": 180} and len(r["themes"]) > 0
    assert (rag.search("app crashes on my phone", k=1).iloc[0].subcategory == "App crashing")


def test_explain_and_recommend_high_risk():
    m = master(); cid = m[m.active].sort_values("churn_risk_score", ascending=False).customer_id.iloc[0]
    e = explain_customer(cid); assert e["risk_tier"] == "High" and e["drivers_up"] and 0 < e["churn_probability"] < 1
    r = recommend(cid); assert r["priority"].startswith("P") and r["message"] == "MOCK NARRATIVE" and r["used_llm"]
    assert "Subject:" in recommend(cid, use_llm=False)["message"]      # deterministic template when no LLM
    assert r["offer_cost"] <= r["expected_benefit"] or r["offer_cost"] == 0


def test_recommend_churned_customer_is_refused():
    m = master(); assert "already churned" in recommend(m[~m.active].customer_id.iloc[0])["error"]


def test_unknown_customer():
    assert "not found" in explain_customer("CUST999999")["error"]


def test_root_cause_detects_group_and_is_statistically_careful():
    r = root_cause_agent.analyse("Why is churn higher in South Korea?")
    assert r["group"] == ("country", "South Korea") and r["investigation"]["n_tests"] > 5
    assert all(f["p"] < 0.05 for f in r["investigation"]["findings"])


def test_report_generates(tmp_path):
    r = generate_report(save=False); assert "## Key metrics" in r["markdown"] and "Executive" in r["markdown"]
