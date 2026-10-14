"""Capability 1: natural-language question -> validated MySQL -> result -> plain-English answer (with self-repair)."""
from __future__ import annotations
import re
import pandas as pd
from src.llm.llm_client import get_client, LLMError
from src.llm.schema_context import SQL_SYSTEM
from src.llm.sql_validator import validate_sql
from src.database.connection import run_readonly

ANSWER_SYSTEM = ("You are a data analyst answering a business question from a SQL result. Use ONLY the numbers in the result; never invent "
                 "or estimate values. Be concise (2-5 sentences), lead with the direct answer, include the key figures, and mention an "
                 "assumption only if it matters (for example: 'as of 2026-06-30', 'active = not churned'). Do not mention SQL or tables.")


def extract_sql(text: str) -> str:
    m = re.search(r"```(?:sql)?\s*(.*?)```", text, re.S | re.I)
    return (m.group(1) if m else text).strip()


class TextToSQL:
    def __init__(self, max_attempts: int = 3):
        self.max_attempts = max_attempts

    def generate_sql(self, question: str, history: list[dict] | None = None, feedback: str | None = None) -> str:
        msgs = list(history or [])[-4:]
        user = question if not feedback else f"{question}\n\nYour previous query failed: {feedback}\nWrite a corrected query."
        msgs.append({"role": "user", "content": user})
        return get_client().chat(msgs, system=SQL_SYSTEM, temperature=0.0, max_tokens=700)

    def ask(self, question: str, history: list[dict] | None = None) -> dict:
        out = {"question": question, "sql": "", "data": pd.DataFrame(), "answer": "", "error": "", "attempts": 0, "notes": []}
        feedback = None
        for attempt in range(1, self.max_attempts + 1):
            out["attempts"] = attempt
            try:
                raw = self.generate_sql(question, history, feedback)
            except LLMError as e:
                out["error"] = str(e); out["answer"] = f"I couldn't reach the language model: {e}"; return out
            if raw.strip().upper().startswith("CANNOT_ANSWER"):
                out["answer"] = "I can't answer that from the database: " + raw.split(":", 1)[-1].strip()
                return out
            sql = extract_sql(raw)
            v = validate_sql(sql)
            if not v.ok:
                feedback = f"validator rejected it: {v.reason}"; out["sql"] = sql; out["error"] = feedback
                continue
            out["sql"], out["notes"] = v.sql, v.notes
            try:
                df = run_readonly(v.sql)
            except Exception as e:
                feedback = f"MySQL error: {str(e)[:300]}"; out["error"] = feedback
                continue
            out["data"], out["error"] = df, ""
            out["answer"] = self._summarise(question, df)
            return out
        out["answer"] = ("I wasn't able to produce a working query for that question after "
                         f"{self.max_attempts} tries. Last problem: {out['error']}. Try rephrasing, or name the table or metric you mean.")
        return out

    def _summarise(self, question: str, df: pd.DataFrame) -> str:
        if df.empty:
            return "The query ran but returned no rows, so there is nothing matching that question in the data."
        shown = df.head(25)
        prompt = f"Question: {question}\n\nSQL result ({len(df)} rows{', first 25 shown' if len(df) > 25 else ''}):\n{shown.to_csv(index=False)}"
        try:
            return get_client().chat(prompt, system=ANSWER_SYSTEM, temperature=0.2, max_tokens=300)
        except LLMError:
            return f"The query returned {len(df)} row(s). See the table below."
