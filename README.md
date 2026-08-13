# RAG Course Assistant — Project README

IIT Bombay CSE elective-selection assistant. Combines semantic search over
syllabus content with SQL-based grade analytics, routed automatically by an
LLM via native tool calling — built specifically to demonstrate the judgment
that **structured data (grades) should be queried, not embedded**, while
**unstructured data (syllabi) should be searched semantically, not filtered**.

**Live app: https://rag-course-assistant-iitb.streamlit.app/**

**Status: built, live-tested against the real Claude API, bugs found and
fixed, deployed and live.** Full implementation in `course_assistant/`. See
`ISSUES_AND_FIXES.md` for what broke during real testing and how it was
diagnosed and fixed — that log is arguably the most interesting artifact in
this whole project for interview purposes.

---

## 0. The actual goal (read this before touching code)

This isn't "build a working RAG app" — that's a means, not the goal. The
real deliverable is a **resume project that demonstrates engineering
judgment about when *not* to use RAG**, demoable live in an interview.

"Done" concretely means — **all four now actually confirmed via live testing, not just planned:**
- A Streamlit app you can open and run live, deployed and shareable, not just describe from a screenshot.
- "Which ML electives are easy to score well in?" → confirmed to visibly use
  *both* tools (vector search for "ML electives," then SQL for grades)
  before answering, with tool-usage badges in the UI showing exactly which
  fired.
- "What are CS725's prerequisites?" → confirmed to go straight to SQL, no
  vector-search detour.
- Something it can't answer (timetable clashes, missing grade data) →
  confirmed to say so honestly instead of inventing an answer, tested
  directly against both cases.

The one-sentence interview pitch this whole project exists to make true:
*"Most people would dump everything into a vector store. I noticed grade
distributions are tabular and shouldn't be embedded, so I built a router
that lets the LLM choose between SQL and semantic search per question."*

**Deliberately out of scope**, so effort doesn't drift: no auth, no
multi-user concerns, no deployment hardening, no chasing 100% data coverage.
A correctly-scoped working demo beats a bigger, flakier one — especially
since the value is in explaining the reasoning, not just showing an app.

---

## 1. Data layer

### `courses` table — 91 rows

Scraped from `https://www.cse.iitb.ac.in/academics/courses` (an Angular/MDB
single-page app — required Playwright, not plain HTML scraping) plus one
manually added course (CS738, found via grade data that had no matching
course record).

| Column | Notes |
|---|---|
| `course_code` | Primary key, e.g. `CS725` |
| `title`, `department` | |
| `home_page` | Course's own page, where one exists |
| `autumn_instructor`, `spring_instructor` | |
| `semester` | `'Autumn'`, `'Spring'`, or `'Autumn, Spring'` (only CS101 is both) |
| `credits`, `prerequisites`, `duration`, `course_type` | |
| `syllabus_text` | The field that gets embedded for semantic search |
| `references_text` | Textbook citations — metadata, not embedded |
| `source_url`, `last_updated` | |
| `level` | `'UG'` or `'PG'` — derived from the course code's numeric part (below 500 = UG, 500+ = PG). Verified against all 91 real codes with zero parse failures. 31 UG / 60 PG. |

### `grade_distributions` table — 582 rows across 81 courses

