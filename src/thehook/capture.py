"""Transcript parsing and hook input reading for the capture pipeline."""

import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

MAX_TRANSCRIPT_CHARS = 50_000
EXTRACTION_TIMEOUT_SECONDS = 85
INTERMEDIATE_EXTRACTION_TIMEOUT_SECONDS = 20
INTERMEDIATE_MAX_TRANSCRIPT_CHARS = 12_000
INTERMEDIATE_MIN_INTERVAL_SECONDS = 180
INTERMEDIATE_STATE_FILENAME = "intermediate_capture_state.json"

EXTRACTION_PROMPT_TEMPLATE = """\
You are a technical knowledge extractor. Analyze the following Claude session transcript and extract concrete, reusable knowledge from it.

Focus exclusively on:
- **conventions**: coding patterns, style choices, naming standards, and structural rules established during the session
- **decisions**: architectural and implementation choices made, and the reasoning behind them
- **gotchas**: non-obvious pitfalls, edge cases, or mistakes discovered and resolved

Do NOT summarise every action taken. Only extract what would genuinely help a developer picking up this project later.

## Output format

Respond with exactly these four sections. If a section has nothing to report, write "None this session." under it.

## SUMMARY
One or two sentences describing what was accomplished in this session.

## CONVENTIONS
A bullet list of concrete conventions established or reinforced. Only include concrete conventions — things like "use X not Y", "files go in Z directory", "always do A before B". Skip generic best practices.

## DECISIONS
A bullet list of decisions that are specific to this project — technology choices, trade-offs accepted, scope limitations. Only include decisions that are specific to this project, not general software engineering principles.

## GOTCHAS
A bullet list of non-obvious issues, edge cases, or traps encountered. Include what the symptom was and how it was resolved.

---

## Session transcript

{transcript_text}
"""

INTERMEDIATE_EXTRACTION_PROMPT_TEMPLATE = """\
You are extracting short-term project memory from an in-progress coding session.

Focus on what changed recently and only keep high-signal details:
- **conventions** newly established or reinforced
- **decisions** with trade-offs or scope implications
- **gotchas** that could cause future regressions

Keep it concise and concrete. Skip generic guidance and routine actions.

## Output format

Respond with exactly these four sections. If a section has nothing to report, write "None this session." under it.

## SUMMARY
One short sentence on recent progress.

## CONVENTIONS
Bullet list of concrete conventions.

## DECISIONS
Bullet list of project-specific decisions.

## GOTCHAS
Bullet list of non-obvious issues and mitigations.

---

## Session transcript

{transcript_text}
"""


def _load_runtime_config(project_dir: Path) -> dict:
    """Load config safely; return defaults on any failure."""
    try:
        from thehook.config import load_config
        return load_config(project_dir)
    except Exception:
        return {}


def _state_file_path(project_dir: Path) -> Path:
    return project_dir / ".thehook" / INTERMEDIATE_STATE_FILENAME


def _read_intermediate_state(project_dir: Path) -> dict:
    path = _state_file_path(project_dir)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _write_intermediate_state(project_dir: Path, state: dict) -> None:
    path = _state_file_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2))


def _should_skip_intermediate_capture(
    project_dir: Path,
    session_id: str,
    transcript_hash: str,
    min_interval_seconds: int,
) -> bool:
    state = _read_intermediate_state(project_dir)
    now = int(time.time())
    last_capture_at = int(state.get("last_capture_at", 0))
    last_session_id = str(state.get("session_id", ""))
    last_transcript_hash = str(state.get("transcript_hash", ""))

    # Skip repeated captures when transcript has not changed.
    if last_session_id == session_id and last_transcript_hash == transcript_hash:
        return True

    # Keep intermediate hooks lightweight by enforcing a minimum interval.
    if now - last_capture_at < max(0, min_interval_seconds):
        return True

    return False


