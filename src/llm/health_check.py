"""
Run this FIRST:   python -m src.llm.health_check
Checks, in order: .env settings -> MySQL connection -> SQL validator -> LLM key & a live call -> one end-to-end text-to-SQL question.
Each step prints PASS / FAIL with the fix.
"""
import os, sys, time
from src.utils.config import DB_HOST, DB_NAME, DB_USER, ROOT


def step(name, fn):
    t = time.time()
    try:
        msg = fn(); print(f"[PASS] {name}: {msg}  ({time.time() - t:.1f}s)"); return True
    except Exception as e:
        print(f"[FAIL] {name}: {e}"); return False


def main():
    from src.llm.llm_client import get_client, PROVIDERS
    from src.llm.sql_validator import validate_sql
    from src.database.connection import db_available, run_readonly
    ok = True
    prov = os.getenv("LLM_PROVIDER", "groq")
    ok &= step("env file", lambda: f".env found, provider={prov}" if (ROOT / ".env").exists() else (_ for _ in ()).throw(RuntimeError("no .env file in project root (copy .env.example)")))
    ok &= step("api key", lambda: "key present" if get_client().is_configured() else (_ for _ in ()).throw(RuntimeError(f"{PROVIDERS[prov]['key_env']} is empty in .env (free key: console.groq.com)")))
    ok &= step("mysql", lambda: f"connected to {DB_NAME} as {DB_USER}@{DB_HOST}" if db_available() else (_ for _ in ()).throw(RuntimeError("cannot connect: is MySQL running, are DB_USER/DB_PASSWORD in .env right, did you run load_data.py?")))
    ok &= step("sql validator", lambda: "blocks DROP, allows SELECT" if (not validate_sql("DROP TABLE customers").ok and validate_sql("SELECT 1 FROM customers").ok) else (_ for _ in ()).throw(RuntimeError("validator misbehaving")))
    ok &= step("readonly query", lambda: f"{len(run_readonly('SELECT COUNT(*) AS n FROM customers'))} row, customers={run_readonly('SELECT COUNT(*) AS n FROM customers').n.iloc[0]}")
    def live():
        c = get_client(); r = c.chat("Reply with exactly: OK", max_tokens=20, temperature=0)
        return f"model={c.model} replied {r!r}"
    ok &= step("llm live call", live)
    def e2e():
        from src.llm.text_to_sql import TextToSQL
        r = TextToSQL().ask("How many active customers are there in each country? Top 3 only.")
        if r["error"] and r["data"].empty: raise RuntimeError(r["error"] or r["answer"])
        return f"{len(r['data'])} rows | answer: {r['answer'][:110]}"
    ok &= step("end-to-end text-to-SQL", e2e)
    print("\nAll good. Start the app." if ok else "\nFix the FAIL lines above (top to bottom), then run this again.")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