Manually collected from ASC (behind IITB login, so scraping wasn't possible)
using a purpose-built paste-and-parse tool (`grade-entry-tool.html`).

| Column | Notes |
|---|---|
| `course_code` | FK → `courses.course_code` |
| `grade` | Letter grade, e.g. `AA`, `BC`, `FR` |
| `student_count` | |

No `academic_year` or `semester` column — deliberately dropped since all
data is from a single year (2025) and most courses run in only one semester
per year; the rare exception (CS101) just has its grades summed together
under one course code, which is fine for "how tough is this course overall."

**10 courses have no grade data** (checked — not a rename/replace situation,
confirmed by scanning syllabus text for "replaces"/"reused" language, found
nothing):
- Autumn: `CS416M`, `CS616`, `CS694`, `CS6010`, `CS6012`, `CS6013`, `CS7001`, `CS721`
- Spring: `CS6009`, `CS713`

CS694 is a Seminar course, almost certainly pass/fail and never letter-graded
— not really "missing," just not applicable. The other 9 are unresolved;
likely either didn't run that year or weren't graded via ASC. Deprioritized
rather than chased further.

### `grade_points` table — verified against IITB's official grading rules

Built after initially getting one grade wrong (`AP` was assumed to mean
"Audit Pass" — actually a full 10-point grade, same tier as `AA`; audit is
`AU`, a separate ungraded grade). Verified via web search against IITB's
actual rules document before use.

| grade | points | is_pass |
|---|---|---|
| AP, AA | 10 | 1 |
| AB | 9 | 1 |
| BB | 8 | 1 |
| BC | 7 | 1 |
| CC | 6 | 1 |
| CD | 5 | 1 |
| DD | 4 | 1 (minimum passing grade) |
| FF, FR, DX | 0 | 0 |
| II, AU, W, DR | NULL | NULL (excluded from averages entirely) |
| PP | NULL | 1 |
| NP | NULL | 0 |

Any future "easiest course" / "average grade" query should `JOIN` against
this table rather than the LLM guessing a mapping.

---

## 2. Tools built along the way

| File | Purpose |
|---|---|
| `scrape_playwright.py` | Scrapes the CSE courses SPA — expands semester accordions, clicks each course's modal, parses fields by their literal UI labels |
| `course-entry-tool.html` | Paste a course's modal text (or any similarly-labeled syllabus page) → auto-parses fields → editable form → exports SQL. In-memory only (no persistent storage — that API doesn't work outside Claude's own artifact preview) |
| `grade-entry-tool.html` | Paste an ASC grade-stats page → auto-detects course code and grade/count pairs → editable rows → exports SQL. Handles the "first grade block vs. secondary section breakdown" ambiguity correctly (confirmed against real CS728/CS101 samples) |
| `schema.sql` | Base schema: `courses` + `grade_distributions` |
| `schema_migration_v2.sql` | Adds `level` column + `grade_points` table |

All course and grade INSERT batches were validated by actually executing
them against a real SQLite engine (not eyeballed) — catching real bugs like
unescaped apostrophes, missing column values, and foreign-key mismatches
before they reached the working database.

---

## 3. Final architecture

```
User ⇄ Streamlit UI (multi-turn conversation)
              │
              ▼
     LLM (Claude API, tool calling)
       │                    │
       ▼                    ▼
 search_syllabi      query_database
 (Chroma, vector)    (SQLite, text-to-SQL)
```

### Router
No custom classifier. Native LLM tool/function calling — the model itself
decides which tool(s) to call based on the two tool descriptions it's given.
Can call one tool, both, or one after seeing the other's result, all within
one conversational turn.

### `search_syllabi`
- **Store**: Chroma (separate from SQLite)
- **Embedding model**: sentence-transformers, local — no API key, no cost, runs on-device
- **Granularity**: one vector per course, not sub-document chunks (syllabi are short enough that a course is already the right retrieval unit — chunking would just fragment single-course hits)
- **What's embedded**: `title + syllabus_text` concatenated (title alone can carry keywords the body never repeats)
- **Missing-data fallback**: when `syllabus_text = 'N/A'`, embed the title alone rather than skipping the course

### `query_database`
- **Approach**: freeform text-to-SQL — the LLM writes its own `SELECT`, not a fixed menu of pre-built functions
- **Guardrails**: read-only connection, reject non-SELECT statements, reject statement-stacking (`;` followed by more content), enforce a row-count cap when no `LIMIT`/course filter is present
- **Full schema (both tables + grade_points) is embedded directly in the tool's description string**, so the LLM always has it — no separate schema-discovery step

### Interface
Streamlit, multi-turn. Conversation history is passed to the LLM each call,
so follow-up questions work without extra engineering — this falls out of
the tool-calling architecture for free.

---

## 4. Router specification (tool schemas, system prompt, error handling)

Full detail in `router_spec.md`. Summary of the key routing rule, arrived at
by stress-testing the design against realistic "first two weeks of semester"
student questions:

> **If the student names an exact course code or title, prefer
> `query_database` over `search_syllabi`** — even for topic questions like
> "what does CS725 cover" — since a direct `WHERE course_code = ...` lookup
> is more reliable than semantic search once you already know the target.
> `search_syllabi` is reserved for "help me find a course about X" when the
> course itself is unknown.

Also encoded in the system prompt: mandatory use of `grade_points` for any
grade-average calculation, and two honest, stated limitations the assistant
should surface rather than guess around:
- **No class-timetable data exists.** Timing/clash questions can't be answered.
- **Grade data is missing for ~10 courses.** If a query returns nothing, say so — don't invent numbers.

---

## 5. Known limitations (accepted scope boundaries, not bugs)

- No lecture timetable data — timing/clash questions are out of scope
- `prerequisites` text is inconsistently formatted across courses (`"CS 213"` vs `"CS213"` vs `"CS101 & CS213 M"`), so prerequisite-matching queries may miss variants
- 10 courses have no grade data (listed above)
- Grade averages from very-low-enrollment courses (e.g. 2-3 students) can be misleading — system prompt tells the LLM to flag this explicitly rather than present a "10.0 average" as meaningful on its own

---

## 6. Implementation status

**Built, live-tested, and deployed.** All modules from the architecture
above exist and run: `db/connection.py`, `embeddings/embedder.py` +
`embeddings/build_index.py`, `tools/query_database.py` +
`tools/search_syllabi.py`, `agent/loop.py` + `agent/system_prompt.py`,
`app.py`. Full file layout and setup instructions in
`course_assistant/IMPLEMENTATION.md`.

Every module was tested two ways:
1. **In isolation, with mocks**, during initial build (SQL injection
   attempts, the tool-use control flow, similarity-threshold filtering,
   etc.) — see `IMPLEMENTATION.md` for the full breakdown of what was
   verified this way and what genuinely couldn't be (no Hugging Face or
   live API access in the build sandbox).
