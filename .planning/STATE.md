# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-23)

**Core value:** The agent remembers what matters — conventions, decisions, and project history — without the developer lifting a finger.
**Current focus:** Phase 4 — Retrieval (complete)

## Current Position

Phase: 4 of 4 (Retrieval)
Plan: 2 of 2 in current phase
Status: Plan 04-02 complete — retrieve and recall CLI subcommands wired, 67 tests green, all v1 requirements satisfied
Last activity: 2026-02-24 — Plan 04-02 complete: CLI retrieve and recall subcommands with integration tests

Progress: [██████████] 100%

## Performance Metrics

**Velocity:**
- Total plans completed: 7
- Average duration: 3 min
- Total execution time: 22 min

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-setup | 2 | 4 min | 2 min |
| 02-capture | 3 | 7 min | 2.3 min |

**Recent Trend:**
- Last 5 plans: 2 min
- Trend: stable

*Updated after each plan completion*
| Phase 03-storage P01 | 13 | 2 tasks | 4 files |
| Phase 03-storage P02 | 3 | 2 tasks | 3 files |
| Phase 04-retrieval P01 | 7 | 1 task | 2 files |
| Phase 04-retrieval P02 | 4 | 2 tasks | 2 files |

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
- [Phase 03-storage]: chromadb>=1.0 added to pyproject.toml; lazy imports inside function bodies to avoid ~1s startup cost
- [Phase 03-storage]: upsert used in index_session_file (idempotent), add used in reindex (no duplicates after drop)
- [Phase 03-storage]: filename stem as fallback ChromaDB ID when session_id absent in frontmatter — stem is unique by write_session_file construction
- [Phase 03-storage]: PyYAML parses ISO 8601 timestamps to datetime objects; use isoformat() to preserve T-separator in ChromaDB metadata
- [Phase 03-storage]: EphemeralClient shares singleton backend in tests; fixture deletes collection pre/post test for isolation
- [03-02]: try/except Exception wraps entire import+call in run_capture — catches ImportError (chromadb absent) and runtime errors; capture never crashes
- [03-02]: project_dir = Path(cwd) in run_capture indexing calls — reuses hook input cwd, not os.getcwd()
- [03-02]: patch('thehook.storage.index_session_file') targets module attribute — correct for lazy import inside function body
- [04-01]: get_collection() used in query_sessions (not get_or_create) — avoids creating empty collection on first query
- [04-01]: min(n_results, count) caps ChromaDB query to prevent ValueError when n_results exceeds collection count
- [04-01]: Static query string 'project conventions decisions gotchas architecture' for SessionStart — no user input at session start
- [04-01]: print(json.dumps(output), flush=True) — flush prevents dropped output if hook process is killed
- [04-01]: Entire run_retrieve() wrapped in try/except Exception: pass — hook must never crash
- [04-01]: Token budget loaded from config via load_config(project_dir) — respects user's thehook.yaml setting
- [04-02]: retrieve CLI command has no options — all input from stdin, matching capture command pattern
- [04-02]: recall uses format_context() for output — same function as run_retrieve, consistent formatting
- [04-02]: CliRunner() without mix_stderr — Click version does not support that parameter; matches existing test patterns

### Pending Todos

None yet.

### Blockers/Concerns

- [02-01 RESOLVED]: Transcript JSONL content shape confirmed with fixture — string for user, array-of-blocks for assistant; research was accurate

## Session Continuity

Last session: 2026-02-24
Stopped at: Completed 04-02-PLAN.md — retrieve and recall CLI subcommands, 4 CLI integration tests, 67 total tests green. All v1 requirements complete.
Resume file: None
