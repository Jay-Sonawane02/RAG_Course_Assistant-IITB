# Course Assistant — Implementation

Modular implementation of the architecture in `router_spec.md`. See the
project-root `README.md` for the full design rationale — this file is just
setup/run instructions for this code.

## Structure

```
config.py                # paths, model names, constants
db/connection.py         # normal + hardened read-only SQLite connections
embeddings/embedder.py   # sentence-transformers wrapper
embeddings/build_index.py # courses table -> Chroma index (run once)
tools/schemas.py         # Claude tool-use JSON schemas
tools/query_database.py  # SQL tool: guardrails + execution
tools/search_syllabi.py  # vector tool: embed + search + threshold
agent/system_prompt.py   # system prompt text
agent/loop.py             # the actual Claude tool-use loop
app.py                    # Streamlit UI
```

## Setup

```bash
pip install -r requirements.txt
```

Copy your `course_assistant.db` (with `courses`, `grade_distributions`,
`grade_points` tables, and the `level` column already added) into this
directory.

Set your API key:
```bash
cp .env.example .env
# edit .env, add your real ANTHROPIC_API_KEY
export ANTHROPIC_API_KEY=your-key-here   # or use python-dotenv if you prefer
```

## Build the vector index (run once, or whenever course data changes)

```bash
python -m embeddings.build_index
```

First run downloads the `all-MiniLM-L6-v2` model from Hugging Face (~90MB) —
needs real internet access once. Every run after that is offline and fast,
since the model gets cached locally.

## Run the app

```bash
streamlit run app.py
```

## What's been tested vs. not

Tested end-to-end against real data in the build sandbox:
- SQL tool: 9 cases including injection attempts, syntax errors, the row
  cap, and a real grade-point-average join — all correct.
- Embedding wrapper, `build_index`'s N/A-fallback logic, and the vector
  search similarity threshold — all correct (tested with fake models/
  collections where network access wasn't available).
- The full tool-use loop's control flow — single tool call, chained
  two-tool calls, and the safety-valve cutoff — all correct (tested with a
  mocked Claude client).

**Not yet tested: an actual live run against the real Claude API, the real
embedding model download, and the real Streamlit UI in a browser.** The
sandbox this was built in has network restrictions (no Hugging Face access)
and no API key — those three things need a real run on your machine as the
first true end-to-end test. Everything underneath them has been verified in
isolation, but "all the pieces work" isn't the same claim as "the whole
system works" — that first real run is worth doing carefully, not just
assuming it'll be fine.
