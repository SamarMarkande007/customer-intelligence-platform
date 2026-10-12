"""
Run every query in sql_business_questions.sql against MySQL, time it, and save each result to
reports/sql_results/<question>.csv (first 2,000 rows).  Doubles as a smoke test: it exits non-zero if any query fails.

Usage (project root):   python database/run_queries.py            # all queries
                        python database/run_queries.py Q05 Q20    # only some
"""
import re, sys, time
from pathlib import Path
import pandas as pd
from sqlalchemy import create_engine, event

sys.path.append(str(Path(__file__).resolve().parents[1]))
from src.utils.config import ROOT, db_url

SQL_FILE = ROOT / "database" / "sql_business_questions.sql"
OUT_DIR = ROOT / "reports" / "sql_results"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Same strict defaults as MySQL 8 (ONLY_FULL_GROUP_BY etc.) so a query that passes here passes in Workbench
STRICT = "ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION"


def load_queries():
    text = SQL_FILE.read_text(encoding="utf-8")
    parts = re.split(r"^-- ===== (Q\d+[a-z]?):[^\n]*\n", text, flags=re.M)
    queries = {}
    for i in range(1, len(parts), 2):
        body = "\n".join(l for l in parts[i + 1].splitlines()
                         if l.strip() and not l.strip().startswith("--"))
        queries[parts[i]] = body.strip().rstrip(";")
    return queries


def main():
    wanted = {a.upper() for a in sys.argv[1:]}
    engine = create_engine(db_url())

    @event.listens_for(engine, "connect")
    def _set_mode(dbapi_conn, _):
        cur = dbapi_conn.cursor(); cur.execute(f"SET SESSION sql_mode = '{STRICT}'"); cur.close()

    queries = load_queries()
    failed = []
    print(f"{'query':6s} {'rows':>8s} {'sec':>6s}")
    with engine.connect() as conn:
        for name, sql in queries.items():
            if wanted and name.upper() not in wanted and name[:3].upper() not in wanted:
                continue
            t0 = time.time()
            try:
                cur = conn.connection.cursor()          # raw DBAPI cursor: no %-formatting of DATE_FORMAT('%Y-%m')
                cur.execute(sql)
                df = pd.DataFrame(cur.fetchall(), columns=[d[0] for d in cur.description])
                cur.close()
                df.head(2000).to_csv(OUT_DIR / f"{name}.csv", index=False)
                print(f"{name:6s} {len(df):8,d} {time.time()-t0:6.2f}")
            except Exception as e:
                failed.append(name)
                print(f"{name:6s} FAILED: {str(e)[:200]}")
    print(f"\n{len(queries)-len(failed) if not wanted else 'selected'} OK, {len(failed)} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
