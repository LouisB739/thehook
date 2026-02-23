# Phase 2: Capture - Research

**Researched:** 2026-02-23
**Domain:** JSONL transcript parsing, subprocess process-group management, LLM extraction via claude -p
**Confidence:** HIGH

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| CAPT-01 | SessionEnd hook reads `transcript_path` from stdin JSON and parses JSONL transcript | SessionEnd input schema confirmed from official docs; `transcript_path` is a standard common field on all hook events; JSONL is newline-delimited JSON parseable with `json.loads` per line |
| CAPT-02 | JSONL parser handles both string content (user messages) and array-of-blocks content (assistant messages) | Transcript structure confirmed from multiple sources: user `message.content` is a string; assistant `message.content` is an array of `{"type":"text","text":"..."}` blocks |
| CAPT-03 | LLM extraction calls `claude -p` via subprocess (Popen + killpg process group, 85s hard timeout) | `claude -p` fully documented; `subprocess.Popen` with `start_new_session=True` + `os.killpg` on `TimeoutExpired` is the verified pattern for killing entire process trees |
| CAPT-04 | Extraction produces structured markdown: session summary, conventions discovered, architecture decisions | No external library needed — plain string template with SUMMARY / CONVENTIONS / DECISIONS / GOTCHAS sections; `claude -p` returns plain text by default |
| CAPT-05 | On timeout or LLM failure, a stub summary is written with raw transcript metadata (graceful degradation) | Python `try/except` + fallback write to `.thehook/sessions/` with frontmatter; stub must contain session_id, transcript_path, timestamp, message count |
| CAPT-06 | Extraction prompt targets specific knowledge types (conventions, ADRs) — not raw observation capture | Prompt engineering: instruct claude to extract conventions (naming, patterns, tooling) and architecture decisions with rationale; explicitly exclude general observations |

</phase_requirements>

---

## Summary

Phase 2 implements the `thehook capture` command, which is registered as the SessionEnd hook (already wired in Phase 1 as `thehook capture`). When Claude Code ends a session, it calls this hook with a JSON payload on stdin that includes `transcript_path` — the path to a JSONL file of the conversation. Phase 2 reads that file, parses each line, assembles a text representation, calls `claude -p` to extract structured knowledge, and writes a markdown file into `.thehook/sessions/`.

The transcript JSONL has a specific, documented structure: each line is a typed record with a `message` object containing `role` and `content`. User message `content` is a plain string; assistant message `content` is an array of typed blocks (text blocks, tool-use blocks, etc.). Parsing requires branching on content type. Messages also carry outer wrapper fields (`type`, `uuid`, `parentUuid`, `sessionId`, `timestamp`, `cwd`) that provide metadata for stub summaries.

The LLM extraction call uses `claude -p "<prompt>"` via `subprocess.Popen` with `start_new_session=True` so the child and any grandchildren are all in a new process group. On `TimeoutExpired` (85 seconds), `os.killpg(os.getpgid(proc.pid), signal.SIGKILL)` terminates the entire group. If extraction fails or times out, a stub file is written with transcript metadata. No new dependencies are required — Python stdlib (`subprocess`, `os`, `signal`, `json`, `pathlib`, `datetime`) covers everything.

