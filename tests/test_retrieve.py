"""TDD tests for the retrieve module — query_sessions, format_context, run_retrieve."""

import json
import chromadb
import pytest
from pathlib import Path
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def project_with_index(tmp_path):
    """Create a tmp project dir with ChromaDB directory and one indexed document."""
    chroma_dir = tmp_path / ".thehook" / "chromadb"
    chroma_dir.mkdir(parents=True)
    return tmp_path


@pytest.fixture
def ephemeral_client():
    """Return an in-memory ChromaDB client for test isolation."""
    from thehook.storage import COLLECTION_NAME

    client = chromadb.EphemeralClient()
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass

    yield client

    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Tests: query_sessions
# ---------------------------------------------------------------------------


def test_query_sessions_returns_documents(tmp_path, ephemeral_client):
    """query_sessions returns a non-empty list after indexing a matching document."""
    from thehook.storage import index_session_file, COLLECTION_NAME

    # Create sessions dir and a session file with known content
    chroma_dir = tmp_path / ".thehook" / "chromadb"
    chroma_dir.mkdir(parents=True)

    session_content = (
        "---\n"
        "session_id: test-session-retrieve-001\n"
        "timestamp: 2026-02-24T10:00:00+00:00\n"
        "transcript_path: /tmp/transcript.jsonl\n"
        "---\n\n"
        "## SUMMARY\n"
        "Use PersistentClient for storage.\n\n"
        "## DECISIONS\n"
        "- PersistentClient provides disk-backed storage.\n"
    )
    session_file = tmp_path / "test_session.md"
    session_file.write_text(session_content)

    # Index the file
    with patch("thehook.storage.get_chroma_client", return_value=ephemeral_client):
        index_session_file(tmp_path, session_file)

    # Query — patch get_chroma_client in retrieve module to use ephemeral client
    with patch("thehook.storage.get_chroma_client", return_value=ephemeral_client):
        from thehook.retrieve import query_sessions
        results = query_sessions(tmp_path, "PersistentClient storage")

    assert isinstance(results, list), "query_sessions should return a list"
    assert len(results) > 0, "Should return at least one document"
    assert any("PersistentClient" in doc for doc in results), (
        "Result should contain the indexed content"
    )


def test_query_sessions_empty_collection(tmp_path, ephemeral_client):
    """query_sessions returns [] when the collection exists but is empty."""
    from thehook.storage import COLLECTION_NAME

    # Create the collection but add nothing to it
    chroma_dir = tmp_path / ".thehook" / "chromadb"
    chroma_dir.mkdir(parents=True)
    ephemeral_client.get_or_create_collection(COLLECTION_NAME)

    with patch("thehook.storage.get_chroma_client", return_value=ephemeral_client):
        from thehook.retrieve import query_sessions
        results = query_sessions(tmp_path, "anything")

    assert results == [], f"Expected [], got {results!r}"


def test_query_sessions_missing_collection(tmp_path):
    """query_sessions returns [] and raises no exception when collection does not exist."""
    # .thehook/chromadb exists but no collection was ever created
    chroma_dir = tmp_path / ".thehook" / "chromadb"
    chroma_dir.mkdir(parents=True)

    # Use a real EphemeralClient with no collections
    client = chromadb.EphemeralClient()

    with patch("thehook.storage.get_chroma_client", return_value=client):
        from thehook.retrieve import query_sessions
        results = query_sessions(tmp_path, "anything")

    assert results == [], f"Expected [] for missing collection, got {results!r}"


def test_query_sessions_respects_n_results(tmp_path):
    """query_sessions forwards n_results (capped by collection count)."""
    from thehook.retrieve import query_sessions
    from unittest.mock import MagicMock

    collection = MagicMock()
    collection.count.return_value = 10
    collection.query.return_value = {"documents": [["doc-a"]]}
    client = MagicMock()
    client.get_collection.return_value = collection

    with patch("thehook.storage.get_chroma_client", return_value=client):
        result = query_sessions(tmp_path, "query text", n_results=3)

    assert result == ["doc-a"]
    collection.query.assert_called_once_with(query_texts=["query text"], n_results=3)


