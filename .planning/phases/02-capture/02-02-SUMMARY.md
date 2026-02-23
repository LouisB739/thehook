---
phase: 02-capture
plan: 02
subsystem: capture
tags: [subprocess, process-group, timeout, session-file, frontmatter, graceful-degradation, tdd]

# Dependency graph
requires:
  - phase: 02-capture/02-01
    provides: parse_transcript, read_hook_input, assemble_transcript_text, tmp_project fixture, conftest.py
provides:
  - LLM extraction via run_claude_extraction (Popen + killpg on timeout, 85s hard limit)
  - Session file writing via write_session_file (YAML frontmatter + content, mkdir parents)
  - Graceful degradation via write_stub_summary (all four sections, failure reason + message count)
affects: [02-capture plan 03, 03-storage, 04-retrieval]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "TDD RED/GREEN — failing tests on missing imports, then full implementation"
    - "Popen with start_new_session=True for process group isolation (thread-safe, Python 3.2+)"
    - "os.killpg(os.getpgid(proc.pid), signal.SIGKILL) on TimeoutExpired — kills entire process tree"
    - "proc.communicate() after killpg — reaps zombie to avoid resource leaks"
    - "stdout.decode().strip() or None — falsy empty-string treated same as None (graceful degradation)"
    - "YAML frontmatter with session_id, timestamp, transcript_path — matches Phase 3 storage schema"
    - "write_stub_summary delegates to write_session_file — single write path for all outcomes"

key-files:
  created: []
  modified:
    - src/thehook/capture.py
    - tests/test_capture.py

key-decisions:
  - "start_new_session=True used (not preexec_fn=os.setsid) — thread-safe equivalent, documented Python 3.2+ standard"
  - "stdout.decode().strip() or None — explicit falsy check treats empty stdout as extraction failure, not empty file"
  - "proc.communicate() called after killpg — mandatory zombie reap; without this, killed proc stays in process table"
  - "write_stub_summary delegates to write_session_file — single write path ensures stubs have identical frontmatter format"
  - "EXTRACTION_TIMEOUT_SECONDS = 85 as module-level constant — single source of truth used by Popen and documented in tests"

patterns-established:
  - "Pattern: Process group kill — Popen(start_new_session=True) + killpg(SIGKILL) + communicate() reap"
  - "Pattern: Graceful degradation — falsy extraction result triggers stub write with reason label"
  - "Pattern: Session file format — YAML frontmatter block + markdown body, date-prefixed filename"

requirements-completed: [CAPT-03, CAPT-05]

# Metrics
duration: 3min
completed: 2026-02-23
---

# Phase 2 Plan 02: LLM Extraction Subprocess and Session File Writing Summary

**Subprocess process-group management with 85s timeout+killpg, session file writing with YAML frontmatter, and stub summary fallback for all failure paths — 9 TDD tests added (18 total passing)**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-23T21:45:55Z
- **Completed:** 2026-02-23T21:48:11Z
- **Tasks:** 2 (RED + GREEN)
- **Files modified:** 2

## Accomplishments

- `run_claude_extraction` calls `claude -p` via `subprocess.Popen` with `start_new_session=True`, kills entire process group via `os.killpg(SIGKILL)` on `TimeoutExpired`, reaps zombie with `proc.communicate()`, returns `None` on timeout/error/empty output
- `write_session_file` writes YAML frontmatter (`session_id`, `timestamp`, `transcript_path`) followed by markdown content, creates parent directories, returns the output `Path`
- `write_stub_summary` writes all four structured sections (`SUMMARY`, `CONVENTIONS`, `DECISIONS`, `GOTCHAS`) with failure reason and message count, delegates to `write_session_file` for consistent frontmatter
- 9 new TDD tests cover all extraction paths: success, timeout+killpg, nonzero exit, empty stdout, OSError, plus session file dir creation and stub metadata
- Full suite of 32 tests passes with no regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: RED — Write failing tests for extraction subprocess and session file writing** - `a49729f` (test)
2. **Task 2: GREEN — Implement extraction subprocess and session file writing** - `58cdcb8` (feat)

**Plan metadata:** (docs commit below)

_Note: TDD tasks have separate RED (test) and GREEN (feat) commits_

## Files Created/Modified

- `src/thehook/capture.py` - Added `run_claude_extraction`, `write_session_file`, `write_stub_summary`, `EXTRACTION_TIMEOUT_SECONDS`; added `os`, `signal`, `subprocess`, `datetime` imports
- `tests/test_capture.py` - 9 new tests for extraction subprocess (5) and session file writing (4); import extended to include new functions

## Decisions Made

- `start_new_session=True` used instead of `preexec_fn=os.setsid` — thread-safe Python 3.2+ equivalent with identical behavior
- `stdout.decode().strip() or None` — explicit falsy guard so exit-0 with empty stdout writes a stub rather than an empty session file
- `proc.communicate()` called after `killpg` — without this the killed process becomes a zombie in the process table
- `write_stub_summary` delegates to `write_session_file` — single write path guarantees stubs have identical frontmatter format, no duplication
- `EXTRACTION_TIMEOUT_SECONDS = 85` as module-level constant — single source of truth referenced by Popen call and verified in tests

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `run_claude_extraction`, `write_session_file`, and `write_stub_summary` ready for use in Phase 2 Plan 03 (full capture command wiring)
- All failure paths (timeout, error, empty output) produce a stub file — no silent failures in the pipeline
- No blockers

## Self-Check: PASSED

- FOUND: `src/thehook/capture.py`
- FOUND: `tests/test_capture.py`
- FOUND: `.planning/phases/02-capture/02-02-SUMMARY.md`
- FOUND commit: `a49729f` (test RED)
- FOUND commit: `58cdcb8` (feat GREEN)

---
*Phase: 02-capture*
*Completed: 2026-02-23*