**Primary recommendation:** stdlib-only capture module: `json` + `pathlib` for parsing, `subprocess.Popen` with `start_new_session=True` + `os.killpg(SIGKILL)` for `claude -p` with 85s timeout, plain f-string template for structured markdown output. No third-party libraries added for Phase 2.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python `json` | stdlib | Parse JSONL transcript lines | One JSON object per line — `json.loads(line)` for each |
| Python `subprocess` | stdlib | Spawn `claude -p` for LLM extraction | `Popen` with `start_new_session=True` isolates process group for clean kill |
| Python `os` / `signal` | stdlib | Kill process group on timeout | `os.killpg(os.getpgid(pid), signal.SIGKILL)` terminates entire tree |
| Python `pathlib` | stdlib | File I/O for transcript and session files | Already established pattern in Phase 1 |
| Python `datetime` | stdlib | ISO 8601 timestamps for frontmatter | `datetime.utcnow().isoformat()` — no third-party needed |
| Click (8.1+) | existing dep | CLI entry point for `thehook capture` | Already in pyproject.toml; no new dependency |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Python `sys` | stdlib | Read stdin JSON (SessionEnd hook input) | `json.loads(sys.stdin.read())` |
| Python `textwrap` | stdlib | Dedent/clean extraction prompt | Minor prompt formatting; optional |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `subprocess.Popen` manual | `subprocess.run(..., timeout=85)` | `subprocess.run` cannot kill child's children; Popen + killpg is required for process group kill |
| `signal.SIGKILL` | `signal.SIGTERM` | SIGTERM allows graceful shutdown but a hung `claude -p` may not respond; SIGKILL is a hard requirement per CAPT-03 |
| Plain text stdout | `--output-format json` for `claude -p` | `text` (default) is simpler; JSON adds parsing complexity for no benefit when we just need the extraction text |
| Hand-written JSONL parser | `jsonlines` library | stdlib `json.loads` per line is sufficient and adds no dependency |

**Installation:** No new packages required. Phase 2 uses Python stdlib only, building on Phase 1's existing `click>=8.1` dependency.

---

## Architecture Patterns

### Recommended Project Structure

```
src/thehook/
├── cli.py          # add: @main.command() def capture(...)
├── capture.py      # NEW: read_stdin_json, parse_transcript, run_extraction, write_session_file
├── init.py         # existing
└── config.py       # existing

tests/
├── test_capture.py # NEW: covers CAPT-01 through CAPT-06
└── fixtures/
    └── sample_transcript.jsonl  # NEW: minimal JSONL fixture for testing
```

### Pattern 1: Reading SessionEnd Hook Input

**What:** Parse the JSON payload Claude Code sends to the hook on stdin at session end
**When to use:** Entry point of `thehook capture` — the first thing the command does

```python
# Source: https://code.claude.com/docs/en/hooks (SessionEnd input schema, verified 2026-02-23)
import sys
import json

def read_hook_input() -> dict:
    """Read the SessionEnd JSON payload from stdin."""
    raw = sys.stdin.read()
    return json.loads(raw)

# SessionEnd input shape:
# {
#   "session_id": "abc123",
#   "transcript_path": "/Users/.../.claude/projects/.../00893aaf.jsonl",
#   "cwd": "/Users/...",
#   "permission_mode": "default",
#   "hook_event_name": "SessionEnd",
#   "reason": "other"
# }
```

### Pattern 2: Parsing the JSONL Transcript

**What:** Read each line of the transcript JSONL, extract user and assistant messages, handling the two different `content` shapes
**When to use:** CAPT-01 / CAPT-02 — called after reading the hook input

```python
# Source: Confirmed from multiple transcript analysis tools (liambx.com/blog/claude-code-log-analysis-with-duckdb,
#          daaain/claude-code-log, withLinda/claude-JSONL-browser) and Claude Code docs transcript_path field
import json
from pathlib import Path

def parse_transcript(transcript_path: str) -> list[dict]:
    """Parse JSONL transcript into a list of message dicts.

    Each returned dict has: role (str), content (str), uuid (str), timestamp (str)

    Transcript line structure:
    {
      "type": "user" | "assistant" | "summary" | ...,
      "uuid": "...",
      "parentUuid": "...",
      "sessionId": "...",
      "timestamp": "2026-02-23T...",
      "cwd": "...",
      "isSidechain": false,
      "message": {
        "role": "user" | "assistant",
        "content": <string for user> | <list of blocks for assistant>,
        # assistant only:
        "model": "claude-sonnet-4-6",
        "usage": {...},
        "stop_reason": "end_turn",
        "id": "..."
      }
    }

    User content: plain string
    Assistant content: list of blocks e.g.
      [{"type": "text", "text": "..."}, {"type": "tool_use", ...}]
    """
    messages = []
    path = Path(transcript_path)
    if not path.exists():
        return messages

    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue

        # Only process user/assistant message records
        record_type = record.get("type")
        if record_type not in ("user", "assistant"):
            continue

        msg = record.get("message", {})
        role = msg.get("role", record_type)
        raw_content = msg.get("content", "")

        # User messages: content is a plain string
        # Assistant messages: content is a list of blocks
        if isinstance(raw_content, str):
            text = raw_content
        elif isinstance(raw_content, list):
            # Extract text from text blocks; skip tool_use, tool_result, etc.
            parts = []
            for block in raw_content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
            text = "\n".join(parts)
        else:
            text = ""

        messages.append({
            "role": role,
            "content": text,
            "uuid": record.get("uuid", ""),
            "timestamp": record.get("timestamp", ""),
        })

    return messages
```