def test_query_sessions_applies_recency_where_clause(tmp_path):
    """query_sessions includes metadata filter when recency_days > 0."""
    from thehook.retrieve import query_sessions
    from unittest.mock import MagicMock

    collection = MagicMock()
    collection.count.return_value = 10
    collection.query.return_value = {"documents": [["doc-recent"]]}
    client = MagicMock()
    client.get_collection.return_value = collection

    with patch("thehook.storage.get_chroma_client", return_value=client):
        result = query_sessions(tmp_path, "query text", n_results=2, recency_days=7)

    assert result == ["doc-recent"]
    assert collection.query.call_count == 1
    kwargs = collection.query.call_args.kwargs
    assert kwargs["query_texts"] == ["query text"]
    assert kwargs["n_results"] == 2
    assert "where" in kwargs
    assert "timestamp" in kwargs["where"]
    assert "$gte" in kwargs["where"]["timestamp"]


def test_query_sessions_recency_can_fallback_to_global(tmp_path):
    """When recency window is empty, query_sessions falls back to global search."""
    from thehook.retrieve import query_sessions
    from unittest.mock import MagicMock

    collection = MagicMock()
    collection.count.return_value = 10
    collection.query.side_effect = [
        {"documents": [[]]},          # recency-constrained result
        {"documents": [["doc-old"]]},  # global fallback result
    ]
    client = MagicMock()
    client.get_collection.return_value = collection

    with patch("thehook.storage.get_chroma_client", return_value=client):
        result = query_sessions(
            tmp_path,
            "query text",
            n_results=4,
            recency_days=30,
            recency_fallback_global=True,
        )

    assert result == ["doc-old"]
    assert collection.query.call_count == 2


def test_query_sessions_returns_knowledge_documents(tmp_path, ephemeral_client):
    """query_sessions can retrieve consolidated knowledge docs from same collection."""
    from thehook.storage import index_markdown_file
    from thehook.retrieve import query_sessions

    knowledge_content = (
        "---\n"
        "knowledge_id: knowledge-retrieve-001\n"
        "type: knowledge\n"
        "timestamp: 2026-02-24T12:00:00+00:00\n"
        "---\n\n"
        "## DECISIONS\n"
        "- Use periodic consolidation every 5 sessions.\n"
    )
    knowledge_file = tmp_path / "knowledge.md"
    knowledge_file.write_text(knowledge_content)

    with patch("thehook.storage.get_chroma_client", return_value=ephemeral_client):
        index_markdown_file(tmp_path, knowledge_file, default_type="knowledge")
        results = query_sessions(tmp_path, "periodic consolidation")

    assert len(results) > 0
    assert any("consolidation every 5 sessions" in doc for doc in results)


# ---------------------------------------------------------------------------
# Tests: format_context
# ---------------------------------------------------------------------------


def test_format_context_joins_documents():
    """format_context assembles documents with '---' separator."""
    from thehook.retrieve import format_context

    result = format_context(["doc one", "doc two"], token_budget=2000)

    assert "doc one" in result, "Result should contain first document"
    assert "doc two" in result, "Result should contain second document"
    assert "\n\n---\n\n" in result, "Documents should be joined with separator"


def test_format_context_truncates_to_budget():
    """format_context caps total chars at token_budget * 4."""
    from thehook.retrieve import format_context

    # token_budget=10 means max 40 chars
    # Build documents where total far exceeds 40 chars
    big_docs = ["A" * 100, "B" * 100, "C" * 100]
    result = format_context(big_docs, token_budget=10)

    assert len(result) <= 40, (
        f"Result length {len(result)} exceeds token_budget * 4 = 40"
    )


def test_format_context_empty_list():
    """format_context returns empty string for an empty document list."""
    from thehook.retrieve import format_context

    result = format_context([], token_budget=2000)

    assert result == "", f"Expected empty string, got {result!r}"


# ---------------------------------------------------------------------------
# Tests: run_retrieve
# ---------------------------------------------------------------------------


def test_run_retrieve_outputs_valid_json(tmp_path, capsys):
    """run_retrieve prints valid hookSpecificOutput JSON when documents are found."""
    from thehook.retrieve import run_retrieve

    hook_input = {"cwd": str(tmp_path), "session_id": "test-session"}

    with patch("thehook.capture.read_hook_input", return_value=hook_input):
        with patch("thehook.retrieve.query_sessions", return_value=["doc1", "doc2"]):
            run_retrieve()

    captured = capsys.readouterr()
    assert captured.out.strip(), "run_retrieve should print JSON when documents found"

    output = json.loads(captured.out.strip())
    assert "hookSpecificOutput" in output, "Output must have 'hookSpecificOutput' key"
    hook_specific = output["hookSpecificOutput"]
    assert hook_specific.get("hookEventName") == "SessionStart", (
        "hookEventName must be 'SessionStart'"
    )
    assert "additionalContext" in hook_specific, (
        "hookSpecificOutput must contain 'additionalContext'"
    )
    assert "doc1" in hook_specific["additionalContext"], (
        "additionalContext should contain the retrieved document text"
    )


