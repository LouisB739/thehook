---
phase: 03-storage
plan: 02
subsystem: database
tags: [chromadb, capture, cli, integration, pipeline]

# Dependency graph
requires:
  - phase: 03-01
    provides: index_session_file(), reindex() in storage.py — fully tested and ready to wire
  - phase: 02-03
    provides: run_capture() orchestration with write_session_file/write_stub_summary write paths

provides:
  - thehook reindex CLI subcommand (--path option, prints "Reindexed N session files.")
  - run_capture() auto-indexes every session via index_session_file after every write (success, timeout stub, empty-transcript stub)
  - graceful degradation: ChromaDB failure in run_capture is swallowed — capture pipeline never crashes
  - 4 new integration tests covering all write paths and error swallowing

affects:
  - 03-03 (if any; phase 3 is now complete with storage wired into capture)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Lazy chromadb import inside try block in run_capture — ImportError caught alongside runtime exceptions, enabling capture-without-chromadb graceful degradation
    - try/except Exception: pass pattern wrapping index_session_file calls — storage never propagates to pipeline

key-files:
  created: []
  modified:
    - src/thehook/capture.py (index_session_file calls after all three write paths)
    - src/thehook/cli.py (reindex subcommand)
    - tests/test_capture.py (4 new integration tests)

key-decisions:
  - "chromadb>=1.0 was already in pyproject.toml from plan 03-01 — no change needed in Task 1"
  - "try/except Exception wraps the entire import+call block — catches ImportError (chromadb absent) and all runtime exceptions in one guard"
  - "project_dir = Path(cwd) reuses the cwd already extracted from hook_input — does not call os.getcwd() per plan spec"
  - "patch('thehook.storage.index_session_file') used in tests — patches the module attribute so the lazy import inside try sees the mock"
  - "test_run_capture_stub_also_indexes verifies stub file content contains 'timeout' as a proxy for the correct write path"

patterns-established:
  - "Lazy import inside try block: from module import func inside try: ... except Exception: pass — catches both import and runtime errors"
  - "CLI reindex follows init pattern exactly: @main.command(), @click.option('--path'), Path(path).resolve(), lazy import, call, echo"

requirements-completed: [STOR-01, STOR-03, STOR-05]

# Metrics
duration: 3min
completed: 2026-02-24
---

# Phase 03 Plan 02: Storage Integration Summary

**reindex CLI command and ChromaDB auto-indexing wired into run_capture after every session write — graceful degradation via try/except, 4 new tests, 54 total green**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-24T09:12:54Z
- **Completed:** 2026-02-24T09:15:54Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- `thehook reindex --path <dir>` CLI subcommand registered — calls `storage.reindex()` with lazy import, prints "Reindexed N session files."
- `run_capture()` now calls `index_session_file()` after all three write paths: extraction success, timeout stub, empty-transcript stub
- ChromaDB exceptions in `run_capture` are caught by `try/except Exception: pass` — capture pipeline never crashes due to indexing
- 4 new integration tests: index called after extraction, index exception swallowed, stub also indexed, reindex CLI output verified

## Task Commits

Each task was committed atomically:

1. **Task 1: Add chromadb dependency and wire reindex CLI command** - `dfdeeb2` (feat)
2. **Task 2: Integrate index_session_file into run_capture and add tests** - `7144bc4` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `src/thehook/cli.py` - Added `reindex` subcommand with `--path` option; lazy import of `storage.reindex`
- `src/thehook/capture.py` - Added `index_session_file` call (lazy import in try/except) after all three `write_session_file`/`write_stub_summary` invocations
- `tests/test_capture.py` - 4 new integration tests covering storage wiring

## Decisions Made

- **chromadb already present:** `chromadb>=1.0` was already added to `pyproject.toml` in plan 03-01, so Task 1 only required the CLI command addition — no dependency change needed.
- **try/except wraps entire import+call:** The entire `from thehook.storage import index_session_file` + call is inside a single `try/except Exception: pass`. This means both `ImportError` (chromadb not installed) and any runtime ChromaDB error are silently swallowed — the plan's stated requirement for graceful degradation when chromadb is absent.
- **project_dir from cwd:** `project_dir = Path(cwd)` reuses the `cwd` extracted from `hook_input` at the top of `run_capture()` — consistent with plan 02-03 decision to use hook input cwd rather than `os.getcwd()`.
- **Test mocking via patch:** `patch("thehook.storage.index_session_file", fake_index)` patches at the module level. Since `capture.py` does a lazy `from thehook.storage import index_session_file` inside the try block, the patch must target `thehook.storage.index_session_file` (where the object lives), not `thehook.capture.index_session_file` (a name that doesn't exist at module level).

## Deviations from Plan

None - plan executed exactly as written. The `chromadb>=1.0` dependency was already present from plan 03-01 (noted in 03-01-SUMMARY.md key-files/modified), so pyproject.toml required no change in this plan.

## Issues Encountered

None. The lazy import pattern established in 03-01 (with the EphemeralClient singleton and ONNX cache redirect already set up in conftest.py) meant all tests passed on first run.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 03-storage is complete: storage module built (03-01), wired into CLI and capture pipeline (03-02)
- All 54 tests pass with no regressions
- The full pipeline is operational: `thehook capture` (via SessionEnd hook) → `run_capture()` → `write_session_file()` → `index_session_file()` → ChromaDB
- `thehook reindex` is available for rebuilding the index from existing session files

---
*Phase: 03-storage*
*Completed: 2026-02-24*

## Self-Check: PASSED

- FOUND: `src/thehook/cli.py`
- FOUND: `src/thehook/capture.py`
- FOUND: `tests/test_capture.py`
- FOUND: `.planning/phases/03-storage/03-02-SUMMARY.md`
- FOUND: commit `dfdeeb2` (Task 1 — reindex CLI command)
- FOUND: commit `7144bc4` (Task 2 — capture pipeline integration)