### Pattern 3: Subprocess with Process Group Kill

**What:** Spawn `claude -p` in a new process group; kill entire group on timeout
**When to use:** CAPT-03 — wraps the LLM extraction call

```python
# Source: Python subprocess docs + alexandra-zaharia.github.io/posts/kill-subprocess-and-its-children-on-timeout-python/
# Verified: start_new_session=True is the thread-safe equivalent of preexec_fn=os.setsid
import os
import signal
import subprocess

EXTRACTION_TIMEOUT_SECONDS = 85

def run_claude_extraction(prompt: str) -> str | None:
    """Run claude -p with the extraction prompt. Returns text output or None on failure.

    Uses start_new_session=True to isolate the process group, then kills the
    entire group on TimeoutExpired to prevent zombie claude processes.
    """
    try:
        proc = subprocess.Popen(
            ["claude", "-p", prompt, "--dangerously-skip-permissions"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,   # new process group; killpg will reach all children
        )
        stdout, stderr = proc.communicate(timeout=EXTRACTION_TIMEOUT_SECONDS)
        if proc.returncode == 0:
            return stdout.decode("utf-8", errors="replace").strip()
        return None
    except subprocess.TimeoutExpired:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        proc.communicate()   # reap to avoid zombie
        return None
    except (OSError, FileNotFoundError):
        # claude binary not found or other OS error
        return None
```

**Note on `--dangerously-skip-permissions`:** The `claude -p` call is invoked from inside a hook (non-interactive context). Without `--dangerously-skip-permissions`, `claude -p` will prompt for tool permissions interactively and hang. This flag is required for non-interactive use. Alternatively, `--allowedTools ""` (no tools) prevents tool calls and avoids the permission prompt entirely — preferred since extraction should not need tools.

**Revised invocation (preferred):**
```python
proc = subprocess.Popen(
    ["claude", "-p", prompt, "--tools", ""],  # no tools = no permission prompts
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    start_new_session=True,
)
```

### Pattern 4: Structured Extraction Prompt (CAPT-06)

**What:** Prompt that directs `claude -p` to extract conventions and decisions specifically, not general observations
**When to use:** CAPT-04 / CAPT-06 — the extraction prompt passed to `run_claude_extraction`

```python
# Source: Project requirement CAPT-06 — prompt must target conventions and ADRs specifically

EXTRACTION_PROMPT_TEMPLATE = """\
You are a technical knowledge extractor. Read this Claude Code session transcript and extract structured project knowledge.

TRANSCRIPT:
{transcript_text}

Extract and return ONLY the following sections in this exact format:

## SUMMARY
2-3 sentences describing what was accomplished in this session.

## CONVENTIONS
Bullet list of coding conventions, naming patterns, tooling choices, or workflow rules established or used.
Only include concrete conventions that would help a developer stay consistent with this project.
Skip general best practices that apply everywhere.

## DECISIONS
Bullet list of architecture or design decisions made with their rationale.
Format: "Decision: [what was decided] — Rationale: [why]"
Only include decisions that are specific to this project.

## GOTCHAS
Bullet list of bugs found, tricky edge cases encountered, or non-obvious behaviors discovered.
Only include things that would trip up someone working on this codebase.

If a section has nothing to report, write "None this session."
Do not add any other sections or commentary.
"""
```

### Pattern 5: Session File with Frontmatter