def _mark_intermediate_capture(
    project_dir: Path,
    session_id: str,
    transcript_hash: str,
) -> None:
    _write_intermediate_state(
        project_dir,
        {
            "session_id": session_id,
            "transcript_hash": transcript_hash,
            "last_capture_at": int(time.time()),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )


def _index_session_file(project_dir: Path, session_path: Path) -> None:
    try:
        from thehook.storage import index_session_file
        index_session_file(project_dir, session_path)
    except Exception:
        pass  # ChromaDB failure must never break capture pipeline


def _resolve_project_dir(hook_input: dict) -> Path:
    workspace_roots = hook_input.get("workspace_roots", [])
    cwd = hook_input.get("cwd") or (workspace_roots[0] if workspace_roots else ".")
    return Path(cwd)


def read_hook_input() -> dict:
    """Read the SessionEnd JSON payload from stdin.

    Returns:
        dict: Parsed JSON payload from stdin. Returns empty dict on error.
    """
    try:
        raw = sys.stdin.read()
        if not raw:
            return {}
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def parse_transcript(transcript_path: str) -> list[dict]:
    """Parse JSONL transcript into a list of message dicts.

    Each returned dict has: role (str), content (str), uuid (str), timestamp (str).

    Only processes records where type is 'user' or 'assistant'.
    User message content is a plain string.
    Assistant message content is an array of blocks — only text blocks are extracted,
    tool_use and other block types are skipped.

    Args:
        transcript_path: Path to the JSONL transcript file.

    Returns:
        list[dict]: List of message dicts. Returns empty list if file does not exist.
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


def assemble_transcript_text(messages: list[dict], max_chars: int = 50_000) -> str:
    """Join messages into a single string with role labels.

    Formats each message as '[ROLE]: content', joined with double newlines.
    Skips messages with empty content after stripping whitespace.
    If the assembled text exceeds max_chars, truncates to the last max_chars
    characters prefixed with '...[truncated]...\\n\\n'.

    Args:
        messages: List of message dicts with 'role' and 'content' keys.
        max_chars: Maximum character length of the returned string.

    Returns:
        str: Assembled transcript text.
    """
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


def run_claude_extraction(prompt: str, timeout_seconds: int = EXTRACTION_TIMEOUT_SECONDS) -> str | None:
    """Run claude -p with the extraction prompt. Returns text output or None on failure.

    Uses start_new_session=True to isolate the process group, then kills the
    entire group on TimeoutExpired to prevent zombie claude processes.

    Args:
        prompt: The extraction prompt to pass to claude -p.

    Returns:
        str | None: Decoded stdout text on success (exit 0 with non-empty output),
            None on timeout, non-zero exit, empty output, or OS error.
    """
    try:
        proc = subprocess.Popen(
            ["claude", "-p", prompt, "--tools", ""],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,  # new process group; killpg will reach all children
        )
        stdout, _ = proc.communicate(timeout=timeout_seconds)
        if proc.returncode == 0:
            return stdout.decode("utf-8", errors="replace").strip() or None
        return None
    except subprocess.TimeoutExpired:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        proc.communicate()  # reap zombie to avoid resource leaks
        return None
    except (OSError, FileNotFoundError):
        return None


def write_session_file(
    sessions_dir: Path,
    session_id: str,
    transcript_path: str,
    content: str,
) -> Path:
    """Write structured markdown with YAML frontmatter to the sessions directory.

    Creates the sessions directory if it does not exist. The filename is derived
    from the current UTC date and the first 8 characters of the session_id.

    Args:
        sessions_dir: Directory where session files are stored (e.g. .thehook/sessions).
        session_id: Unique session identifier from the hook input.
        transcript_path: Path to the JSONL transcript file.
        content: Markdown body content (extraction result or stub).

    Returns:
        Path: Path to the written session file.
    """
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
    """Write a stub summary when extraction fails or times out.

    The stub contains all four structured sections (SUMMARY, CONVENTIONS,
    DECISIONS, GOTCHAS) with minimal metadata indicating the failure reason
    and message count. This ensures every session produces a file even when
    LLM extraction is unavailable.

    Args:
        sessions_dir: Directory where session files are stored.
        session_id: Unique session identifier from the hook input.
        transcript_path: Path to the JSONL transcript file.
        message_count: Number of messages parsed from the transcript.
        reason: Failure reason label ('timeout', 'error', etc.).

    Returns:
        Path: Path to the written stub file.
    """
    stub_content = (
        f"## SUMMARY\n"
        f"Extraction {reason}. Session had {message_count} messages.\n\n"
        f"## CONVENTIONS\nNone this session.\n\n"
        f"## DECISIONS\nNone this session.\n\n"
        f"## GOTCHAS\nNone this session.\n"
    )
    return write_session_file(sessions_dir, session_id, transcript_path, stub_content)


def run_capture(mode: Literal["full", "lite"] = "full") -> None:
    """Orchestrate capture pipeline for final and intermediate memory.

    Reads hook input from stdin, parses the JSONL transcript, runs LLM
    extraction via run_claude_extraction, and writes a session file.

    - full mode (SessionEnd): always writes either extraction or stub.
    - lite mode (Stop/PreCompact): skips when disabled, throttled, unchanged,
      or transcript is empty.

    Uses cwd from hook input as the project directory to avoid being affected
    by the shell's current working directory at hook invocation time.
    """
    hook_input = read_hook_input()
    if not hook_input:
        return

    session_id = hook_input.get("session_id") or hook_input.get("conversation_id", "unknown")
    transcript_path = hook_input.get("transcript_path") or ""
    project_dir = _resolve_project_dir(hook_input)

    # Use project dir from hook input — hook may run from a different cwd
    sessions_dir = project_dir / ".thehook" / "sessions"
    config = _load_runtime_config(project_dir)

    # Cursor may send transcript_path as null when transcripts are disabled.
    if not transcript_path:
        if mode == "lite":
            return
        session_path = write_stub_summary(
            sessions_dir,
            session_id,
            transcript_path,
            0,
            reason="empty transcript_path",
        )
        _index_session_file(project_dir, session_path)
        return

    messages = parse_transcript(transcript_path)
    if not messages:
        if mode == "lite":
            return
        session_path = write_stub_summary(sessions_dir, session_id, transcript_path, 0, reason="empty transcript")
        _index_session_file(project_dir, session_path)
        return

    if mode == "lite":
        if not bool(config.get("intermediate_capture_enabled", True)):
            return
        max_chars = int(config.get("intermediate_capture_max_transcript_chars", INTERMEDIATE_MAX_TRANSCRIPT_CHARS))
        timeout_seconds = int(config.get("intermediate_capture_timeout_seconds", INTERMEDIATE_EXTRACTION_TIMEOUT_SECONDS))
        min_interval_seconds = int(config.get("intermediate_capture_min_interval_seconds", INTERMEDIATE_MIN_INTERVAL_SECONDS))
        prompt_template = INTERMEDIATE_EXTRACTION_PROMPT_TEMPLATE
    else:
        max_chars = MAX_TRANSCRIPT_CHARS
        timeout_seconds = EXTRACTION_TIMEOUT_SECONDS
        min_interval_seconds = 0
        prompt_template = EXTRACTION_PROMPT_TEMPLATE

    transcript_text = assemble_transcript_text(messages, max_chars=max_chars)

    if mode == "lite":
        transcript_hash = hashlib.sha256(transcript_text.encode("utf-8")).hexdigest()
        if _should_skip_intermediate_capture(
            project_dir,
            session_id=str(session_id),
            transcript_hash=transcript_hash,
            min_interval_seconds=min_interval_seconds,
        ):
            return
    else:
        transcript_hash = ""

    prompt = prompt_template.format(transcript_text=transcript_text)
    result = run_claude_extraction(prompt, timeout_seconds=timeout_seconds)
    if result:
        session_path = write_session_file(sessions_dir, session_id, transcript_path, result)
        _index_session_file(project_dir, session_path)
        if mode == "lite":
            _mark_intermediate_capture(project_dir, str(session_id), transcript_hash)
    else:
        if mode == "lite":
            # Keep intermediate mode cheap: skip stub writes on extraction failure.
            _mark_intermediate_capture(project_dir, str(session_id), transcript_hash)
            return
        session_path = write_stub_summary(sessions_dir, session_id, transcript_path, len(messages), reason="timeout")
        _index_session_file(project_dir, session_path)