2. **Live, against the real running app and real Claude API** — this is
   where the actually interesting bugs surfaced, since isolated tests with
   mocked responses can't catch problems that only show up when a real LLM
   makes different decisions across repeated identical questions.

**Six real issues were found and fixed via live testing** — full detail,
root causes, and fixes in `ISSUES_AND_FIXES.md`. Summary:

| # | Issue | Status |
|---|---|---|
| 1 | Crash from mismatched file versions after an update | Fixed |
| 2 | Silent wrong grade-average numbers, inconsistent across identical repeated questions | Fixed, verified across repeats |
| 3 | Inconsistent table/list formatting across identical questions | Fixed, verified across repeats |
| 4 | Large ranking queries silently truncated mid-table | Fixed, verified |
| 5 | Vector search occasionally surfaces topically-adjacent but irrelevant courses | Partially mitigated, documented as a known limitation rather than force-fixed |
| 6 | Model's own summary text occasionally inconsistent with the data table it just rendered | Not fixed, noted for future work |

**The genuinely interesting pattern**: issues 2, 3, and 4 all traced back
to the same root cause — leaving something important to the LLM's per-call
judgment instead of giving it a hard constraint. Issue 2 got fixed with an
exact query template to copy rather than reconstruct; issues 3 and 4 got
fixed with explicit rules instead of vague guidance. Issue 5 is the one
case where a harder constraint (a numeric similarity threshold) would
likely help more than the soft instruction that was tried — but we
couldn't reproduce the failure case with debug logging on to get the real
number needed to set that threshold correctly, so it's left as an honest
open item rather than a guessed fix. That's a genuinely defensible
engineering story, not just "I built a RAG app and it worked."

## 7. Deployment

**Live at https://rag-course-assistant-iitb.streamlit.app/** — deployed via
Streamlit Community Cloud (free, GitHub-connected). Full walkthrough in
`course_assistant/DEPLOYMENT.md`, including the two deployment-specific
code changes that were needed:
- `config.py` reads the API key via `st.secrets` when running on Community
  Cloud, falling back to a plain environment variable for local dev.
- `chroma_store/` (the built vector index) is committed directly to the
  repo rather than rebuilt on every deploy, since Community Cloud's
  filesystem resets between deploys and rebuilding would mean re-downloading
  the embedding model from Hugging Face each time.

Known, accepted deployment limits (free tier): ~1GB RAM, app sleeps after
12 hours idle (auto-wakes on next visit), only one private app allowed.
Fine for a portfolio demo; documented rather than worked around.