**What:** Write the extracted knowledge (or stub) as a markdown file with YAML frontmatter
**When to use:** CAPT-04 / CAPT-05 — final output of the capture command

```python
# Source: Project requirements STOR-01, STOR-02 (Phase 3 will use these files)
from datetime import datetime, timezone
from pathlib import Path

def write_session_file(
    sessions_dir: Path,
    session_id: str,
    transcript_path: str,
    content: str,
) -> Path:
    """Write structured markdown with frontmatter to .thehook/sessions/."""
    timestamp = datetime.now(timezone.utc).isoformat()
    safe_id = session_id[:8] if len(session_id) > 8 else session_id
    filename = f"{timestamp[:10]}-{safe_id}.md"

    frontmatter = (
        f"---\n"
        f"session_id: {session_id}\n"
        f"timestamp: {timestamp}\n"
        f"transcript_path: {transcript_path}\n"
        f"---\n\n"
    )

    sessions_dir.mkdir(parents=True, exist_ok=True)
    output_path = sessions_dir / filename
    output_path.write_text(frontmatter + content)
    return output_path

def write_stub_summary(
    sessions_dir: Path,
    session_id: str,
    transcript_path: str,
    message_count: int,
    reason: str = "timeout",
) -> Path:
    """Write a stub summary when extraction fails or times out."""
    stub_content = (
        f"## SUMMARY\n"
        f"Extraction {reason}. Session had {message_count} messages.\n\n"
        f"## CONVENTIONS\nNone this session.\n\n"
        f"## DECISIONS\nNone this session.\n\n"
        f"## GOTCHAS\nNone this session.\n"
    )
    return write_session_file(sessions_dir, session_id, transcript_path, stub_content)
```

### Pattern 6: CLI Command Registration

**What:** Register `capture` as a Click subcommand in `cli.py`
**When to use:** CAPT-01 entry point — called by the SessionEnd hook as `thehook capture`

```python
# Source: Phase 1 cli.py pattern (verified working)
@main.command()
def capture():
    """Extract knowledge from the completed session transcript (called by SessionEnd hook)."""
    from thehook.capture import run_capture
    import sys
    run_capture(project_dir=Path(".").resolve())
```

The hook command in `settings.local.json` is already `"thehook capture"` (wired in Phase 1).

### Anti-Patterns to Avoid

- **`subprocess.run(..., timeout=85)` without process group kill:** `subprocess.run` raises `TimeoutExpired` but does NOT kill grandchildren. Use `Popen` + `killpg` to ensure all descendant processes are killed.
- **`subprocess.Popen(..., preexec_fn=os.setsid)`:** `preexec_fn` is not thread-safe. Use `start_new_session=True` instead — it's the documented thread-safe equivalent since Python 3.2.
- **Calling `os.killpg` without `proc.communicate()` after:** After killpg, you must still call `proc.communicate()` (or `proc.wait()`) to reap the zombie and avoid resource leaks.
- **Parsing assistant content as string:** Assistant `message.content` is always an array of blocks. Treating it as a string causes `AttributeError` or empty output. Always check `isinstance(content, list)`.
- **Truncating transcript before extraction:** Naively joining all message text may produce a very long prompt that exceeds model context. Truncate to a reasonable character limit (e.g., last 50,000 characters) before calling `claude -p`.
- **Running `claude -p` with interactive tools enabled:** Without `--tools ""`, claude may prompt for permissions in a non-interactive context and hang until timeout. Always use `--tools ""` for extraction.
- **Writing to `.thehook/sessions/` without `mkdir(parents=True, exist_ok=True)`:** The directory is created by `thehook init`, but the hook may run in a project where init was run before the directory existed. Always ensure parent directories exist before write.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSONL line parsing | Custom state machine | `json.loads(line)` per line | JSONL is one JSON object per newline; stdlib handles all edge cases |
| Process kill on timeout | Custom signal sending loop | `os.killpg` + `start_new_session=True` | Process groups ensure all descendants are killed, not just the direct child |
| Markdown generation | Template engine / jinja2 | f-string with fixed section headers | Output is a fixed 4-section structure; no logic branching needed |
| Transcript summarization | Custom NLP / transformers | `claude -p` | LLM does better extraction; already installed as the product's runtime dependency |
| File naming / deduplication | UUID library | `datetime.now().isoformat()[:10] + "-" + session_id[:8]` | Timestamp prefix gives chronological sort; session_id suffix prevents collisions |

