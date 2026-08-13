"""
Two connection helpers, deliberately kept separate:

- get_connection(): normal read-write connection. Use for setup/admin
  scripts (like build_index.py reading the courses table).
- get_readonly_connection(): opened in SQLite's URI read-only mode. Use
  for anything that executes LLM-generated SQL. Even if every other
  guardrail in tools/query_database.py were somehow bypassed, this
  connection itself physically cannot write to the database.
"""

import sqlite3

from config import DB_PATH


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_readonly_connection() -> sqlite3.Connection:
    uri = f"file:{DB_PATH}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn
