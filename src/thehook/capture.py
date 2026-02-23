"""Transcript parsing and hook input reading for the capture pipeline."""

import json
import os
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

MAX_TRANSCRIPT_CHARS = 50_000
EXTRACTION_TIMEOUT_SECONDS = 85

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


def run_claude_extraction(prompt: str) -> str | None:
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
        stdout, _ = proc.communicate(timeout=EXTRACTION_TIMEOUT_SECONDS)
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


def run_capture() -> None:
    """Orchestrate the full SessionEnd capture pipeline.

    Reads hook input from stdin, parses the JSONL transcript, runs LLM
    extraction via run_claude_extraction, and writes a session file. On any
    failure path (bad stdin, empty transcript, extraction failure), writes a
    stub summary so every session always produces a file.

    Uses cwd from hook input as the project directory to avoid being affected
    by the shell's current working directory at hook invocation time.
    """
    hook_input = read_hook_input()
    if not hook_input:
        return

    session_id = hook_input.get("session_id", "unknown")
    transcript_path = hook_input.get("transcript_path", "")
    cwd = hook_input.get("cwd", ".")

    # Use project dir from hook input — hook may run from a different cwd
    sessions_dir = Path(cwd) / ".thehook" / "sessions"

    messages = parse_transcript(transcript_path)
    if not messages:
        write_stub_summary(sessions_dir, session_id, transcript_path, 0, reason="empty transcript")
        return

    transcript_text = assemble_transcript_text(messages, max_chars=MAX_TRANSCRIPT_CHARS)
    prompt = EXTRACTION_PROMPT_TEMPLATE.format(transcript_text=transcript_text)

    result = run_claude_extraction(prompt)
    if result:
        write_session_file(sessions_dir, session_id, transcript_path, result)
    else:
        write_stub_summary(sessions_dir, session_id, transcript_path, len(messages), reason="timeout")
