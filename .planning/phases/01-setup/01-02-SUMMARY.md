---
phase: 01-setup
plan: 02
subsystem: infra
tags: [python, click, pytest, json, hooks, claude-code]

# Dependency graph
requires:
  - phase: 01-setup/01-01
    provides: Click CLI skeleton, test infrastructure (pytest, conftest, tmp_project fixture)
provides:
  - thehook init command creating .thehook/sessions/, .thehook/knowledge/, .thehook/chromadb/
  - Hook registration in .claude/settings.local.json (SessionEnd + SessionStart)
  - init_project() function in src/thehook/init.py
  - 9 TDD tests covering init logic and CLI integration
affects: [02-capture, 03-storage, 04-retrieval]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - HOOK_CONFIG dict with nested structure for Claude Code hooks format
    - idempotent directory creation with mkdir(parents=True, exist_ok=True)
    - settings.local.json merge pattern (read existing JSON, update hooks key, write back)
    - Click subcommand pattern with --path option defaulting to "."
    - CLI testing via CliRunner with isolated_filesystem() for default-path tests

key-files:
  created:
    - src/thehook/init.py
    - tests/test_init.py
  modified:
    - src/thehook/cli.py

key-decisions:
  - "SessionStart matcher set to 'startup' only (not 'resume') to prevent double-injection on session resume"
  - "HOOK_CONFIG defined as module-level constant for testability and reuse"
  - "init_project() writes hooks key unconditionally, preserving all other existing settings keys"

patterns-established:
  - "Init pattern: mkdir(parents=True, exist_ok=True) for all subdirectories ensures idempotency"
  - "Settings merge: read existing JSON or default to {}, set hooks key, write back with indent=2"
  - "CLI subcommand: import init_project inside command function for lazy loading"

requirements-completed: [SETUP-01, SETUP-02]

# Metrics
duration: 2min
completed: 2026-02-23
---

# Phase 1 Plan 02: Init Command Summary

**`thehook init` command wiring .thehook/ directory structure and registering SessionEnd/SessionStart Claude Code hooks in settings.local.json with 9 passing TDD tests**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-23T21:14:48Z
- **Completed:** 2026-02-23T21:16:30Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- `thehook init --path <dir>` creates `.thehook/sessions/`, `.thehook/knowledge/`, `.thehook/chromadb/` (SETUP-02)
- Registers SessionEnd hook (`thehook capture`, async=True, timeout=120) and SessionStart hook (`thehook retrieve`, timeout=30, matcher="startup") in `.claude/settings.local.json` (SETUP-01)
- Existing settings preserved on re-init; command is fully idempotent
- 9 tests pass (6 unit + 3 CLI integration); combined with config tests 14 total pass

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement init command with TDD** - `fa2a236` (feat)
2. **Task 2: Wire init into CLI and run end-to-end verification** - `ba702fc` (feat)

**Plan metadata:** (docs commit — see below)

## Files Created/Modified

- `src/thehook/init.py` - `init_project(project_dir)` function + `HOOK_CONFIG` constant
- `src/thehook/cli.py` - Added `init` subcommand with `--path` option; imports and calls `init_project()`
- `tests/test_init.py` - 9 tests: 6 unit (TDD) + 3 CLI integration via CliRunner

## Decisions Made

- SessionStart matcher is `"startup"` only — prevents double-injection when Claude Code resumes a session (as flagged in STATE.md blockers)
- `HOOK_CONFIG` defined as a module-level constant so tests can import and validate it directly
- Settings merge writes hooks key unconditionally: any prior hooks config is replaced on re-init (idempotent, predictable)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed unsupported `mix_stderr` kwarg from CliRunner**
- **Found during:** Task 2 (Wire init into CLI)
- **Issue:** Plan spec used `CliRunner(mix_stderr=False)` but the installed Click version does not support this kwarg, causing `TypeError`
- **Fix:** Changed to `CliRunner()` without the kwarg; test behavior unaffected
- **Files modified:** `tests/test_init.py`
- **Verification:** `test_cli_init_default_path` passes; full suite 14/14 green
- **Committed in:** `ba702fc` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — bug in plan spec)
**Impact on plan:** Fix was necessary; no scope change.

## Issues Encountered

None beyond the auto-fixed deviation above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 1 complete: package installs, config loads, `thehook init` wires hooks and creates directory structure
- `src/thehook/init.py` exposes `init_project()` ready for import by future commands
- `.thehook/sessions/`, `.thehook/knowledge/`, `.thehook/chromadb/` structure ready for Phase 2 capture logic
- All 4 Phase 1 ROADMAP success criteria satisfied (directory creation, hook registration, config no-yaml, config custom yaml)

---
*Phase: 01-setup*
*Completed: 2026-02-23*

## Self-Check: PASSED

- FOUND: src/thehook/init.py
- FOUND: src/thehook/cli.py
- FOUND: tests/test_init.py
- FOUND: .planning/phases/01-setup/01-02-SUMMARY.md
- FOUND commit: fa2a236 (Task 1)
- FOUND commit: ba702fc (Task 2)
