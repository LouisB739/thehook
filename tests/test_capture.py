"""Tests for transcript parsing and hook input reading (capture pipeline)."""
import io
import json
import signal
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from thehook.capture import (
    EXTRACTION_PROMPT_TEMPLATE,
    INTERMEDIATE_EXTRACTION_PROMPT_TEMPLATE,
    assemble_transcript_text,
    parse_transcript,
    read_hook_input,
    run_capture,
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


# ---------------------------------------------------------------------------
# Extraction prompt tests (CAPT-06)
# ---------------------------------------------------------------------------

def test_extraction_prompt_targets_conventions():
    """EXTRACTION_PROMPT_TEMPLATE must mention 'conventions' and 'decisions' as targets."""
    assert "conventions" in EXTRACTION_PROMPT_TEMPLATE.lower()
    assert "decisions" in EXTRACTION_PROMPT_TEMPLATE.lower()


def test_extraction_prompt_excludes_observations():
    """EXTRACTION_PROMPT_TEMPLATE must NOT contain the word 'observations' (per CAPT-06)."""
    assert "observations" not in EXTRACTION_PROMPT_TEMPLATE.lower()


def test_extraction_prompt_has_all_four_sections():
    """EXTRACTION_PROMPT_TEMPLATE must contain all four section headers."""
    assert "## SUMMARY" in EXTRACTION_PROMPT_TEMPLATE
    assert "## CONVENTIONS" in EXTRACTION_PROMPT_TEMPLATE
    assert "## DECISIONS" in EXTRACTION_PROMPT_TEMPLATE
    assert "## GOTCHAS" in EXTRACTION_PROMPT_TEMPLATE


# ---------------------------------------------------------------------------
# run_capture orchestration tests (CAPT-04)
# ---------------------------------------------------------------------------

def test_run_capture_success_writes_session_file(tmp_project, monkeypatch):
    """run_capture writes a session .md file when extraction succeeds."""
    fixture_path = Path(__file__).parent / "fixtures" / "sample_transcript.jsonl"
    sessions_dir = tmp_project / ".thehook" / "sessions"
    sessions_dir.mkdir(parents=True)

    hook_input = json.dumps({
        "session_id": "test123",
        "transcript_path": str(fixture_path),
        "cwd": str(tmp_project),
    })
    monkeypatch.setattr(sys, "stdin", io.StringIO(hook_input))

    extraction_result = (
        "## SUMMARY\nTest session.\n\n"
        "## CONVENTIONS\n- Use pytest\n\n"
        "## DECISIONS\n- Chose Click\n\n"
        "## GOTCHAS\nNone this session."
    )
    monkeypatch.setattr(
        "thehook.capture.run_claude_extraction",
        lambda *args, **kwargs: extraction_result,
    )

    run_capture()

    md_files = list(sessions_dir.glob("*.md"))
    assert len(md_files) == 1, f"Expected 1 session file, got {len(md_files)}"
    content = md_files[0].read_text()
    assert "session_id: test123" in content
    assert "## SUMMARY" in content
    assert "## CONVENTIONS" in content


def test_run_capture_extraction_failure_writes_stub(tmp_project, monkeypatch):
    """run_capture writes a stub file when extraction returns None."""
    fixture_path = Path(__file__).parent / "fixtures" / "sample_transcript.jsonl"
    sessions_dir = tmp_project / ".thehook" / "sessions"
    sessions_dir.mkdir(parents=True)

    hook_input = json.dumps({
        "session_id": "test123",
        "transcript_path": str(fixture_path),
        "cwd": str(tmp_project),
    })
    monkeypatch.setattr(sys, "stdin", io.StringIO(hook_input))
    monkeypatch.setattr("thehook.capture.run_claude_extraction", lambda *args, **kwargs: None)

    run_capture()

    md_files = list(sessions_dir.glob("*.md"))
    assert len(md_files) == 1
    content = md_files[0].read_text()
    assert "Extraction timeout" in content
    assert "session_id: test123" in content


def test_run_capture_empty_transcript_writes_stub(tmp_project, monkeypatch):
    """run_capture writes a stub with 'empty transcript' when transcript file does not exist."""
    sessions_dir = tmp_project / ".thehook" / "sessions"
    sessions_dir.mkdir(parents=True)

    hook_input = json.dumps({
        "session_id": "test123",
        "transcript_path": str(tmp_project / "nonexistent.jsonl"),
        "cwd": str(tmp_project),
    })
    monkeypatch.setattr(sys, "stdin", io.StringIO(hook_input))

    run_capture()

    md_files = list(sessions_dir.glob("*.md"))
    assert len(md_files) == 1
    content = md_files[0].read_text()
    assert "empty transcript" in content


def test_run_capture_invalid_stdin_returns_silently(monkeypatch):
    """run_capture returns silently and does not raise when stdin is not valid JSON."""
    monkeypatch.setattr(sys, "stdin", io.StringIO("not json"))
    # Should not raise
    run_capture()


# ---------------------------------------------------------------------------
# CLI integration test
# ---------------------------------------------------------------------------

def test_cli_capture_command_exists():
    """The 'capture' subcommand is registered in the CLI and shows help text."""
    from click.testing import CliRunner
    from thehook.cli import main

    runner = CliRunner()
    result = runner.invoke(main, ["capture", "--help"])
    assert result.exit_code == 0
    assert "capture" in result.output.lower() or "extract" in result.output.lower()


def test_cli_capture_lite_command_exists():
    """The 'capture-lite' subcommand is registered in the CLI."""
    from click.testing import CliRunner
    from thehook.cli import main

    runner = CliRunner()
    result = runner.invoke(main, ["capture-lite", "--help"])
    assert result.exit_code == 0
    assert "lite" in result.output.lower()


# ---------------------------------------------------------------------------
# Storage integration tests — index_session_file wiring in run_capture
# ---------------------------------------------------------------------------

def test_run_capture_calls_index_session_file(tmp_project, monkeypatch):
    """run_capture calls index_session_file after a successful extraction write."""
    fixture_path = Path(__file__).parent / "fixtures" / "sample_transcript.jsonl"
    sessions_dir = tmp_project / ".thehook" / "sessions"
    sessions_dir.mkdir(parents=True)

    hook_input = json.dumps({
        "session_id": "test-index-01",
        "transcript_path": str(fixture_path),
        "cwd": str(tmp_project),
    })
    monkeypatch.setattr(sys, "stdin", io.StringIO(hook_input))

    extraction_result = (
        "## SUMMARY\nTest session.\n\n"
        "## CONVENTIONS\n- Use pytest\n\n"
        "## DECISIONS\n- Chose Click\n\n"
        "## GOTCHAS\nNone this session."
    )
    monkeypatch.setattr(
        "thehook.capture.run_claude_extraction",
        lambda *args, **kwargs: extraction_result,
    )

    index_calls = []

    def fake_index(project_dir, session_path):
        index_calls.append((project_dir, session_path))

    with patch("thehook.storage.index_session_file", fake_index):
        run_capture()

    assert len(index_calls) == 1, f"Expected 1 index call, got {len(index_calls)}"
    project_dir_used, session_path_used = index_calls[0]
    assert project_dir_used == tmp_project
    assert session_path_used.suffix == ".md"
    assert session_path_used.exists()


def test_run_capture_index_failure_does_not_crash(tmp_project, monkeypatch):
    """run_capture completes without raising when index_session_file raises an exception."""
    fixture_path = Path(__file__).parent / "fixtures" / "sample_transcript.jsonl"
    sessions_dir = tmp_project / ".thehook" / "sessions"
    sessions_dir.mkdir(parents=True)

    hook_input = json.dumps({
        "session_id": "test-index-crash",
        "transcript_path": str(fixture_path),
        "cwd": str(tmp_project),
    })
    monkeypatch.setattr(sys, "stdin", io.StringIO(hook_input))
    monkeypatch.setattr(
        "thehook.capture.run_claude_extraction",
        lambda *args, **kwargs: "## SUMMARY\nOK.",
    )

    def exploding_index(project_dir, session_path):
        raise RuntimeError("ChromaDB is down")

    with patch("thehook.storage.index_session_file", exploding_index):
        # Must NOT raise
        run_capture()

    # Session file was still written despite index failure
    md_files = list((tmp_project / ".thehook" / "sessions").glob("*.md"))
    assert len(md_files) == 1


def test_run_capture_stub_also_indexes(tmp_project, monkeypatch):
    """run_capture calls index_session_file for stub files written on extraction failure."""
    fixture_path = Path(__file__).parent / "fixtures" / "sample_transcript.jsonl"
    sessions_dir = tmp_project / ".thehook" / "sessions"
    sessions_dir.mkdir(parents=True)

    hook_input = json.dumps({
        "session_id": "test-stub-index",
        "transcript_path": str(fixture_path),
        "cwd": str(tmp_project),
    })
    monkeypatch.setattr(sys, "stdin", io.StringIO(hook_input))
    # Trigger stub path by returning None from extraction
    monkeypatch.setattr(
        "thehook.capture.run_claude_extraction",
        lambda *args, **kwargs: None,
    )

    index_calls = []

    def fake_index(project_dir, session_path):
        index_calls.append((project_dir, session_path))

    with patch("thehook.storage.index_session_file", fake_index):
        run_capture()

    assert len(index_calls) == 1, f"Expected 1 index call for stub, got {len(index_calls)}"
    _, session_path_used = index_calls[0]
    # Stub file should exist and contain the timeout reason
    assert session_path_used.exists()
    assert "timeout" in session_path_used.read_text()


def test_cli_reindex_command(tmp_path, monkeypatch):
    """thehook reindex --path <dir> prints the indexed file count."""
    from click.testing import CliRunner
    from thehook.cli import main

    # Mock the storage.reindex function so no real ChromaDB is needed
    with patch("thehook.storage.reindex", return_value=3) as mock_reindex:
        runner = CliRunner()
        result = runner.invoke(main, ["reindex", "--path", str(tmp_path)])

    assert result.exit_code == 0, f"Non-zero exit: {result.output}"
    assert "Reindexed 3 session files." in result.output


def test_intermediate_prompt_has_all_four_sections():
    """INTERMEDIATE_EXTRACTION_PROMPT_TEMPLATE must contain all four section headers."""
    assert "## SUMMARY" in INTERMEDIATE_EXTRACTION_PROMPT_TEMPLATE
    assert "## CONVENTIONS" in INTERMEDIATE_EXTRACTION_PROMPT_TEMPLATE
    assert "## DECISIONS" in INTERMEDIATE_EXTRACTION_PROMPT_TEMPLATE
    assert "## GOTCHAS" in INTERMEDIATE_EXTRACTION_PROMPT_TEMPLATE


def test_run_capture_lite_respects_disabled_config(tmp_project, monkeypatch):
    """run_capture(mode='lite') returns without writing when intermediate capture is disabled."""
    fixture_path = Path(__file__).parent / "fixtures" / "sample_transcript.jsonl"
    sessions_dir = tmp_project / ".thehook" / "sessions"
    sessions_dir.mkdir(parents=True)
    (tmp_project / "thehook.yaml").write_text("intermediate_capture_enabled: false\n")

    hook_input = json.dumps({
        "session_id": "test-lite-disabled",
        "transcript_path": str(fixture_path),
        "cwd": str(tmp_project),
    })
    monkeypatch.setattr(sys, "stdin", io.StringIO(hook_input))
    monkeypatch.setattr(
        "thehook.capture.run_claude_extraction",
        lambda *args, **kwargs: "## SUMMARY\nShould not be written",
    )

    run_capture(mode="lite")
    assert list(sessions_dir.glob("*.md")) == []


def test_run_capture_lite_throttles_repeated_calls(tmp_project, monkeypatch):
    """run_capture(mode='lite') skips a second immediate capture due to min interval."""
    fixture_path = Path(__file__).parent / "fixtures" / "sample_transcript.jsonl"
    sessions_dir = tmp_project / ".thehook" / "sessions"
    sessions_dir.mkdir(parents=True)
    (tmp_project / "thehook.yaml").write_text("intermediate_capture_min_interval_seconds: 3600\n")

    extraction_calls = []

    def fake_extract(*args, **kwargs):
        extraction_calls.append(1)
        return (
            "## SUMMARY\nIntermediate session.\n\n"
            "## CONVENTIONS\nNone this session.\n\n"
            "## DECISIONS\nNone this session.\n\n"
            "## GOTCHAS\nNone this session."
        )

    monkeypatch.setattr("thehook.capture.run_claude_extraction", fake_extract)

    payload = json.dumps({
        "session_id": "test-lite-throttle",
        "transcript_path": str(fixture_path),
        "cwd": str(tmp_project),
    })

    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))
    run_capture(mode="lite")
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))
    run_capture(mode="lite")

    assert len(extraction_calls) == 1
    assert len(list(sessions_dir.glob("*.md"))) == 1