**Key insight:** Phase 2 is an orchestration problem, not a data-structure problem. The hard parts (LLM extraction, JSON parsing, process management) are all solved by stdlib + an already-installed binary (`claude`). Custom code risk is highest in the subprocess timeout pattern — use the verified `Popen` + `killpg` approach exactly.

---

## Common Pitfalls

### Pitfall 1: Incomplete Process Kill on Timeout

**What goes wrong:** `subprocess.run(..., timeout=85)` is used instead of `Popen` + `killpg`. When timeout fires, the Python wrapper process (`claude`) is killed but any grandchild processes it spawned continue running, consuming resources and potentially causing test failures.
**Why it happens:** `subprocess.run` looks simpler and handles the common case. The process-tree-kill requirement isn't obvious until you encounter zombie processes in CI.
**How to avoid:** Always use `subprocess.Popen(..., start_new_session=True)` + `os.killpg(os.getpgid(proc.pid), signal.SIGKILL)` in the `TimeoutExpired` handler.
**Warning signs:** Tests pass individually but leave background processes. `ps aux | grep claude` shows orphaned processes after test runs.

### Pitfall 2: Missing `proc.communicate()` After killpg

**What goes wrong:** `os.killpg` is called but the process is never waited on. The killed process becomes a zombie in the process table.
**Why it happens:** After killpg the programmer assumes the process is "gone" and doesn't need to be reaped.
**How to avoid:** Always call `proc.communicate()` (or `proc.wait()`) after killpg — even for an already-dead process it returns immediately with empty output.
**Warning signs:** `ps aux` shows zombie `<defunct>` processes after test runs. Memory leaks in long-running test suites.

### Pitfall 3: User Content Treated as Array / Assistant Content as String

**What goes wrong:** Code does `for block in message.content` when `role == "user"` but user content is a plain string, causing iteration over characters.
**Why it happens:** Assuming both roles use the same content shape.
**How to avoid:** Always check `isinstance(content, list)` before iterating. Handle string path explicitly. See Pattern 2.
**Warning signs:** Test with a real transcript fixture. If extracted user text looks like `"H e l l o w o r l d"` (spaced characters), you iterated over a string.

### Pitfall 4: Empty Extraction Output Treated as Success

**What goes wrong:** `claude -p` exits 0 but returns empty stdout. The empty string is written as the session file content.
**Why it happens:** `claude -p` can succeed with no output if the prompt produces no response (edge case).
**How to avoid:** Check `if not result` after `run_claude_extraction()` — treat falsy output the same as None and write a stub.
**Warning signs:** Session files exist but contain only frontmatter + empty body.

### Pitfall 5: Transcript Read Fails Silently

**What goes wrong:** `transcript_path` in the hook input points to a file that doesn't exist yet (race condition: hook fires before transcript is fully flushed) or has been deleted. `Path.read_text()` raises `FileNotFoundError`.
**Why it happens:** Claude Code writes the transcript async; the hook fires at session end but the JSONL file may not be fully written.
**How to avoid:** Wrap transcript read in a `try/except (FileNotFoundError, PermissionError)` and write a stub summary if the file is unreadable. Also handle empty files (0 messages).
**Warning signs:** Hook crashes silently (async hook, exit code is discarded by Claude Code).

### Pitfall 6: Hook Runs in Wrong Working Directory

**What goes wrong:** `thehook capture` uses `Path(".")` to find `.thehook/sessions/` but the hook runs from a different working directory (not the project root).
**Why it happens:** Claude Code sets `cwd` in the hook input, but the shell working directory at hook execution time is the value of `cwd` from the hook event, which is the project directory — but this should be verified.
**How to avoid:** Read `cwd` from the stdin JSON and use that as the project_dir rather than `Path(".")`. The SessionEnd input always includes `cwd`.
**Warning signs:** `FileNotFoundError: .thehook/sessions` — means the hook is running from a different directory than expected.

