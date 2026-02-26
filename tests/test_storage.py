"""Tests for the storage module — ChromaDB indexing functions."""

import chromadb
import pytest
from pathlib import Path
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def ephemeral_client():
    """Return an in-memory ChromaDB client (no disk I/O, no model download).

    EphemeralClient instances share a singleton in-memory backend, so we clean
    up the collection before and after each test to ensure test isolation.
    """
    from thehook.storage import COLLECTION_NAME

    client = chromadb.EphemeralClient()
    # Pre-test cleanup: remove any data from previous tests
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass

    yield client

    # Post-test cleanup
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass


@pytest.fixture
def session_file(tmp_path):
    """Create a valid session markdown file with frontmatter."""
    content = (
        "---\n"
        "session_id: abc12345-test-uuid\n"
        "timestamp: 2026-02-24T10:00:00+00:00\n"
        "transcript_path: /tmp/transcript.jsonl\n"
        "---\n\n"
        "## SUMMARY\n"
        "Session covered ChromaDB integration.\n\n"
        "## CONVENTIONS\n"
        "- Use PersistentClient for local storage.\n\n"
        "## DECISIONS\n"
        "- ChromaDB for vector indexing.\n\n"
        "## GOTCHAS\n"
        "- Pass str() not Path() to PersistentClient.\n"
    )
    f = tmp_path / "2026-02-24-abc12345.md"
    f.write_text(content)
    return f


@pytest.fixture
def malformed_file(tmp_path):
    """Create a session file without frontmatter delimiters."""
    content = "No frontmatter here at all. Just plain text.\n"
    f = tmp_path / "2026-02-24-malformed.md"
    f.write_text(content)
    return f


@pytest.fixture
def empty_body_file(tmp_path):
    """Create a session file with frontmatter but empty/whitespace body."""
    content = (
        "---\n"
        "session_id: empty-body-session\n"
        "timestamp: 2026-02-24T10:00:00+00:00\n"
        "transcript_path: /tmp/transcript.jsonl\n"
        "---\n\n"
        "   \n"  # only whitespace after frontmatter
    )
    f = tmp_path / "2026-02-24-emptybody.md"
    f.write_text(content)
    return f


@pytest.fixture
def no_session_id_file(tmp_path):
    """Create a session file with frontmatter but no session_id field."""
    content = (
        "---\n"
        "timestamp: 2026-02-24T10:00:00+00:00\n"
        "transcript_path: /tmp/transcript.jsonl\n"
        "---\n\n"
        "## SUMMARY\n"
        "Session with no session_id in frontmatter.\n"
    )
    f = tmp_path / "2026-02-24-nosessionid.md"
    f.write_text(content)
    return f


@pytest.fixture
def knowledge_file(tmp_path):
    """Create a consolidated knowledge markdown file with knowledge frontmatter."""
    content = (
        "---\n"
        "knowledge_id: knowledge-2026-02-24-123456\n"
        "type: knowledge\n"
        "timestamp: 2026-02-24T12:00:00+00:00\n"
        "consolidated_until: 2026-02-24T11:59:59+00:00\n"
        "---\n\n"
        "## SUMMARY\n"
        "Consolidated memory across recent sessions.\n"
    )
    f = tmp_path / "2026-02-24-knowledge.md"
    f.write_text(content)
    return f


@pytest.fixture
def sessions_dir_with_files(tmp_path):
    """Create .thehook/sessions/ with several valid session files."""
    sessions = tmp_path / ".thehook" / "sessions"
    sessions.mkdir(parents=True)

    for i in range(3):
        content = (
            f"---\n"
            f"session_id: session-{i:04d}-uuid\n"
            f"timestamp: 2026-02-24T1{i}:00:00+00:00\n"
            f"transcript_path: /tmp/transcript-{i}.jsonl\n"
            f"---\n\n"
            f"## SUMMARY\n"
            f"Session {i} body content here.\n"
        )
        f = sessions / f"2026-02-24-session{i:04d}.md"
        f.write_text(content)

    return tmp_path


# ---------------------------------------------------------------------------
# Tests: get_chroma_client
# ---------------------------------------------------------------------------


def test_get_chroma_client_path(tmp_path):
    """get_chroma_client returns a client configured with the correct path."""
    from thehook.storage import get_chroma_client

    # We patch chromadb.PersistentClient to capture the path argument
    with patch("chromadb.PersistentClient") as mock_client:
        mock_client.return_value = chromadb.EphemeralClient()
        get_chroma_client(tmp_path)
        mock_client.assert_called_once()
        call_args = mock_client.call_args
        # path should be a str pointing to .thehook/chromadb
        actual_path = call_args[1].get("path") or call_args[0][0]
        expected_path = str(tmp_path / ".thehook" / "chromadb")
        assert actual_path == expected_path, (
            f"Expected path {expected_path!r}, got {actual_path!r}"
        )


# ---------------------------------------------------------------------------
# Tests: index_session_file
# ---------------------------------------------------------------------------


def test_index_session_file_adds_document(tmp_path, session_file, ephemeral_client):
    """After indexing, the collection contains 1 document with correct metadata."""
    from thehook.storage import index_session_file, COLLECTION_NAME

    with patch("thehook.storage.get_chroma_client", return_value=ephemeral_client):
        index_session_file(tmp_path, session_file)

    collection = ephemeral_client.get_or_create_collection(COLLECTION_NAME)
    results = collection.get()
    assert len(results["ids"]) == 1
    assert results["ids"][0] == "abc12345-test-uuid"
    assert results["metadatas"][0]["session_id"] == "abc12345-test-uuid"
    assert results["metadatas"][0]["type"] == "session"
    assert results["metadatas"][0]["timestamp"] == "2026-02-24T10:00:00+00:00"


def test_index_session_file_upsert_idempotent(tmp_path, session_file, ephemeral_client):
    """Calling index_session_file twice for the same file does not raise; collection has 1 doc."""
    from thehook.storage import index_session_file, COLLECTION_NAME

    with patch("thehook.storage.get_chroma_client", return_value=ephemeral_client):
        index_session_file(tmp_path, session_file)
        index_session_file(tmp_path, session_file)  # second call — must not raise

    collection = ephemeral_client.get_or_create_collection(COLLECTION_NAME)
    results = collection.get()
    assert len(results["ids"]) == 1, "Expected exactly 1 document after two identical upserts"


def test_index_session_file_skips_malformed(tmp_path, malformed_file, ephemeral_client):
    """File without frontmatter delimiters is silently skipped — no exception, no documents."""
    from thehook.storage import index_session_file, COLLECTION_NAME

    with patch("thehook.storage.get_chroma_client", return_value=ephemeral_client):
        index_session_file(tmp_path, malformed_file)  # must not raise

    collection = ephemeral_client.get_or_create_collection(COLLECTION_NAME)
    results = collection.get()
    assert len(results["ids"]) == 0, "Malformed file should produce no indexed documents"


def test_index_session_file_skips_empty_body(tmp_path, empty_body_file, ephemeral_client):
    """File with frontmatter but empty/whitespace body is silently skipped."""
    from thehook.storage import index_session_file, COLLECTION_NAME

    with patch("thehook.storage.get_chroma_client", return_value=ephemeral_client):
        index_session_file(tmp_path, empty_body_file)

    collection = ephemeral_client.get_or_create_collection(COLLECTION_NAME)
    results = collection.get()
    assert len(results["ids"]) == 0, "Empty-body file should produce no indexed documents"


def test_index_session_file_uses_filename_fallback(tmp_path, no_session_id_file, ephemeral_client):
    """File with no session_id in frontmatter uses filename stem as ChromaDB ID."""
    from thehook.storage import index_session_file, COLLECTION_NAME

    with patch("thehook.storage.get_chroma_client", return_value=ephemeral_client):
        index_session_file(tmp_path, no_session_id_file)

    collection = ephemeral_client.get_or_create_collection(COLLECTION_NAME)
    results = collection.get()
    assert len(results["ids"]) == 1
    # ID should be filename stem, not session_id (which was missing)
    assert results["ids"][0] == no_session_id_file.stem


def test_index_markdown_file_indexes_knowledge_docs(tmp_path, knowledge_file, ephemeral_client):
    """index_markdown_file supports knowledge docs with type=knowledge metadata."""
    from thehook.storage import index_markdown_file, COLLECTION_NAME

    with patch("thehook.storage.get_chroma_client", return_value=ephemeral_client):
        index_markdown_file(tmp_path, knowledge_file, default_type="knowledge")

    collection = ephemeral_client.get_or_create_collection(COLLECTION_NAME)
    results = collection.get()
    assert len(results["ids"]) == 1
    assert results["ids"][0] == "knowledge-2026-02-24-123456"
    assert results["metadatas"][0]["type"] == "knowledge"
    assert results["metadatas"][0]["knowledge_id"] == "knowledge-2026-02-24-123456"


# ---------------------------------------------------------------------------
# Tests: reindex
# ---------------------------------------------------------------------------


