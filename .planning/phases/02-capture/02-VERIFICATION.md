---
phase: 02-capture
verified: 2026-02-23T22:10:00Z
status: passed
score: 5/5 must-haves verified
re_verification: false
---

# Phase 2: Capture Verification Report

**Phase Goal:** At every Claude Code session end, conversation knowledge is automatically extracted and ready to store
**Verified:** 2026-02-23T22:10:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (from Phase Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | After a Claude Code session ends, the SessionEnd hook reads `transcript_path` from stdin JSON and parses the JSONL transcript without error | VERIFIED | `read_hook_input()` reads stdin JSON; `parse_transcript()` reads JSONL via `Path.read_text().splitlines()`; both tested and passing |
| 2 | The extraction produces a structured markdown document with SUMMARY, CONVENTIONS, DECISIONS, and GOTCHAS sections — not raw transcript content | VERIFIED | `EXTRACTION_PROMPT_TEMPLATE` contains all four section headers; `write_session_file` writes the markdown body; `write_stub_summary` writes all four sections on failure |
| 3 | Both user message content (string) and assistant message content (array of blocks) are parsed correctly | VERIFIED | `isinstance(raw_content, str)` branch for user; `isinstance(raw_content, list)` branch for assistant; `tool_use` blocks explicitly skipped; 3 dedicated tests pass |
| 4 | If `claude -p` hangs or exceeds the 85-second timeout, a stub summary is written with transcript metadata and the hook exits cleanly — no silent failures | VERIFIED | `TimeoutExpired` caught; `os.killpg(os.getpgid(proc.pid), signal.SIGKILL)` called; `proc.communicate()` reaps zombie; `write_stub_summary` called with `reason="timeout"`; test `test_run_claude_extraction_returns_none_on_timeout` passes |
| 5 | The extraction prompt targets conventions and architecture decisions specifically, not general observations | VERIFIED | `EXTRACTION_PROMPT_TEMPLATE` contains "conventions" and "decisions"; does NOT contain "observations" (grep confirmed); `test_extraction_prompt_excludes_observations` passes |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/thehook/capture.py` | Transcript parsing, extraction, session file writing, capture orchestration | VERIFIED | 293 lines; exports `read_hook_input`, `parse_transcript`, `assemble_transcript_text`, `run_claude_extraction`, `write_session_file`, `write_stub_summary`, `run_capture`, `EXTRACTION_PROMPT_TEMPLATE`; all substantive |
| `tests/test_capture.py` | TDD tests for all capture behaviors | VERIFIED | 364 lines; 26 tests; all pass; covers parsing, extraction subprocess, session file writing, orchestration, CLI |
| `tests/fixtures/sample_transcript.jsonl` | Minimal JSONL fixture with system, user, and assistant records | VERIFIED | 4 lines; system record (to be skipped), user string content, two assistant array-of-blocks records (one with tool_use) |
| `src/thehook/cli.py` | `capture` CLI subcommand | VERIFIED | `@main.command()` `capture()` function present; delegates to `run_capture`; `thehook capture --help` works |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `capture.py::parse_transcript` | `tests/fixtures/sample_transcript.jsonl` | `path.read_text().splitlines()` | WIRED | Line 84: `for line in path.read_text().splitlines()` |
| `capture.py::run_claude_extraction` | `subprocess.Popen` | `start_new_session=True` | WIRED | Line 172: `start_new_session=True` in Popen call |
| `capture.py::run_claude_extraction` | `os.killpg` | `TimeoutExpired` handler kills process group | WIRED | Line 179: `os.killpg(os.getpgid(proc.pid), signal.SIGKILL)` |
| `cli.py::capture` | `capture.py::run_capture` | CLI command calls run_capture | WIRED | Line 26 of cli.py: `from thehook.capture import run_capture` then `run_capture()` |
| `capture.py::run_capture` | `parse_transcript` | Orchestration calls parsing | WIRED | Line 280: `messages = parse_transcript(transcript_path)` |
| `capture.py::run_capture` | `run_claude_extraction` | Orchestration calls extraction | WIRED | Line 288: `result = run_claude_extraction(prompt)` |
| `capture.py::run_capture` | `write_session_file` | Orchestration writes output | WIRED | Line 290: `write_session_file(sessions_dir, session_id, transcript_path, result)` |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| CAPT-01 | 02-01 | SessionEnd hook reads `transcript_path` from stdin JSON and parses JSONL transcript | SATISFIED | `read_hook_input()` reads stdin JSON; `parse_transcript()` parses JSONL; tested |
| CAPT-02 | 02-01 | JSONL parser handles string content (user) and array-of-blocks content (assistant) | SATISFIED | `isinstance` branching on `raw_content`; `tool_use` blocks skipped; 3 parse tests pass |
| CAPT-03 | 02-02 | LLM extraction calls `claude -p` via subprocess (Popen + killpg process group, 85s timeout) | SATISFIED | `subprocess.Popen(["claude", "-p", prompt, "--tools", ""], start_new_session=True)`; `communicate(timeout=85)`; `killpg(SIGKILL)` on timeout |
| CAPT-04 | 02-03 | Extraction produces structured markdown: session summary, conventions, architecture decisions | SATISFIED | `EXTRACTION_PROMPT_TEMPLATE` with 4 sections; `write_session_file` writes full markdown; `run_capture` orchestrates end-to-end |
| CAPT-05 | 02-02 | On timeout or LLM failure, stub summary written with raw transcript metadata | SATISFIED | `write_stub_summary` called on `None` result, timeout, empty transcript; all 4 sections written with failure reason and message count |
| CAPT-06 | 02-03 | Extraction prompt targets specific knowledge types (conventions, ADRs) — not raw observation capture | SATISFIED | "conventions" and "decisions" appear in prompt; "observations" absent (grep confirmed); test `test_extraction_prompt_excludes_observations` passes |

All 6 required requirement IDs are accounted for across three plans (02-01, 02-02, 02-03). No orphaned or unmapped requirements for Phase 2.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None | — | — | — | — |

No TODO/FIXME/placeholder comments found. No `NotImplementedError` stubs remain. No empty return bodies. The `return {}` calls at lines 57 and 60 in `capture.py` are intentional graceful degradation in `read_hook_input()`, not stubs.

### Human Verification Required

#### 1. Real SessionEnd Hook Invocation

**Test:** Run `thehook init` in a test project, start a Claude Code session, perform some work (establish a convention, make a decision), end the session, inspect `.thehook/sessions/` for a generated markdown file.
**Expected:** A `.md` file exists with YAML frontmatter (`session_id`, `timestamp`, `transcript_path`) and structured sections (SUMMARY, CONVENTIONS, DECISIONS, GOTCHAS) containing extracted knowledge — not raw transcript content.
**Why human:** Requires a live Claude Code session. `claude -p` behavior with a real transcript cannot be verified programmatically without executing the full pipeline end-to-end.

#### 2. Timeout Behavior Under Real Conditions

**Test:** If `claude -p` is available, verify the 85-second timeout actually kills the subprocess cleanly and does not leave zombie processes.
**Expected:** Process group killed within 85 seconds; `.thehook/sessions/` contains a stub file; no orphaned `claude` processes remain.
**Why human:** Subprocess kill behavior and zombie reaping require OS-level inspection (`ps aux`) during actual timeout; cannot be reliably tested without a real hanging process.

### Gaps Summary

No gaps. All observable truths verified. All artifacts are substantive and wired. All 6 requirement IDs satisfied. Full test suite (40 tests) passes with no regressions.

---

## Test Run Evidence

```
40 passed in 0.23s (tests/ full suite)
26 passed in 0.15s (tests/test_capture.py only)
```

Commit history covering this phase:
- `5a85d64` — test: RED phase for transcript parsing (Plan 01)
- `9dfd51e` — feat: GREEN — implement transcript parsing (Plan 01)
- `a49729f` — test: RED phase for extraction subprocess (Plan 02)
- `58cdcb8` — feat: GREEN — implement extraction subprocess (Plan 02)
- `acdbd46` — test: RED phase for extraction prompt and orchestration (Plan 03)
- `37adb6a` — feat: GREEN — implement extraction prompt, run_capture, CLI command (Plan 03)

---

_Verified: 2026-02-23T22:10:00Z_
_Verifier: Claude (gsd-verifier)_
