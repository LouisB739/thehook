"""Tests for transcript parsing and hook input reading (capture pipeline)."""
import io
import json
import sys
from pathlib import Path

import pytest

from thehook.capture import assemble_transcript_text, parse_transcript, read_hook_input


@pytest.fixture
def sample_transcript_path():
    """Return the path to the sample JSONL transcript fixture."""
    return Path(__file__).parent / "fixtures" / "sample_transcript.jsonl"


def test_read_hook_input_parses_stdin_json(monkeypatch):
    """read_hook_input reads JSON payload from stdin and returns it as a dict."""
    payload = {"session_id": "abc", "transcript_path": "/tmp/t.jsonl"}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    result = read_hook_input()
    assert result["session_id"] == "abc"
    assert result["transcript_path"] == "/tmp/t.jsonl"


def test_parse_transcript_returns_messages(sample_transcript_path):
    """parse_transcript returns a list of 3 messages (system record is skipped)."""
    messages = parse_transcript(str(sample_transcript_path))
    assert isinstance(messages, list)
    assert len(messages) == 3


def test_parse_transcript_user_string_content(sample_transcript_path):
    """First message has role='user' and the expected string content."""
    messages = parse_transcript(str(sample_transcript_path))
    user_msg = messages[0]
    assert user_msg["role"] == "user"
    assert user_msg["content"] == "Hello, can you help me set up auth?"


def test_parse_transcript_assistant_block_content(sample_transcript_path):
    """Second message has role='assistant' with text block extracted and tool_use skipped."""
    messages = parse_transcript(str(sample_transcript_path))
    assistant_msg = messages[1]
    assert assistant_msg["role"] == "assistant"
    assert assistant_msg["content"] == "Sure, I can help with authentication."


def test_parse_transcript_assistant_multiple_text_blocks(sample_transcript_path):
    """Third message has two text blocks joined with newline."""
    messages = parse_transcript(str(sample_transcript_path))
    assistant_msg = messages[2]
    assert assistant_msg["role"] == "assistant"
    assert assistant_msg["content"] == "Here is the plan:\nStep 1: Create auth module"


def test_parse_transcript_nonexistent_file():
    """parse_transcript returns empty list for a path that does not exist."""
    result = parse_transcript("/nonexistent/path/to/transcript.jsonl")
    assert result == []


def test_parse_transcript_empty_file(tmp_path):
    """parse_transcript returns empty list for an empty file."""
    empty_file = tmp_path / "empty.jsonl"
    empty_file.write_text("")
    result = parse_transcript(str(empty_file))
    assert result == []


def test_assemble_transcript_text_formats_messages():
    """assemble_transcript_text includes [USER]: and [ASSISTANT]: labels."""
    messages = [
        {"role": "user", "content": "Hello there", "uuid": "u1", "timestamp": "t1"},
        {"role": "assistant", "content": "Hi back", "uuid": "u2", "timestamp": "t2"},
    ]
    result = assemble_transcript_text(messages)
    assert "[USER]:" in result
    assert "[ASSISTANT]:" in result
    assert "Hello there" in result
    assert "Hi back" in result


def test_assemble_transcript_text_truncates():
    """assemble_transcript_text truncates to max_chars and prefixes with ...[truncated]..."""
    # Create messages whose assembled text will be longer than 50 chars
    messages = [
        {"role": "user", "content": "A" * 30, "uuid": "u1", "timestamp": "t1"},
        {"role": "assistant", "content": "B" * 30, "uuid": "u2", "timestamp": "t2"},
    ]
    max_chars = 50
    result = assemble_transcript_text(messages, max_chars=max_chars)
    assert result.startswith("...[truncated]...")
    # The truncated portion should be at most max_chars characters (after the prefix)
    prefix = "...[truncated]...\n\n"
    assert len(result) <= len(prefix) + max_chars
