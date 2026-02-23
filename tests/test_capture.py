"""Tests for transcript parsing and hook input reading (capture pipeline)."""
import io
import json
import signal
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from thehook.capture import (
    assemble_transcript_text,
    parse_transcript,
    read_hook_input,
    run_claude_extraction,
    write_session_file,
    write_stub_summary,
)


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


# ---------------------------------------------------------------------------
# Session file writing tests
# ---------------------------------------------------------------------------

def test_write_session_file_creates_markdown_with_frontmatter(tmp_path):
    """write_session_file creates a .md file with YAML frontmatter and content."""
    sessions_dir = tmp_path / "sessions"
    result_path = write_session_file(
        sessions_dir, "sess123", "/tmp/t.jsonl", "## SUMMARY\nTest content"
    )
    assert result_path.exists()
    assert result_path.suffix == ".md"
    content = result_path.read_text()
    assert "session_id: sess123" in content
    assert "transcript_path: /tmp/t.jsonl" in content
    assert "---" in content
    assert "## SUMMARY" in content


def test_write_session_file_creates_sessions_dir(tmp_path):
    """write_session_file creates the sessions directory if it does not exist."""
    sessions_dir = tmp_path / "nonexistent" / "sessions"
    assert not sessions_dir.exists()
    result_path = write_session_file(
        sessions_dir, "sess999", "/tmp/t.jsonl", "content"
    )
    assert sessions_dir.exists()
    assert result_path.exists()


def test_write_stub_summary_contains_metadata(tmp_path):
    """write_stub_summary writes a stub file with failure metadata and all four sections."""
    sessions_dir = tmp_path / "sessions"
    result_path = write_stub_summary(
        sessions_dir, "sess456", "/tmp/t.jsonl", 42, reason="timeout"
    )
    content = result_path.read_text()
    assert "session_id: sess456" in content
    assert "Extraction timeout" in content
    assert "42 messages" in content
    assert "## SUMMARY" in content
    assert "## CONVENTIONS" in content
    assert "## DECISIONS" in content
    assert "## GOTCHAS" in content


def test_write_stub_summary_on_failure_reason(tmp_path):
    """write_stub_summary with reason='error' contains 'Extraction error'."""
    sessions_dir = tmp_path / "sessions"
    result_path = write_stub_summary(
        sessions_dir, "sessErr", "/tmp/t.jsonl", 5, reason="error"
    )
    content = result_path.read_text()
    assert "Extraction error" in content


# ---------------------------------------------------------------------------
# Extraction subprocess tests (mocked)
# ---------------------------------------------------------------------------

def test_run_claude_extraction_returns_stdout_on_success(monkeypatch):
    """run_claude_extraction returns decoded stdout text when claude exits 0."""
    mock_proc = MagicMock()
    mock_proc.communicate.return_value = (b"## SUMMARY\nExtracted text", b"")
    mock_proc.returncode = 0
    mock_proc.pid = 12345

    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: mock_proc)
    result = run_claude_extraction("test prompt")
    assert result == "## SUMMARY\nExtracted text"


def test_run_claude_extraction_returns_none_on_timeout(monkeypatch):
    """run_claude_extraction kills process group and returns None on TimeoutExpired."""
    mock_proc = MagicMock()
    mock_proc.pid = 12345
    # First communicate raises TimeoutExpired; second (reap) returns empty
    mock_proc.communicate.side_effect = [
        subprocess.TimeoutExpired(cmd="claude", timeout=85),
        (b"", b""),
    ]

    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: mock_proc)

    import os
    monkeypatch.setattr(os, "getpgid", lambda pid: 12345)
    killpg_calls = []
    monkeypatch.setattr(os, "killpg", lambda pgid, sig: killpg_calls.append((pgid, sig)))

    result = run_claude_extraction("test prompt")
    assert result is None
    assert len(killpg_calls) == 1
    assert killpg_calls[0] == (12345, signal.SIGKILL)


def test_run_claude_extraction_returns_none_on_nonzero_exit(monkeypatch):
    """run_claude_extraction returns None when claude exits with non-zero returncode."""
    mock_proc = MagicMock()
    mock_proc.communicate.return_value = (b"error output", b"stderr")
    mock_proc.returncode = 1
    mock_proc.pid = 12345

    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: mock_proc)
    result = run_claude_extraction("test prompt")
    assert result is None


def test_run_claude_extraction_returns_none_on_empty_stdout(monkeypatch):
    """run_claude_extraction returns None (not empty string) when stdout is empty."""
    mock_proc = MagicMock()
    mock_proc.communicate.return_value = (b"", b"")
    mock_proc.returncode = 0
    mock_proc.pid = 12345

    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: mock_proc)
    result = run_claude_extraction("test prompt")
    assert result is None


def test_run_claude_extraction_returns_none_on_oserror(monkeypatch):
    """run_claude_extraction returns None when Popen raises FileNotFoundError."""
    monkeypatch.setattr(
        subprocess, "Popen", lambda *a, **kw: (_ for _ in ()).throw(FileNotFoundError("claude not found"))
    )
    result = run_claude_extraction("test prompt")
    assert result is None
