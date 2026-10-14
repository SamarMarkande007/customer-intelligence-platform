"""Routes a chat message to one of the six capabilities. Rule-based first (free, instant, predictable); no LLM call is spent on routing."""
from __future__ import annotations
import re
from src.llm import rag, root_cause_agent
from src.llm.explainer import explain_customer
from src.llm.recommender import recommend
from src.llm.report_generator import generate_report
from src.llm.text_to_sql import TextToSQL

CUSTOMER_ID = re.compile(r"\bCUST\d{6}\b", re.I)
CAPABILITIES = {"sql": "Text-to-SQL", "rag": "Ticket & feedback search (RAG)", "explain": "Churn prediction explainer", "report": "Report generator",
                "root_cause": "Root-cause analysis", "recommend": "Retention recommender"}
EXAMPLES = ["How many active customers do we have in each country?", "What are customers saying about billing?", "Explain the churn risk of CUST000123",
            "Why is churn higher in South Korea?", "What should we do to retain CUST000123?", "Generate the executive report"]


def detect_intent(message: str) -> str:
    q = message.lower()
    if CUSTOMER_ID.search(message):
        return "recommend" if re.search(r"recommend|offer|retain|retention|what should|action|save|reach out|next best|contact", q) else "explain"
    if re.search(r"\b(report|executive summary|board summary|weekly summary|monthly summary|business summary)\b", q):
        return "report"
    if re.search(r"root cause|what.s (causing|driving)|drivers? of|\bwhy\b.*(churn|cancel|leav|retention|higher|lower|drop)|(churn|cancel).*\bwhy\b", q):
        return "root_cause"
    if re.search(r"complain|feedback|reviews?\b|saying|say about|themes|voice of|pain points|what are customers|what do customers|sentiment|tickets? (about|mention)", q):
        return "rag"
    return "sql"


class Copilot:
    def __init__(self):
        self.sql = TextToSQL(); self.history: list[dict] = []

    def chat(self, message: str, history: list[dict] | None = None) -> dict:
        intent = detect_intent(message); out = {"capability": intent, "capability_name": CAPABILITIES[intent], "message": message}
        if intent == "sql":
            r = self.sql.ask(message, history=history); out.update(answer=r["answer"], sql=r["sql"], data=r["data"], error=r["error"], attempts=r["attempts"])
        elif intent == "rag":
            r = rag.ask(message); out.update(answer=r["answer"], themes=r["themes"], filters=r["filters"])
        elif intent == "explain":
            cid = CUSTOMER_ID.search(message).group(0).upper(); r = explain_customer(cid)
            out.update(answer=r.get("error") or r["narrative"], detail=r)
        elif intent == "recommend":
            cid = CUSTOMER_ID.search(message).group(0).upper(); r = recommend(cid)
            if "error" in r:
                out.update(answer=r["error"])
            else:
                out.update(answer=(f"**{r['priority']}** for {cid}: {r['action']}. Offer: {r['offer']}. Channel: {r['channel']} ({r['sla']}). "
                                   f"Expected net value ${r['net_value']:.2f}.\n\n" + ("Also: " + "; ".join(r["tactics"]) + "\n\n" if r["tactics"] else "") + "Draft message:\n\n" + r["message"]), detail=r)
        elif intent == "root_cause":
            r = root_cause_agent.analyse(message); out.update(answer=r["answer"], detail=r)
        elif intent == "report":
            r = generate_report(); out.update(answer=r["markdown"], detail={"path": r["path"], "used_llm": r["used_llm"]})
        return out