def test_run_retrieve_no_output_on_empty(tmp_path, capsys):
    """run_retrieve prints nothing when no documents are found."""
    from thehook.retrieve import run_retrieve

    hook_input = {"cwd": str(tmp_path)}

    with patch("thehook.capture.read_hook_input", return_value=hook_input):
        with patch("thehook.retrieve.query_sessions", return_value=[]):
            run_retrieve()

    captured = capsys.readouterr()
    assert captured.out == "", (
        f"run_retrieve should print nothing when no context found, got: {captured.out!r}"
    )


def test_run_retrieve_uses_config_token_budget(tmp_path, capsys):
    """run_retrieve reads token_budget from thehook.yaml and enforces it."""
    from thehook.retrieve import run_retrieve

    # Write config with small token budget
    config_file = tmp_path / "thehook.yaml"
    config_file.write_text("token_budget: 500\n")

    hook_input = {"cwd": str(tmp_path)}
    # Large document that exceeds 500 * 4 = 2000 chars
    large_doc = "a" * 5000

    with patch("thehook.capture.read_hook_input", return_value=hook_input):
        with patch("thehook.retrieve.query_sessions", return_value=[large_doc]):
            run_retrieve()

    captured = capsys.readouterr()
    assert captured.out.strip(), "run_retrieve should print JSON when documents found"

    output = json.loads(captured.out.strip())
    additional_context = output["hookSpecificOutput"]["additionalContext"]
    max_chars = 500 * 4  # 2000 chars
    assert len(additional_context) <= max_chars, (
        f"additionalContext length {len(additional_context)} exceeds token_budget * 4 = {max_chars}"
    )


def test_run_retrieve_uses_user_prompt_for_query(tmp_path, capsys):
    """UserPromptSubmit uses the incoming prompt as semantic retrieval query."""
    from thehook.retrieve import run_retrieve

    hook_input = {
        "cwd": str(tmp_path),
        "hook_event_name": "UserPromptSubmit",
        "prompt": "How did we decide auth token rotation?",
    }

    with patch("thehook.capture.read_hook_input", return_value=hook_input):
        with patch("thehook.retrieve.query_sessions", return_value=["doc-auth"]) as mock_query:
            run_retrieve()

    captured = capsys.readouterr()
    assert captured.out.strip(), "run_retrieve should print JSON when documents found"

    output = json.loads(captured.out.strip())
    hook_specific = output["hookSpecificOutput"]
    assert hook_specific.get("hookEventName") == "UserPromptSubmit"
    assert "doc-auth" in hook_specific["additionalContext"]

    mock_query.assert_called_once_with(
        tmp_path,
        query_text="How did we decide auth token rotation?",
        n_results=5,
        recency_days=0,
        recency_fallback_global=True,
    )


def test_run_retrieve_passes_retrieval_tuning_from_config(tmp_path, capsys):
    """run_retrieve forwards retrieval knobs from thehook.yaml into query_sessions."""
    from thehook.retrieve import run_retrieve

    (tmp_path / "thehook.yaml").write_text(
        "retrieval_n_results: 2\n"
        "retrieval_recency_days: 14\n"
        "retrieval_recency_fallback_global: false\n"
    )

    hook_input = {
        "cwd": str(tmp_path),
        "hook_event_name": "UserPromptSubmit",
        "prompt": "database migration policy",
    }

    with patch("thehook.capture.read_hook_input", return_value=hook_input):
        with patch("thehook.retrieve.query_sessions", return_value=["doc-db"]) as mock_query:
            run_retrieve()

    captured = capsys.readouterr()
    assert captured.out.strip(), "run_retrieve should print JSON when documents found"

    mock_query.assert_called_once_with(
        tmp_path,
        query_text="database migration policy",
        n_results=2,
        recency_days=14,
        recency_fallback_global=False,
    )


# ---------------------------------------------------------------------------
# CLI integration tests: retrieve and recall subcommands
# ---------------------------------------------------------------------------