### Pitfall 7: Extraction Prompt Exceeds Context Window

**What goes wrong:** A long Claude Code session with 200+ tool calls produces a transcript text of 300,000+ characters. Passing this entire text to `claude -p` exceeds the model context window.
**Why it happens:** No truncation applied before passing transcript to extraction prompt.
**How to avoid:** Truncate assembled transcript text to a maximum of ~50,000 characters (keeping the last N characters for recency) before formatting the extraction prompt. Document the truncation limit as a constant.
**Warning signs:** `claude -p` returns an error about context length, or the hook consistently times out on long sessions.

---

## Code Examples

Verified patterns from official sources and confirmed research:

### Full Capture Command Flow

```python
# src/thehook/capture.py
import json
import os
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

EXTRACTION_TIMEOUT_SECONDS = 85
MAX_TRANSCRIPT_CHARS = 50_000  # prevent context window overflow

def run_capture(project_dir: Path) -> None:
    """Main entry point for `thehook capture` (SessionEnd hook)."""
    # Step 1: Read hook input from stdin
    try:
        hook_input = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError):
        return  # nothing to do if we can't read input

    session_id = hook_input.get("session_id", "unknown")
    transcript_path = hook_input.get("transcript_path", "")
    cwd = hook_input.get("cwd", str(project_dir))
    project_dir = Path(cwd)  # use cwd from hook input, not caller's cwd
    sessions_dir = project_dir / ".thehook" / "sessions"

    # Step 2: Parse transcript
    messages = parse_transcript(transcript_path)
    message_count = len(messages)

    if message_count == 0:
        write_stub_summary(sessions_dir, session_id, transcript_path, 0, reason="empty transcript")
        return

    # Step 3: Assemble text for extraction
    transcript_text = assemble_transcript_text(messages, max_chars=MAX_TRANSCRIPT_CHARS)

    # Step 4: Run LLM extraction
    prompt = EXTRACTION_PROMPT_TEMPLATE.format(transcript_text=transcript_text)
    result = run_claude_extraction(prompt)

    # Step 5: Write session file (or stub on failure)
    if result:
        write_session_file(sessions_dir, session_id, transcript_path, result)
    else:
        write_stub_summary(sessions_dir, session_id, transcript_path, message_count, reason="timeout")
```

### Subprocess Timeout with killpg

```python
# Source: Python subprocess docs + alexandra-zaharia.github.io/posts/kill-subprocess-and-its-children-on-timeout-python/
# start_new_session=True is the thread-safe equivalent of preexec_fn=os.setsid (Python 3.2+)
def run_claude_extraction(prompt: str) -> str | None:
    try:
        proc = subprocess.Popen(
            ["claude", "-p", prompt, "--tools", ""],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        stdout, _ = proc.communicate(timeout=EXTRACTION_TIMEOUT_SECONDS)
        if proc.returncode == 0:
            return stdout.decode("utf-8", errors="replace").strip() or None
        return None
    except subprocess.TimeoutExpired:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        proc.communicate()  # reap zombie
        return None
    except (OSError, FileNotFoundError):
        return None
```

### Transcript Text Assembly with Truncation

