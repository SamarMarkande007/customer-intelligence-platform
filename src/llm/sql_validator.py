"""
SQL safety layer for LLM-generated queries (defence in depth).

Accepts ONLY: a single SELECT / WITH...SELECT statement that touches the nine project tables, with a row cap.
Rejects: multiple statements, any write/DDL/admin keyword, INTO OUTFILE, comments that can hide code, user variables,
system schemas, sleep()/benchmark() style functions.

IMPORTANT: this is one of three layers. The others are (1) read-only + time-limited execution in connection.run_readonly and
(2) a dedicated read-only MySQL user. Create it with:
    CREATE USER 'copilot_ro'@'localhost' IDENTIFIED BY 'choose_a_password';
    GRANT SELECT ON netflix_ci.* TO 'copilot_ro'@'localhost';
and put DB_USER=copilot_ro / DB_PASSWORD=... in .env when you run the copilot.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field

ALLOWED_TABLES = {"customers", "subscription_plans", "subscriptions", "content", "viewing_activity",
                  "payments", "support_tickets", "customer_feedback", "churn_labels"}
DEFAULT_LIMIT, MAX_ROWS = 200, 1000

_FORBIDDEN_WORDS = {"insert", "update", "delete", "drop", "alter", "truncate", "create", "grant", "revoke", "call", "exec", "execute",
                    "handler", "load", "outfile", "dumpfile", "into", "lock", "unlock", "rename", "set", "use", "show", "describe",
                    "explain", "optimize", "analyze", "flush", "kill", "shutdown", "prepare", "deallocate"}
_FORBIDDEN_FUNCS = {"sleep", "benchmark", "load_file", "get_lock", "release_lock", "master_pos_wait", "sys_exec", "user", "current_user",
                    "database", "version", "system_user", "session_user", "connection_id"}
_SYSTEM_SCHEMAS = ("information_schema", "mysql", "performance_schema", "sys")


@dataclass
class ValidationResult:
    ok: bool
    sql: str = ""
    reason: str = ""
    tables: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _strip_literals(sql: str) -> str:
    sql = re.sub(r"'(?:[^'\\]|\\.|'')*'", "''", sql)
    sql = re.sub(r'"(?:[^"\\]|\\.|"")*"', '""', sql)
    return sql


def validate_sql(raw: str, max_rows: int = MAX_ROWS) -> ValidationResult:
    if not raw or not raw.strip():
        return ValidationResult(False, reason="Empty query.")
    sql = raw.strip()
    if "/*!" in sql or "/*+" in sql:
        return ValidationResult(False, reason="MySQL executable comments / hints are not allowed.")
    if "@" in _strip_literals(sql):
        return ValidationResult(False, reason="User or system variables (@, @@) are not allowed.")

    scan = _strip_literals(sql)
    scan = re.sub(r"/\*.*?\*/", " ", scan, flags=re.S)
    scan = re.sub(r"(--[ \t].*?$|--$|#.*?$)", " ", scan, flags=re.M)
    scan = scan.strip()
    # drop ONE trailing semicolon; any other semicolon means multiple statements
    scan = scan.rstrip(";").strip()
    if ";" in scan:
        return ValidationResult(False, reason="Only a single statement is allowed (found ';').")

    first = re.match(r"\(?\s*(\w+)", scan)
    if not first or first.group(1).lower() not in ("select", "with"):
        return ValidationResult(False, reason="Only SELECT queries (optionally starting with WITH) are allowed.")

    words = set(re.findall(r"[a-z_]+", scan.lower()))
    bad = sorted(words & _FORBIDDEN_WORDS)
    if bad:
        return ValidationResult(False, reason=f"Forbidden keyword: {', '.join(bad)}.")
    for fn in _FORBIDDEN_FUNCS:
        if re.search(rf"\b{fn}\s*\(", scan, re.I):
            return ValidationResult(False, reason=f"Forbidden function: {fn}().")
    for s in _SYSTEM_SCHEMAS:
        if re.search(rf"\b{s}\b", scan, re.I):
            return ValidationResult(False, reason=f"Access to system schema '{s}' is not allowed.")

    # tables referenced after FROM / JOIN must be project tables (or a CTE defined in the query)
    ctes = set(m.lower() for m in re.findall(r"(?:\bwith\b|,)\s*(?:recursive\s+)?(\w+)\s*(?:\([^)]*\))?\s*as\s*\(", scan, re.I))
    tables = []
    for m in re.finditer(r"\b(?:from|join)\s+(?!\()([`\w.]+)", scan, re.I):
        t = m.group(1).replace("`", "")
        if "." in t:
            db, t = t.split(".", 1)
            if db.lower() != "netflix_ci":
                return ValidationResult(False, reason=f"Cross-database access ({db}.{t}) is not allowed.")
        tl = t.lower()
        if tl in ctes:
            continue
        if tl not in ALLOWED_TABLES:
            return ValidationResult(False, reason=f"Unknown table '{t}'. Allowed: {', '.join(sorted(ALLOWED_TABLES))}.")
        tables.append(tl)

    notes = []
    m = re.search(r"\blimit\s+(\d+)(?:\s*,\s*(\d+)|\s+offset\s+\d+)?\s*$", scan, re.I)
    if m:
        n = int(m.group(2) or m.group(1))
        if n > max_rows:
            scan = re.sub(r"\blimit\s+\d+(\s*,\s*\d+|\s+offset\s+\d+)?\s*$", f"LIMIT {max_rows}", scan, flags=re.I); notes.append(f"LIMIT reduced to {max_rows}.")
    else:
        scan = f"{scan}\nLIMIT {DEFAULT_LIMIT}"; notes.append(f"Added LIMIT {DEFAULT_LIMIT}.")

    # return the ORIGINAL text (comments / literals intact) with the same limit handling applied
    final = re.sub(r";\s*$", "", sql.strip())
    if m:
        if notes:
            final = re.sub(r"\blimit\s+\d+(\s*,\s*\d+|\s+offset\s+\d+)?\s*$", f"LIMIT {max_rows}", final, flags=re.I)
    else:
        final = f"{final}\nLIMIT {DEFAULT_LIMIT}"
    return ValidationResult(True, sql=final, tables=sorted(set(tables)), notes=notes)