def test_reindex_drops_and_recreates(sessions_dir_with_files, ephemeral_client):
    """Pre-existing collection is dropped; after reindex, collection has exactly N valid documents."""
    from thehook.storage import reindex, COLLECTION_NAME

    project_dir = sessions_dir_with_files

    # Pre-populate the collection with a "stale" doc that should be gone after reindex
    stale_collection = ephemeral_client.get_or_create_collection(COLLECTION_NAME)
    stale_collection.add(
        documents=["stale document"],
        metadatas=[{"session_id": "stale", "type": "session", "timestamp": ""}],
        ids=["stale-doc-id"],
    )

    with patch("thehook.storage.get_chroma_client", return_value=ephemeral_client):
        count = reindex(project_dir)

    assert count == 3, f"Expected 3 indexed files, got {count}"
    fresh_collection = ephemeral_client.get_or_create_collection(COLLECTION_NAME)
    results = fresh_collection.get()
    assert len(results["ids"]) == 3, "Collection should have exactly 3 documents"
    # Stale doc must be gone
    assert "stale-doc-id" not in results["ids"]


def test_reindex_empty_dir(tmp_path, ephemeral_client):
    """reindex returns 0 gracefully when sessions dir exists but has no .md files."""
    from thehook.storage import reindex

    sessions = tmp_path / ".thehook" / "sessions"
    sessions.mkdir(parents=True)
    # No .md files inside

    with patch("thehook.storage.get_chroma_client", return_value=ephemeral_client):
        count = reindex(tmp_path)

    assert count == 0


def test_reindex_missing_dir(tmp_path, ephemeral_client):
    """reindex returns 0 gracefully when sessions dir does not exist at all."""
    from thehook.storage import reindex

    # Do NOT create .thehook/sessions/
    with patch("thehook.storage.get_chroma_client", return_value=ephemeral_client):
        count = reindex(tmp_path)

    assert count == 0


def test_reindex_skips_empty_body(tmp_path, ephemeral_client):
    """Files with empty body after frontmatter are not indexed by reindex."""
    from thehook.storage import reindex, COLLECTION_NAME

    sessions = tmp_path / ".thehook" / "sessions"
    sessions.mkdir(parents=True)

    # One valid file
    valid = sessions / "2026-02-24-valid001.md"
    valid.write_text(
        "---\n"
        "session_id: valid-session-001\n"
        "timestamp: 2026-02-24T10:00:00+00:00\n"
        "transcript_path: /tmp/t.jsonl\n"
        "---\n\n"
        "## SUMMARY\nThis session had content.\n"
    )

    # One empty-body file
    empty = sessions / "2026-02-24-empty002.md"
    empty.write_text(
        "---\n"
        "session_id: empty-session-002\n"
        "timestamp: 2026-02-24T11:00:00+00:00\n"
        "transcript_path: /tmp/t2.jsonl\n"
        "---\n\n"
        "   \n"
    )

    with patch("thehook.storage.get_chroma_client", return_value=ephemeral_client):
        count = reindex(tmp_path)

    assert count == 1, f"Expected 1 indexed file (empty body skipped), got {count}"
    collection = ephemeral_client.get_or_create_collection(COLLECTION_NAME)
    results = collection.get()
    assert len(results["ids"]) == 1
    assert results["ids"][0] == "valid-session-001"


def test_reindex_includes_knowledge_documents(tmp_path, ephemeral_client):
    """reindex indexes both sessions and consolidated knowledge docs."""
    from thehook.storage import reindex, COLLECTION_NAME

    sessions = tmp_path / ".thehook" / "sessions"
    sessions.mkdir(parents=True)
    knowledge = tmp_path / ".thehook" / "knowledge"
    knowledge.mkdir(parents=True)

    session_file = sessions / "2026-02-24-session.md"
    session_file.write_text(
        "---\n"
        "session_id: session-reindex-001\n"
        "timestamp: 2026-02-24T10:00:00+00:00\n"
        "---\n\n"
        "## SUMMARY\nSession content.\n"
    )
    knowledge_file = knowledge / "2026-02-24-knowledge.md"
    knowledge_file.write_text(
        "---\n"
        "knowledge_id: knowledge-reindex-001\n"
        "type: knowledge\n"
        "timestamp: 2026-02-24T11:00:00+00:00\n"
        "---\n\n"
        "## SUMMARY\nKnowledge content.\n"
    )

    with patch("thehook.storage.get_chroma_client", return_value=ephemeral_client):
        count = reindex(tmp_path)

    assert count == 2
    collection = ephemeral_client.get_or_create_collection(COLLECTION_NAME)
    results = collection.get()
    assert set(results["ids"]) == {"session-reindex-001", "knowledge-reindex-001"}
