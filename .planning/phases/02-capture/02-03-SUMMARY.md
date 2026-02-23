---
phase: 02-capture
plan: 03
subsystem: capture
tags: [extraction-prompt, orchestration, cli, tdd, graceful-degradation, stdin, sessionend]

# Dependency graph
requires:
  - phase: 02-capture/02-01
    provides: parse_transcript, read_hook_input, assemble_transcript_text, MAX_TRANSCRIPT_CHARS
  - phase: 02-capture/02-02
    provides: run_claude_extraction, write_session_file, write_stub_summary, EXTRACTION_TIMEOUT_SECONDS
provides:
  - Complete capture pipeline via run_capture (stdin -> parse -> extract -> write session file)
  - EXTRACTION_PROMPT_TEMPLATE targeting conventions and decisions (CAPT-06 compliant)
  - CLI capture subcommand registered in thehook CLI
  - Graceful degradation on empty transcript (stub with reason='empty transcript') and extraction failure (stub with reason='timeout')
affects: [03-storage, 04-retrieval]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "TDD RED/GREEN — failing import on missing symbols, then full implementation"
    - "Extraction prompt design — 4-section structured output (SUMMARY/CONVENTIONS/DECISIONS/GOTCHAS), no 'observations'"
    - "run_capture orchestration — single function reads stdin, calls parse/extract/write, returns silently on bad input"
    - "Graceful degradation — every code path produces a session file (stub or full)"
    - "cwd from hook input used as project_dir — avoids reliance on shell cwd at hook invocation time"

key-files:
  created: []
  modified:
    - src/thehook/capture.py
    - src/thehook/cli.py
    - tests/test_capture.py

key-decisions:
  - "EXTRACTION_PROMPT_TEMPLATE uses 'conventions' and 'decisions' as extraction targets — excludes 'observations' per CAPT-06"
  - "run_capture uses cwd from hook input (not os.getcwd()) — hook may be invoked from a different shell directory"
  - "Empty transcript path produces stub with reason='empty transcript' — distinguishes from timeout in stub content"
  - "run_capture returns silently on bad JSON stdin — no exception propagation to hook runner"
  - "CLI capture command has no options — all input comes from stdin, matching SessionEnd hook invocation pattern"

patterns-established:
  - "Pattern: run_capture as thin orchestrator — reads hook_input, delegates to existing primitives, writes result"
  - "Pattern: Extraction prompt with 4-section forced output — SUMMARY/CONVENTIONS/DECISIONS/GOTCHAS ensures parseable structure"

requirements-completed: [CAPT-04, CAPT-06]

# Metrics
duration: 2min
completed: 2026-02-23
---

# Phase 2 Plan 03: Extraction Prompt and Capture Orchestration Summary

**Extraction prompt targeting conventions/decisions (not observations), run_capture orchestration wiring stdin-to-session-file, and CLI capture subcommand — completing the full SessionEnd capture pipeline with 26 TDD tests**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-23T21:51:05Z
- **Completed:** 2026-02-23T21:53:07Z
- **Tasks:** 2 (RED + GREEN)
- **Files modified:** 3

## Accomplishments

- `EXTRACTION_PROMPT_TEMPLATE` defines the 4-section structured extraction format (SUMMARY, CONVENTIONS, DECISIONS, GOTCHAS), explicitly targets conventions and decisions, and contains no mention of "observations" (CAPT-06)
- `run_capture` orchestrates the full SessionEnd pipeline: reads JSON from stdin, calls `parse_transcript`, `assemble_transcript_text`, `run_claude_extraction`, and `write_session_file` or `write_stub_summary` on all failure paths
- `thehook capture` CLI subcommand registered and callable; delegates to `run_capture` with no arguments (input from stdin)
- Every code path produces a session file: empty transcript -> stub with reason='empty transcript', extraction failure -> stub with reason='timeout', bad stdin -> silent return
- 8 new TDD tests added (26 total capture tests): 3 for prompt constraints, 4 for orchestration, 1 for CLI — all pass; 40/40 full suite passes

## Task Commits

Each task was committed atomically:

1. **Task 1: RED — Write failing tests for extraction prompt, run_capture, and CLI command** - `acdbd46` (test)
2. **Task 2: GREEN — Implement extraction prompt, run_capture orchestration, and CLI capture command** - `37adb6a` (feat)

**Plan metadata:** (docs commit below)

_Note: TDD tasks have separate RED (test) and GREEN (feat) commits_

## Files Created/Modified

- `src/thehook/capture.py` - Added `EXTRACTION_PROMPT_TEMPLATE` (40-line extraction prompt) and `run_capture()` (orchestration function)
- `src/thehook/cli.py` - Added `capture` subcommand delegating to `run_capture`
- `tests/test_capture.py` - 8 new tests: prompt constraints (3), run_capture orchestration (4), CLI integration (1); import extended to include new symbols

## Decisions Made

- `EXTRACTION_PROMPT_TEMPLATE` explicitly avoids "observations" — targets only concrete, reusable knowledge (conventions, decisions, gotchas) per CAPT-06 requirement
- `run_capture` uses `cwd` from hook input as the project directory — the hook runner may invoke from a different working directory, so relying on `os.getcwd()` would be unreliable (Pitfall 6 from research)
- Empty transcript path (file does not exist) produces a stub with `reason='empty transcript'` — distinguishes from extraction timeout in stub content, making failure reason visible in the file
- `run_capture` returns silently on invalid JSON stdin — no exception propagated to the hook runner (consistent with `read_hook_input` returning `{}` on error)
- `capture` CLI command has no options — all input comes from stdin, matching how the SessionEnd hook invokes the command

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Complete capture pipeline (`thehook capture`) is ready for real SessionEnd hook invocation testing
- `run_capture`, `EXTRACTION_PROMPT_TEMPLATE`, and all supporting functions ready for Phase 3 (storage indexing)
- All 40 tests pass with no regressions
- No blockers

## Self-Check: PASSED

- FOUND: `src/thehook/capture.py`
- FOUND: `src/thehook/cli.py`
- FOUND: `tests/test_capture.py`
- FOUND: `.planning/phases/02-capture/02-03-SUMMARY.md`
- FOUND commit: `acdbd46` (test RED)
- FOUND commit: `37adb6a` (feat GREEN)

---
*Phase: 02-capture*
*Completed: 2026-02-23*