```python
def assemble_transcript_text(messages: list[dict], max_chars: int = 50_000) -> str:
    parts = []
    for msg in messages:
        role = msg["role"].upper()
        content = msg["content"].strip()
        if content:
            parts.append(f"[{role}]: {content}")
    full = "\n\n".join(parts)
    if len(full) > max_chars:
        # Keep the last max_chars to preserve recent context
        full = "...[truncated]...\n\n" + full[-max_chars:]
    return full
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `preexec_fn=os.setsid` | `start_new_session=True` | Python 3.2+ | Thread-safe; no deprecation warnings; functionally identical |
| `subprocess.run(timeout=N)` | `Popen` + `killpg` | Always was better | `subprocess.run` does not kill grandchildren; required for process tree kill |
| `claude` headless mode docs | Agent SDK / `-p` flag docs | 2025 | The CLI was previously called "headless mode." The `-p` flag and all CLI options remain identical. |
| `--dangerously-skip-permissions` | `--tools ""` | Current | `--tools ""` is cleaner than skipping permissions; extraction does not need any tools |

**Deprecated/outdated:**
- `preexec_fn=os.setsid`: Technically works but is not thread-safe in multi-threaded programs. Use `start_new_session=True` in all new code.
- Claude Code "headless mode" terminology: The official name is now "Agent SDK" or `-p` mode. All flags are unchanged.

---

## Open Questions

1. **Does `claude -p` require a TTY?**
   - What we know: The docs show `cat file | claude -p "query"` with piped input, confirming non-TTY operation is supported.
   - What's unclear: Whether stdout from `Popen` (not a TTY) causes any buffering issues or special behavior. The `--output-format text` default should stream plain text.
   - Recommendation: Test with a minimal transcript fixture on day 1 of Phase 2 implementation. If buffering is an issue, add `--output-format text` explicitly to the command.

2. **Transcript JSONL race condition: is the file complete when SessionEnd fires?**
   - What we know: Claude Code fires SessionEnd when the session terminates. The transcript file path is provided in the hook input. The async hook flag is already set on the SessionEnd command (`"async": True, "timeout": 120` — from Phase 1 init.py), so the hook can take up to 120 seconds.
   - What's unclear: Whether there is a brief window between session end and transcript flush where the file might be incomplete or absent.
   - Recommendation: Wrap transcript read in try/except FileNotFoundError; write a stub if file is unreadable. Add a 1-second sleep before reading as a simple mitigation if needed (LOW risk, defer to testing).

3. **Maximum `--tools ""` behavior**
   - What we know: `--tools ""` is documented to disable all tools. For extraction, we only need a text response — no tools are needed.
   - What's unclear: Whether `--tools ""` prevents ALL permission prompts or just tool-use ones.
   - Recommendation: Use `--tools ""` as the primary approach; if the hook hangs in testing, add `--dangerously-skip-permissions` as a secondary fallback.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.0+ |
| Config file | `pyproject.toml` — `[tool.pytest.ini_options]` (exists from Phase 1) |
| Quick run command | `pytest tests/ -x -q` |
| Full suite command | `pytest tests/ -v` |
| Estimated runtime | ~3–8 seconds (JSONL parsing + stub writing are fast; subprocess tests mock `claude -p`) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CAPT-01 | `run_capture()` reads `transcript_path` from stdin JSON and opens the JSONL file | unit | `pytest tests/test_capture.py -x -k "stdin_json"` | Wave 0 gap |
| CAPT-01 | JSONL lines are parsed without error for a valid transcript fixture | unit | `pytest tests/test_capture.py -x -k "parse_transcript"` | Wave 0 gap |
| CAPT-02 | User message content (string) is extracted correctly | unit | `pytest tests/test_capture.py -x -k "user_string_content"` | Wave 0 gap |
| CAPT-02 | Assistant message content (array of blocks) is extracted correctly (text blocks joined) | unit | `pytest tests/test_capture.py -x -k "assistant_block_content"` | Wave 0 gap |
| CAPT-02 | Non-text blocks (tool_use) in assistant content are skipped without error | unit | `pytest tests/test_capture.py -x -k "tool_use_blocks_skipped"` | Wave 0 gap |
| CAPT-03 | `run_claude_extraction` is called with 85s timeout; `TimeoutExpired` triggers `killpg` | unit (mocked subprocess) | `pytest tests/test_capture.py -x -k "timeout_kills_group"` | Wave 0 gap |
| CAPT-04 | Session file contains SUMMARY / CONVENTIONS / DECISIONS / GOTCHAS sections | unit (mocked extraction) | `pytest tests/test_capture.py -x -k "structured_markdown"` | Wave 0 gap |
| CAPT-05 | On `TimeoutExpired`, a stub file is written with session_id, transcript_path, message_count | unit (mocked subprocess) | `pytest tests/test_capture.py -x -k "stub_on_timeout"` | Wave 0 gap |
| CAPT-05 | On `claude -p` exit nonzero, a stub file is written | unit (mocked subprocess) | `pytest tests/test_capture.py -x -k "stub_on_failure"` | Wave 0 gap |
| CAPT-06 | Extraction prompt contains the word "conventions" and "decisions" but not "observations" | unit | `pytest tests/test_capture.py -x -k "prompt_targeting"` | Wave 0 gap |

### Nyquist Sampling Rate

- **Minimum sample interval:** After every committed task → run: `pytest tests/ -x -q`
- **Full suite trigger:** Before merging final task of Phase 2
- **Phase-complete gate:** Full suite green before `/gsd:verify-work` runs
- **Estimated feedback latency per task:** ~5 seconds

### Wave 0 Gaps (must be created before implementation)

- [ ] `tests/test_capture.py` — covers CAPT-01 through CAPT-06 (all gaps above)
- [ ] `tests/fixtures/sample_transcript.jsonl` — minimal JSONL with 1 user message (string content) + 1 assistant message (array of blocks including a text block and a tool_use block)
- [ ] `src/thehook/capture.py` — skeleton with function signatures and docstrings, no implementation

*(Existing `tests/conftest.py` with `tmp_project` fixture covers Phase 2 needs — no changes required.)*

---

## Sources

### Primary (HIGH confidence)

- `https://code.claude.com/docs/en/hooks` — SessionEnd input schema; `transcript_path` as common input field on all events; async hook behavior; verified 2026-02-23.
- `https://code.claude.com/docs/en/headless` (redirects to headless page) — `claude -p` usage, `--output-format text/json/stream-json`, `--tools ""` flag, piped stdin support; verified 2026-02-23.
- `https://code.claude.com/docs/en/cli-reference` — Complete flag reference including `--tools`, `--dangerously-skip-permissions`, `--output-format`; verified 2026-02-23.
- Python `subprocess` docs — `Popen`, `start_new_session`, `communicate(timeout=N)`, `TimeoutExpired`; `os.killpg`, `signal.SIGKILL`; stdlib, always current.

