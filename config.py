"""
Central configuration. Every other module imports from here rather than
hardcoding paths or model names -- change something once, it's correct
everywhere.
"""

import os
from pathlib import Path

# --- Paths -----------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent
DB_PATH = PROJECT_ROOT / "course_assistant.db"
CHROMA_PERSIST_DIR = PROJECT_ROOT / "chroma_store"
CHROMA_COLLECTION_NAME = "syllabi"

# --- Embedding model ---------------------------------------------------------
# Local, free, no API key. all-MiniLM-L6-v2 is a small, fast, well-tested
# sentence-transformers model -- more than sufficient for 91 short documents.
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"

# --- LLM (Claude API) --------------------------------------------------------
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
CLAUDE_MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 4096

# --- Tool guardrails ---------------------------------------------------------
SQL_DEFAULT_ROW_LIMIT = 50
VECTOR_SEARCH_DEFAULT_TOP_K = 5
VECTOR_SEARCH_MIN_SIMILARITY = 0.3  # below this, treat as "no relevant match"

# --- Sanity check on import ---------------------------------------------------
if not DB_PATH.exists():
    raise FileNotFoundError(
        f"Database not found at {DB_PATH}. Copy your course_assistant.db "
        f"into the project root before running anything else."
    )