def test_run_capture_lite_failure_skips_stub_write(tmp_project, monkeypatch):
    """run_capture(mode='lite') does not write stub files on extraction failure."""
    fixture_path = Path(__file__).parent / "fixtures" / "sample_transcript.jsonl"
    sessions_dir = tmp_project / ".thehook" / "sessions"
    sessions_dir.mkdir(parents=True)

    hook_input = json.dumps({
        "session_id": "test-lite-failure",
        "transcript_path": str(fixture_path),
        "cwd": str(tmp_project),
    })
    monkeypatch.setattr(sys, "stdin", io.StringIO(hook_input))
    monkeypatch.setattr("thehook.capture.run_claude_extraction", lambda *args, **kwargs: None)

    run_capture(mode="lite")
    assert list(sessions_dir.glob("*.md")) == []


def test_run_capture_full_triggers_auto_consolidation_at_threshold(tmp_project, monkeypatch):
    """run_capture(full) writes a knowledge doc when pending sessions hit threshold."""
    fixture_path = Path(__file__).parent / "fixtures" / "sample_transcript.jsonl"
    sessions_dir = tmp_project / ".thehook" / "sessions"
    sessions_dir.mkdir(parents=True)

    # Seed 4 existing sessions so the new full capture reaches threshold=5.
    for idx in range(4):
        existing = (
            "---\n"
            f"session_id: seeded-{idx}\n"
            f"timestamp: 2026-02-24T0{idx}:00:00+00:00\n"
            f"transcript_path: /tmp/seed-{idx}.jsonl\n"
            "---\n\n"
            "## SUMMARY\nSeeded session.\n\n"
            "## CONVENTIONS\nNone this session.\n\n"
            "## DECISIONS\nNone this session.\n\n"
            "## GOTCHAS\nNone this session.\n"
        )
        (sessions_dir / f"2026-02-24-seeded-{idx}.md").write_text(existing)

    hook_input = json.dumps({
        "session_id": "test-consolidation",
        "transcript_path": str(fixture_path),
        "cwd": str(tmp_project),
    })
    monkeypatch.setattr(sys, "stdin", io.StringIO(hook_input))

    extraction_outputs = [
        (
            "## SUMMARY\nFresh session.\n\n"
            "## CONVENTIONS\n- Keep tests close to feature code.\n\n"
            "## DECISIONS\n- Use Python for hooks.\n\n"
            "## GOTCHAS\n- Beware stale caches.\n"
        ),
        (
            "## SUMMARY\nConsolidated memory.\n\n"
            "## CONVENTIONS\n- Keep tests close to feature code.\n\n"
            "## DECISIONS\n- Use Python for hooks.\n\n"
            "## GOTCHAS\n- Beware stale caches.\n"
        ),
    ]
    monkeypatch.setattr(
        "thehook.capture.run_claude_extraction",
        lambda *args, **kwargs: extraction_outputs.pop(0),
    )

    run_capture(mode="full")

    knowledge_files = list((tmp_project / ".thehook" / "knowledge").glob("*.md"))
    assert len(knowledge_files) == 1
    text = knowledge_files[0].read_text()
    assert "type: knowledge" in text
    assert "source_session_count: 5" in text


def test_run_capture_full_skips_consolidation_below_threshold(tmp_project, monkeypatch):
    """run_capture(full) does not consolidate when pending sessions are below threshold."""
    fixture_path = Path(__file__).parent / "fixtures" / "sample_transcript.jsonl"
    sessions_dir = tmp_project / ".thehook" / "sessions"
    sessions_dir.mkdir(parents=True)
    (tmp_project / "thehook.yaml").write_text("consolidation_threshold: 10\n")

    hook_input = json.dumps({
        "session_id": "test-no-consolidation",
        "transcript_path": str(fixture_path),
        "cwd": str(tmp_project),
    })
    monkeypatch.setattr(sys, "stdin", io.StringIO(hook_input))
    monkeypatch.setattr(
        "thehook.capture.run_claude_extraction",
        lambda *args, **kwargs: (
            "## SUMMARY\nFresh session.\n\n"
            "## CONVENTIONS\nNone this session.\n\n"
            "## DECISIONS\nNone this session.\n\n"
            "## GOTCHAS\nNone this session."
        ),
    )

    run_capture(mode="full")
    knowledge_files = list((tmp_project / ".thehook" / "knowledge").glob("*.md"))
    assert knowledge_files == []
