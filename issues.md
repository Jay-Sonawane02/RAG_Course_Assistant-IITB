# Issues Found & Fixed — Post-Launch Testing Log

Everything below happened *after* the first successful `streamlit run app.py`
— i.e. real bugs found by actually running the live app against the real
Claude API, not issues caught during the earlier isolated/mocked testing in
`IMPLEMENTATION.md`. Kept in chronological order, each with what was
observed, the actual root cause, the fix applied, and how confident we are
that it's actually fixed (not just "should be fixed").

---

## 1. Crash: "not enough values to unpack (expected 3, got 2)"

**Observed:** First query after the UI update failed immediately with this
Python error instead of an answer.

**Root cause:** Not a real bug — `agent/loop.py`'s `run_turn()` function was
changed to return 3 values (`messages, answer, tools_used`) instead of 2, as
part of adding the tool-usage badges to the UI. `app.py` was updated to
expect 3 values, but the local copy of `agent/loop.py` hadn't been replaced
yet, so it was still returning the old 2-value signature.

**Fix:** Replace `agent/loop.py` with the updated version whenever `app.py`
changes alongside it — the two files are coupled by this return signature.

**Confidence:** High — this is a straightforward signature mismatch, not a
logic bug. Resolved immediately once both files were in sync.

---

## 2. Silent numerical inconsistency in grade-average calculations

**Observed:** Asked *"which ML electives are easy to score well in?"* twice.
First run gave correct numbers (verified against the real database directly:
CS769 = 7.15, CS217 = 7.21, etc.). Second run gave **different, wrong**
numbers for the same courses (CS769 = 8.24, CS217 = 7.48, with inflated
student counts too) — same question, same data, different answer.

**Root cause:** The SQL tool uses freeform text-to-SQL — the LLM writes a
fresh query every single call rather than using a fixed function. The
system prompt described the JOIN logic needed (grade_distributions →
grade_points → courses) but didn't give an exact query to follow, so the
model reconstructed it differently across calls. One reconstruction was
correct; another silently double-counted or mis-filtered something and
produced wrong numbers with no error — the query was syntactically valid
SQL, just semantically different from what was intended.

**Fix:** Added the exact, verified-correct SQL query as a literal template
directly in `tools/schemas.py`'s tool description, with explicit instruction
to copy it rather than reconstruct it from scratch. This trades away some of
freeform SQL's flexibility specifically for the one calculation that needed
to be reliably exact.

**Confidence:** High — re-ran the identical question 2 more times after the
fix; both runs matched ground truth exactly and matched each other exactly
(same numbers, same course order). This is meaningfully different from "it
worked once."

---

## 3. Inconsistent answer formatting across identical questions

**Observed:** Same "which ML electives" question — one run produced a clean
markdown table, a later run produced a bulleted list with sub-bullets for
the same 9-course comparison. The table was genuinely easier to scan; the
list wasn't a formatting bug exactly, just a worse choice for this kind of
side-by-side comparison, and nothing was pinning the model to a consistent
choice.

**Root cause:** The system prompt had no formatting guidance at all — table
vs. list vs. prose was left entirely to the model's in-the-moment judgment,
which isn't guaranteed to be stable run to run.

**Fix:** Added explicit formatting rules to `agent/system_prompt.py`: use a
markdown table for multi-course comparisons with several attributes, plain
prose for single-course or simple yes/no answers.

**Confidence:** High — re-tested across 5+ different questions after the
fix (multi-course rankings, single-course lookups, a 2-course comparison);
formatting stayed appropriate and consistent in every case observed.

---

## 4. Table silently truncated mid-row on a large result set

**Observed:** Asked to rank *all* PG-level courses (51 of them). The
response cut off mid-table at course #33, with the next row's cells empty —
not an error, just silently incomplete output that could easily be mistaken
for the full list.

**Root cause:** `MAX_TOKENS` in `config.py` was set to 1024. A 50+ row
markdown table plus surrounding analysis text exceeded that ceiling, and the
response was cut off exactly where the token budget ran out.

**Fix:** Two changes together, not just one:
1. Raised `MAX_TOKENS` from 1024 to 4096 in `config.py`.
2. Added guidance to the system prompt: for rankings/comparisons involving
   more than ~15 courses, show a top 10-15 subset and **say explicitly**
   that the list has been limited, rather than attempting to list
   everything and risking another silent cutoff.

