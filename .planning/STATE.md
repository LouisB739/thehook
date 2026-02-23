# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-23)

**Core value:** The agent remembers what matters — conventions, decisions, and project history — without the developer lifting a finger.
**Current focus:** Phase 2 — Capture (in progress)

## Current Position

Phase: 2 of 4 (Capture)
Plan: 3 of 3 in current phase
Status: Plan 02-03 complete — Extraction prompt, run_capture orchestration, and CLI capture command (Phase 2 complete)
Last activity: 2026-02-23 — Plan 02-03 complete: EXTRACTION_PROMPT_TEMPLATE, run_capture, CLI capture subcommand (26 tests)

Progress: [█████░░░░░] 56%

## Performance Metrics

**Velocity:**
- Total plans completed: 5
- Average duration: 2 min
- Total execution time: 11 min

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-setup | 2 | 4 min | 2 min |
| 02-capture | 3 | 7 min | 2.3 min |

**Recent Trend:**
- Last 5 plans: 2 min
- Trend: stable

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Pre-planning]: Python CLI over Ruby/TS — ChromaDB is native Python
- [Pre-planning]: Markdown + ChromaDB dual storage — markdown is source of truth, ChromaDB is disposable index
- [Pre-planning]: CLI headless (`claude -p`) as LLM engine — zero config, uses existing subscription
- [Pre-planning]: Per-project `.thehook/` storage — project isolation, no cross-contamination
- [01-01]: Config file is thehook.yaml at project root (not .thehook/config.yaml) per SETUP-03
- [01-01]: deepcopy(DEFAULT_CONFIG) ensures no shared mutable state between load_config calls
- [01-01]: hatchling build backend with src/ layout; entry point thehook = thehook.cli:main
- [01-02]: SessionStart matcher set to "startup" only — prevents double-injection on session resume
- [01-02]: HOOK_CONFIG as module-level constant for testability and reuse
- [01-02]: init_project() writes hooks key unconditionally, preserving all other existing settings keys
- [02-01]: isinstance(raw_content, list) branch detects assistant content shape — more robust than role-based check
- [02-01]: Text blocks joined with \n (not \n\n) — preserves natural multi-block assistant message flow
- [02-01]: read_hook_input returns {} on error — graceful degradation over exception propagation
- [02-01]: MAX_TRANSCRIPT_CHARS = 50_000 as module-level constant — single source of truth for context limit
- [02-02]: start_new_session=True used (not preexec_fn=os.setsid) — thread-safe Python 3.2+ equivalent
- [02-02]: stdout.decode().strip() or None — falsy empty stdout treated as extraction failure, not empty file
- [02-02]: proc.communicate() called after killpg — mandatory zombie reap for resource cleanup
- [02-02]: write_stub_summary delegates to write_session_file — single write path, identical frontmatter format
- [02-02]: EXTRACTION_TIMEOUT_SECONDS = 85 as module-level constant — single source of truth
- [02-03]: EXTRACTION_PROMPT_TEMPLATE uses 'conventions' and 'decisions' as extraction targets — excludes 'observations' per CAPT-06
- [02-03]: run_capture uses cwd from hook input (not os.getcwd()) — hook may be invoked from a different shell directory
- [02-03]: Empty transcript produces stub with reason='empty transcript' — distinguishes from timeout in stub content
- [02-03]: run_capture returns silently on bad JSON stdin — no exception propagation to hook runner
- [02-03]: CLI capture command has no options — all input comes from stdin, matching SessionEnd hook invocation pattern

### Pending Todos

None yet.

### Blockers/Concerns

- [02-01 RESOLVED]: Transcript JSONL content shape confirmed with fixture — string for user, array-of-blocks for assistant; research was accurate

## Session Continuity

Last session: 2026-02-23
Stopped at: Completed 02-03-PLAN.md — Extraction prompt, run_capture orchestration, CLI capture command (26 tests, 40 total) — Phase 2 complete
Resume file: None
