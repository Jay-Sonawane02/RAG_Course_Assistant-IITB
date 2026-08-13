"""
The query_database tool's actual implementation. All the safety logic from
router_spec.md lives here: statement whitelist, injection guard, row cap,
read-only connection, and graceful error handling so a bad query becomes a
tool-result the LLM can see and recover from, not a crash.
"""

import re
import sqlite3

from config import SQL_DEFAULT_ROW_LIMIT
from db.connection import get_readonly_connection

_SELECT_ONLY = re.compile(r"^\s*SELECT\b", re.IGNORECASE)


def _is_select_only(sql: str) -> bool:
    """Reject anything that isn't a single SELECT statement."""
    if not _SELECT_ONLY.match(sql):
        return False
    # Guard against statement-stacking: a semicolon followed by more
    # non-whitespace content means there's a second statement riding along.
    # A single trailing semicolon (optionally followed by whitespace) is fine.
    stripped = sql.strip()
    semi_index = stripped.find(";")
    if semi_index != -1 and stripped[semi_index + 1:].strip():
        return False
    return True


def _has_limit_or_course_filter(sql: str) -> bool:
    lowered = sql.lower()
    return "limit" in lowered or "course_code" in lowered


def _enforce_row_cap(sql: str) -> str:
    """Append a LIMIT if the query has neither a LIMIT nor a course_code
    filter -- prevents a broad query from flooding the LLM's context."""
    if _has_limit_or_course_filter(sql):
        return sql
    stripped = sql.rstrip().rstrip(";")
    return f"{stripped} LIMIT {SQL_DEFAULT_ROW_LIMIT}"


def query_database(sql: str) -> dict:
    """
    Execute a read-only SQL query. Returns a dict suitable for handing back
    to the LLM as a tool result -- either {"rows": [...], "row_count": N}
    on success, or {"error": "..."} on any failure. Never raises.
    """
    if not sql or not sql.strip():
        return {"error": "Empty SQL query provided."}

    if not _is_select_only(sql):
        return {
            "error": (
                "Only single read-only SELECT statements are permitted. "
                "This query was rejected before execution."
            )
        }

    safe_sql = _enforce_row_cap(sql)

    try:
        conn = get_readonly_connection()
        cur = conn.cursor()
        cur.execute(safe_sql)
        rows = [dict(row) for row in cur.fetchall()]
        conn.close()
        return {"rows": rows, "row_count": len(rows)}
    except sqlite3.Error as e:
        return {"error": f"SQL error: {e}"}
