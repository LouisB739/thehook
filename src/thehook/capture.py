"""Transcript parsing and hook input reading for the capture pipeline."""

MAX_TRANSCRIPT_CHARS = 50_000


def read_hook_input() -> dict:
    """Read the SessionEnd JSON payload from stdin.

    Returns:
        dict: Parsed JSON payload from stdin. Returns empty dict on error.
    """
    raise NotImplementedError


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
    raise NotImplementedError


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
    raise NotImplementedError
