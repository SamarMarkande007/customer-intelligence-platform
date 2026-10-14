"""MySQL access for the copilot: one cached engine + a read-only, time-limited query runner."""
from __future__ import annotations
from functools import lru_cache
import pandas as pd
from sqlalchemy import create_engine
from src.utils.config import db_url


@lru_cache(maxsize=1)
def get_engine():
    return create_engine(db_url(), pool_pre_ping=True, pool_recycle=1800)


def db_available() -> bool:
    try:
        with get_engine().connect() as c:
            c.connection.cursor().execute("SELECT 1")
        return True
    except Exception:
        return False


def run_readonly(sql: str, timeout_s: int = 15) -> pd.DataFrame:
    """Run an already-validated SELECT. Uses a raw DBAPI cursor (so '%Y-%m' in DATE_FORMAT is not treated as a format token),
    a read-only transaction, and a server-side time limit (MySQL: max_execution_time ms, MariaDB: max_statement_time s)."""
    with get_engine().connect() as conn:
        cur = conn.connection.cursor()
        for stmt in (f"SET SESSION max_execution_time = {timeout_s * 1000}", f"SET SESSION max_statement_time = {timeout_s}",
                     "SET SESSION TRANSACTION READ ONLY"):
            try:
                cur.execute(stmt)
            except Exception:
                pass                                   # the other server flavour does not know this variable
        cur.execute(sql)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        cur.close()
    return pd.DataFrame(rows, columns=cols)