def test_cli_retrieve_command(tmp_path, ephemeral_client):
    """thehook retrieve reads stdin JSON and outputs hookSpecificOutput JSON."""
    from click.testing import CliRunner
    from thehook.cli import main
    from thehook.storage import index_session_file

    # Set up project with indexed session
    chroma_dir = tmp_path / ".thehook" / "chromadb"
    chroma_dir.mkdir(parents=True)

    session_content = (
        "---\n"
        "session_id: cli-retrieve-001\n"
        "timestamp: 2026-02-24T10:00:00+00:00\n"
        "transcript_path: /tmp/transcript.jsonl\n"
        "---\n\n"
        "## SUMMARY\n"
        "Always use dependency injection for testability.\n\n"
        "## CONVENTIONS\n"
        "- Prefer composition over inheritance.\n"
    )
    session_file = tmp_path / "session.md"
    session_file.write_text(session_content)

    with patch("thehook.storage.get_chroma_client", return_value=ephemeral_client):
        index_session_file(tmp_path, session_file)

    # Invoke the retrieve CLI command with stdin JSON
    hook_input = json.dumps({"cwd": str(tmp_path), "session_id": "test123"})

    with patch("thehook.storage.get_chroma_client", return_value=ephemeral_client):
        runner = CliRunner()
        result = runner.invoke(main, ["retrieve"], input=hook_input)

    assert result.exit_code == 0, f"Non-zero exit: {result.output}"
    output = json.loads(result.output.strip())
    assert "hookSpecificOutput" in output
    assert output["hookSpecificOutput"]["additionalContext"]


def test_cli_retrieve_no_collection(tmp_path, ephemeral_client):
    """thehook retrieve produces no output when collection is empty."""
    from click.testing import CliRunner
    from thehook.cli import main

    chroma_dir = tmp_path / ".thehook" / "chromadb"
    chroma_dir.mkdir(parents=True)

    hook_input = json.dumps({"cwd": str(tmp_path)})

    with patch("thehook.storage.get_chroma_client", return_value=ephemeral_client):
        runner = CliRunner()
        result = runner.invoke(main, ["retrieve"], input=hook_input)

    assert result.exit_code == 0, f"Non-zero exit: {result.output}"
    assert result.output.strip() == "", (
        f"Expected no output for empty collection, got: {result.output!r}"
    )


def test_cli_recall_prints_results(tmp_path, ephemeral_client):
    """thehook recall <query> prints matching documents from indexed sessions."""
    from click.testing import CliRunner
    from thehook.cli import main
    from thehook.storage import index_session_file

    # Set up project with indexed session
    chroma_dir = tmp_path / ".thehook" / "chromadb"
    chroma_dir.mkdir(parents=True)
    sessions_dir = tmp_path / ".thehook" / "sessions"
    sessions_dir.mkdir(parents=True)

    session_content = (
        "---\n"
        "session_id: cli-recall-001\n"
        "timestamp: 2026-02-24T10:00:00+00:00\n"
        "transcript_path: /tmp/transcript.jsonl\n"
        "---\n\n"
        "## CONVENTIONS\n"
        "- Always write docstrings for public functions.\n"
        "- Use type hints on all function signatures.\n"
    )
    session_file = sessions_dir / "cli-recall-001.md"
    session_file.write_text(session_content)

    with patch("thehook.storage.get_chroma_client", return_value=ephemeral_client):
        index_session_file(tmp_path, session_file)

    # Invoke recall CLI
    with patch("thehook.storage.get_chroma_client", return_value=ephemeral_client):
        runner = CliRunner()
        result = runner.invoke(main, ["recall", "conventions", "--path", str(tmp_path)])

    assert result.exit_code == 0, f"Non-zero exit: {result.output}"
    assert "docstrings" in result.output, (
        f"Expected indexed content in output, got: {result.output!r}"
    )


def test_cli_recall_empty_collection(tmp_path, ephemeral_client):
    """thehook recall prints 'No relevant knowledge found.' when collection is empty."""
    from click.testing import CliRunner
    from thehook.cli import main

    chroma_dir = tmp_path / ".thehook" / "chromadb"
    chroma_dir.mkdir(parents=True)

    with patch("thehook.storage.get_chroma_client", return_value=ephemeral_client):
        runner = CliRunner()
        result = runner.invoke(main, ["recall", "anything", "--path", str(tmp_path)])

    assert result.exit_code == 0, f"Non-zero exit: {result.output}"
    assert "No relevant knowledge found." in result.output
