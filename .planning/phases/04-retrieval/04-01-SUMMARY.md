---
phase: 04-retrieval
plan: 01
subsystem: database
tags: [chromadb, vector-search, retrieval, sessionstart-hook, token-budget]

# Dependency graph
requires:
  - phase: 03-storage
    provides: get_chroma_client(), COLLECTION_NAME, index_session_file() for ChromaDB access
  - phase: 02-capture
    provides: read_hook_input() for stdin JSON parsing

provides:
  - query_sessions(project_dir, query_text, n_results) — ChromaDB similarity search returning document strings
  - format_context(documents, token_budget) — token-budgeted context assembly with --- separators
  - run_retrieve() — SessionStart hook pipeline printing hookSpecificOutput JSON to stdout
  - tests/test_retrieve.py — 9 TDD tests covering RETR-01, RETR-02, RETR-03

affects:
  - 04-02 (CLI retrieve and recall subcommands — will import query_sessions, format_context)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Lazy chromadb import inside query_sessions() function body (consistent with Phase 3)
    - get_collection() + try/except for read-only access (no get_or_create on query path)
    - min(n_results, count) guard against ChromaDB ValueError on oversized queries
    - chars/4 token estimate for soft budget enforcement
    - print(json.dumps(output), flush=True) for reliable hook stdout

key-files:
  created:
    - src/thehook/retrieve.py
    - tests/test_retrieve.py
  modified: []

key-decisions:
  - "get_collection() used instead of get_or_create_collection() in query_sessions — avoids creating an empty collection on first query"
  - "min(n_results, count) caps query to avoid ChromaDB ValueError when n_results exceeds collection count"
  - "Static query string 'project conventions decisions gotchas architecture' for SessionStart — no user input available at session start"
  - "print(json.dumps(output), flush=True) with flush — prevents dropped output if hook process is killed before buffer flushes"
  - "Entire run_retrieve() wrapped in try/except Exception: pass — hook must never crash, degrade silently"
  - "Token budget loaded from config via load_config(project_dir) — respects user's thehook.yaml token_budget setting"

patterns-established:
  - "Read-only ChromaDB access: use get_collection() + except, not get_or_create_collection()"
  - "Hook output: single print(json.dumps(...), flush=True) call, nothing else to stdout"
  - "Token budgeting: chars/4 approximation, trim last document to fit remaining space"

requirements-completed: [RETR-01, RETR-02, RETR-03]

# Metrics
duration: 7min
completed: 2026-02-24
---

# Phase 04 Plan 01: Retrieve Module Summary

**ChromaDB similarity search with query_sessions(), token-budgeted format_context(), and SessionStart hook pipeline run_retrieve() — 9 TDD tests, 63 total green**

## Performance

- **Duration:** 7 min
- **Started:** 2026-02-24T10:23:31Z
- **Completed:** 2026-02-24T10:31:23Z
- **Tasks:** 1 (TDD: RED + GREEN phases)
- **Files modified:** 2

## Accomplishments

- `src/thehook/retrieve.py` with `query_sessions()`, `format_context()`, and `run_retrieve()` — all with lazy imports and graceful error handling
- `tests/test_retrieve.py` with 9 test cases: 3 for query_sessions (returns docs, empty collection, missing collection), 3 for format_context (joins, truncates, empty), 3 for run_retrieve (valid JSON, empty output, config token_budget)
- Full test suite (63 tests) passes with zero regressions
- SessionStart hook output contract verified: `hookSpecificOutput.hookEventName = "SessionStart"` with `additionalContext` string

## Task Commits

TDD flow produced two task commits:

1. **RED phase: failing tests** - `747f859` (test)
2. **GREEN phase: retrieve implementation** - `a814bed` (feat)

## Files Created/Modified

- `src/thehook/retrieve.py` - Retrieve module: query_sessions, format_context, run_retrieve
- `tests/test_retrieve.py` - 9 TDD test cases for retrieve module

## Decisions Made

- **get_collection() over get_or_create_collection():** query_sessions uses `client.get_collection()` wrapped in try/except. This avoids creating an empty ChromaDB collection on the first query when no sessions have been captured yet. The exception path returns `[]` gracefully.
- **min(n_results, count) guard:** ChromaDB raises `ValueError` when `n_results > collection.count()`. The guard ensures we never request more results than exist.
- **Static query string for SessionStart:** No user input is available at session start, so a fixed query string targeting the most useful knowledge categories ("project conventions decisions gotchas architecture") is used. This is a v1 heuristic.
- **flush=True on stdout:** Critical for hook reliability — if the process is killed before the buffer flushes, Claude Code receives no JSON. `flush=True` ensures immediate write.
- **Entire pipeline wrapped in try/except:** `run_retrieve()` catches all exceptions silently. A crashing hook would break the Claude Code session start flow, so silent degradation is the correct behavior.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `retrieve.py` is complete and tested — ready for plan 04-02 (CLI retrieve and recall subcommands)
- `query_sessions()` and `format_context()` are ready to be imported by CLI commands
- `run_retrieve()` is ready to be wired to `thehook retrieve` CLI command
- No blockers for plan 04-02

---
*Phase: 04-retrieval*
*Completed: 2026-02-24*

## Self-Check: PASSED

- FOUND: `src/thehook/retrieve.py`
- FOUND: `tests/test_retrieve.py`
- FOUND: `.planning/phases/04-retrieval/04-01-SUMMARY.md`
- FOUND: commit `747f859` (RED phase -- failing tests)
- FOUND: commit `a814bed` (GREEN phase -- retrieve implementation)
