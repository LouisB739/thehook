---
phase: 02-capture
plan: 01
subsystem: capture
tags: [jsonl, transcript, parsing, stdlib, tdd]

# Dependency graph
requires:
  - phase: 01-setup
    provides: cli.py entry point, pyproject.toml with pytest config, conftest.py with tmp_project fixture
provides:
  - JSONL transcript parsing via parse_transcript (handles user string content and assistant array-of-blocks)
  - Hook stdin reading via read_hook_input
  - Transcript text assembly with truncation via assemble_transcript_text
  - tests/fixtures/sample_transcript.jsonl reusable JSONL fixture
affects: [02-capture plans 02+, 03-storage, 04-retrieval]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "TDD RED/GREEN — skeleton with NotImplementedError stubs, failing tests, then implementation"
    - "JSONL parsing with json.loads per line — no library, just Path.read_text().splitlines()"
    - "Content-type branching — isinstance(raw_content, str) for user, isinstance(raw_content, list) for assistant"
    - "Transcript truncation — keep last max_chars characters, prefix with ...[truncated]..."

key-files:
  created:
    - src/thehook/capture.py
    - tests/test_capture.py
    - tests/fixtures/sample_transcript.jsonl
  modified: []

key-decisions:
  - "isinstance(raw_content, list) branch used for assistant content — handles both string (user) and array-of-blocks (assistant) without trying to detect role from outer record"
  - "text blocks joined with \\n (not \\n\\n) — preserves natural multi-block assistant message flow"
  - "read_hook_input returns empty dict on any error (JSONDecodeError or empty stdin) — graceful degradation over exception propagation"
  - "MAX_TRANSCRIPT_CHARS = 50_000 as module-level constant — single source of truth for context limit"

patterns-established:
  - "Pattern: JSONL transcript parsing — json.loads per line, skip empty/invalid lines, filter by type field"
  - "Pattern: Content shape branching — isinstance check on raw_content before extraction"
  - "Pattern: Truncation with recency bias — keep last N chars, prepend ...[truncated]... marker"

requirements-completed: [CAPT-01, CAPT-02]

# Metrics
duration: 2min
completed: 2026-02-23
---

# Phase 2 Plan 01: Transcript Parsing Summary

**JSONL transcript parser using stdlib-only content-type branching — handles user string content and assistant array-of-blocks with tool_use skipping, 9 TDD tests passing**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-23T21:41:15Z
- **Completed:** 2026-02-23T21:43:40Z
- **Tasks:** 2 (RED + GREEN)
- **Files modified:** 3

## Accomplishments

- `parse_transcript` correctly handles both JSONL content shapes: plain string for user messages, array-of-blocks for assistant messages (text blocks extracted, tool_use/tool_result skipped)
- `read_hook_input` reads JSON from stdin with graceful empty dict fallback on error
- `assemble_transcript_text` joins messages with `[ROLE]:` labels and truncates to `max_chars` with recency bias
- 9 TDD tests cover all behaviors including edge cases (nonexistent file, empty file, truncation, multi-block joining)
- Full suite of 23 tests passes with no regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: RED — Write failing tests for transcript parsing and hook input reading** - `5a85d64` (test)
2. **Task 2: GREEN — Implement transcript parsing to pass all tests** - `9dfd51e` (feat)

**Plan metadata:** (docs commit below)

_Note: TDD tasks have separate RED (test) and GREEN (feat) commits_

## Files Created/Modified

- `src/thehook/capture.py` - Three parsing functions: `read_hook_input`, `parse_transcript`, `assemble_transcript_text`
- `tests/test_capture.py` - 9 tests covering all parsing behaviors and edge cases
- `tests/fixtures/sample_transcript.jsonl` - Minimal JSONL fixture with system (skipped), user (string), and two assistant (array-of-blocks) records

## Decisions Made

- `isinstance(raw_content, list)` branch used to detect assistant content shape — checking the content type directly is more robust than checking the role field
- Text blocks joined with `\n` (not `\n\n`) — preserves natural multi-block flow in assembled text
- `read_hook_input` returns `{}` on error (JSONDecodeError, empty input) rather than raising — allows callers to handle gracefully
- `MAX_TRANSCRIPT_CHARS = 50_000` as a module-level constant — single source of truth for downstream plans that call `assemble_transcript_text`

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- `pytest-asyncio` was installed system-wide and caused an `INTERNALERROR` when collecting tests. Resolved by uninstalling it (`pip uninstall pytest-asyncio`). This is a pre-existing system-level interference, not caused by this plan's code.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `parse_transcript`, `read_hook_input`, and `assemble_transcript_text` are ready for use in Phase 2 Plan 02 (LLM extraction via `claude -p`)
- `tests/fixtures/sample_transcript.jsonl` is reusable as a fixture for all subsequent capture plan tests
- No blockers

---
*Phase: 02-capture*
*Completed: 2026-02-23*