**Confidence:** High for the specific case tested — re-ran the same "rank
all PG courses" question; it correctly returned 15 rows with an explicit
"showing top 15 of 51" style note, no more empty-cell truncation.

**Cost note:** raising `MAX_TOKENS` raises the *ceiling* on possible output
length, which raises the *ceiling* on per-query cost too, even though actual
cost only increases when a response genuinely needs the extra room. Worth
watching against the workspace spend limit.

---

## 5. Vector search occasionally surfaces topically-adjacent but irrelevant courses

**Observed:** A "security electives" query pulled in CS348/CS224M (plain
Computer Networks — confirmed via direct DB check, no mention of "security"
anywhere in either syllabus). A later "ML electives" query pulled in CS602
(Applied Algorithms — no ML content) and, separately, CS789 (Probabilistic
Proof Systems — also unrelated). Confirmed via direct database inspection
that these courses' syllabus text has no real connection to the query topic.

**Root cause:** Semantic similarity isn't the same as topical correctness.
`search_syllabi` ranks by embedding distance, and a course can land
"nearby" in vector space to a query without actually being about that
query's subject (e.g. shared vocabulary around proofs/algorithms without
shared subject matter).

**Fix attempted:** Added instruction to `tools/schemas.py`'s
`search_syllabi` description explicitly warning that similarity-ranked
results aren't guaranteed topically correct, and telling the model to
review and exclude tangential matches before presenting them.

**Confidence: partial, not fully resolved.** Re-ran the exact same "ML
electives" question 3 additional times after the fix — all 3 came back
clean (no CS602, no CS789). But this was already an intermittent problem
before the fix too, so 3 clean runs isn't proof of a full fix, just evidence
the failure rate is low. We tried to pin down the exact similarity score
that was letting these through (to set a hard numeric threshold instead of
soft LLM guidance) by adding temporary debug logging, but the false
positives didn't reproduce during that specific debugging session, so we
don't have the number needed to set a more precise cutoff.

**Decision:** Documented as a known limitation rather than pursued further.
Given the observed rate (roughly 1 anomalous run out of 6 total attempts
across both the security-electives and ML-electives cases), further
engineering effort here has diminishing returns for a portfolio-scale
project. If this recurs noticeably in future testing, the next step would
be tuning `VECTOR_SEARCH_MIN_SIMILARITY` in `config.py` with real observed
numbers, not tightening the soft prompt guidance further.

---

## 6. Observed but not yet fixed: model's own summary text can be internally inconsistent

**Observed:** In the "rank all PG courses" response, the model's own
summary said *"the top 3 courses (CS782, CS691, CS740, CS604) have very
small cohorts"* — four courses named as "the top 3," and two of them
(CS740, CS604) weren't even in the displayed top-15 table's actual top 3 by
rank.

**Root cause:** Not investigated in depth. Likely the model drafting the
summary loosely from memory of the full tool result rather than strictly
cross-checking against the table it just rendered.

**Status:** Not fixed. Noted here so it isn't forgotten — worth watching
for in future testing, and worth adding explicit "your summary must match
the table exactly" guidance if it recurs.

---

## Running tally

| # | Issue | Severity | Status |
|---|---|---|---|
| 1 | Crash from mismatched file versions | High (crash) | Fixed — user error, not a code bug |
| 2 | Wrong grade averages, inconsistent across runs | High (silent wrong data) | Fixed, verified across repeats |
| 3 | Inconsistent table/list formatting | Low (cosmetic) | Fixed, verified across repeats |
| 4 | Silent table truncation on large result sets | Medium (silent incomplete data) | Fixed, verified |
| 5 | Vector search topical false positives | Medium (occasional wrong inclusions) | Partially mitigated, documented as known limitation |
| 6 | Inconsistent self-summary text | Low (cosmetic, but confusing) | Not fixed, noted for future work |

**The pattern across most of these**: problems 2, 3, and 4 all trace back to
the same root cause — leaving something important to the LLM's per-call
judgment without a hard constraint, when what was actually needed was
either an exact template to follow (problem 2) or an explicit rule instead
of vague guidance (problems 3 and 4). Problem 5 is the one case where a
harder constraint (a numeric threshold) would likely help more than the
soft instruction that was tried, but we didn't have the real data needed to
set that threshold correctly, so it's left as an honest open item rather
than a guessed "fix."