### Secondary (MEDIUM confidence)

- `https://liambx.com/blog/claude-code-log-analysis-with-duckdb` — JSONL transcript structure: outer fields (type, uuid, sessionId, timestamp, message), message.role, user content as string, assistant content as array of blocks with `{"type":"text","text":"..."}`. Verified against multiple independent sources.
- `https://github.com/daaain/claude-code-log` — Independent Python tool parsing same JSONL structure; uses Pydantic models with branching on content type. Confirms the string/array duality.
- `https://github.com/withLinda/claude-JSONL-browser` — Third independent tool confirming same JSONL structure.
- `https://alexandra-zaharia.github.io/posts/kill-subprocess-and-its-children-on-timeout-python/` — `start_new_session=True` + `os.killpg(SIGKILL)` pattern. Verified against Python subprocess docs.

### Tertiary (LOW confidence)

- `https://kentgigger.com/posts/claude-code-conversation-history` — General transcript format description; consistent with higher-confidence sources but not authoritative.
- STATE.md note: "Transcript JSONL content shape variation should be confirmed with a real transcript fixture on day one of Phase 2" — this is the project's own flag; validate with a real file before shipping.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — stdlib only; all patterns verified against Python docs and official Claude Code CLI reference
- Architecture: HIGH — JSONL structure confirmed by 3+ independent open-source tools and official hooks docs; `claude -p` CLI fully documented
- Pitfalls: HIGH for subprocess patterns (verified Python docs); MEDIUM for transcript race condition (no official timing guarantee found); LOW for `--tools ""` vs `--dangerously-skip-permissions` behavior (document says it works but not tested here)

**Research date:** 2026-02-23
**Valid until:** 2026-03-25 (stable ecosystem; Claude Code CLI flags may change faster — re-check `--tools ""` behavior if more than 2 weeks pass)
