"""Transcript parsing and hook input reading for the capture pipeline."""

import json
import sys
from pathlib import Path

MAX_TRANSCRIPT_CHARS = 50_000


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
