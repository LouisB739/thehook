---
phase: 04-retrieval
plan: 02
subsystem: cli
tags: [click, cli, retrieve, recall, sessionstart-hook, integration-tests]

# Dependency graph
requires:
  - phase: 04-retrieval-01
    provides: query_sessions(), format_context(), run_retrieve() from retrieve.py

provides:
  - "thehook retrieve" CLI subcommand (SessionStart hook entry point)
  - "thehook recall <query>" CLI subcommand with --path option (user-facing search)
  - 4 CLI integration tests in tests/test_retrieve.py (13 total)

affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Lazy import of run_retrieve inside retrieve CLI command body (consistent with capture, reindex)
    - Lazy import of query_sessions, format_context, load_config inside recall CLI command body
    - recall loads token_budget from config via load_config(project_dir)
    - recall prints "No relevant knowledge found." for empty results (user-friendly feedback)

key-files:
  created: []
  modified:
    - src/thehook/cli.py
    - tests/test_retrieve.py

key-decisions:
  - "CliRunner() without mix_stderr -- Click version in project does not support mix_stderr parameter"
  - "recall uses click.echo(format_context(...)) for output -- same format_context as run_retrieve, consistent output"
  - "retrieve command has no options -- all input from stdin, matching SessionEnd capture pattern"

patterns-established:
  - "All CLI subcommands use lazy imports inside function body for fast startup"
  - "Commands taking project path use --path option with default '.'"

requirements-completed: [RETR-03, RETR-04]

# Metrics
duration: 4min
completed: 2026-02-24
---

# Phase 04 Plan 02: CLI Retrieve and Recall Subcommands Summary

**`thehook retrieve` and `thehook recall` CLI subcommands wired with lazy imports, token budget from config, and 4 integration tests -- 67 total tests green**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-24T10:35:26Z
- **Completed:** 2026-02-24T10:39:46Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- `thehook retrieve` subcommand registered -- calls `run_retrieve()` for SessionStart hook pipeline (stdin JSON -> stdout JSON)
- `thehook recall <query> --path <dir>` subcommand registered -- queries ChromaDB and prints matching results with token budget from config
- 4 CLI integration tests using CliRunner cover: retrieve with indexed data, retrieve with empty collection, recall with results, recall with empty collection
- Full test suite (67 tests) passes with zero regressions
- The complete memory loop is now wired: capture at SessionEnd -> index to ChromaDB -> inject at SessionStart -> recall on demand

## Task Commits

Each task was committed atomically:

1. **Task 1: Add retrieve and recall CLI subcommands** - `1b6dda6` (feat)
2. **Task 2: Add CLI integration tests for retrieve and recall** - `8a3b350` (test)

## Files Created/Modified

- `src/thehook/cli.py` - Added retrieve and recall subcommands with lazy imports
- `tests/test_retrieve.py` - Appended 4 CLI integration tests (13 total in file)

## Decisions Made

- **CliRunner() without mix_stderr:** The plan specified `CliRunner(mix_stderr=False)` but the installed Click version does not support that parameter. Used plain `CliRunner()` matching existing test patterns in test_capture.py and test_init.py.
- **retrieve has no options:** All input comes from stdin (hook input JSON), exactly matching the capture command pattern. No --path needed since cwd comes from the hook input.
- **recall uses format_context for output:** Same function used by run_retrieve, ensuring consistent formatting between automatic injection and manual recall.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed mix_stderr=False from CliRunner**
- **Found during:** Task 2 (CLI integration tests)
- **Issue:** Plan specified `CliRunner(mix_stderr=False)` but the installed Click version raises `TypeError: CliRunner.__init__() got an unexpected keyword argument 'mix_stderr'`
- **Fix:** Changed to `CliRunner()` matching existing test patterns in test_capture.py and test_init.py; removed `result.stderr` references from assertions
- **Files modified:** tests/test_retrieve.py
- **Verification:** All 13 tests pass
- **Committed in:** 8a3b350 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Trivial API compatibility fix. No scope creep.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 4 (Retrieval) is complete -- all 4 RETR requirements satisfied
- The full v1.0 memory loop is working end-to-end:
  - `thehook init` wires hooks and creates project structure
  - `thehook capture` extracts knowledge at SessionEnd
  - `thehook reindex` rebuilds ChromaDB from markdown
  - `thehook retrieve` injects context at SessionStart
  - `thehook recall <query>` enables on-demand natural language search
- All 67 tests pass across 4 test files

---
*Phase: 04-retrieval*
*Completed: 2026-02-24*

## Self-Check: PASSED

- FOUND: `src/thehook/cli.py`
- FOUND: `tests/test_retrieve.py`
- FOUND: `.planning/phases/04-retrieval/04-02-SUMMARY.md`
- FOUND: commit `1b6dda6` (feat: retrieve and recall CLI subcommands)
- FOUND: commit `8a3b350` (test: CLI integration tests)
