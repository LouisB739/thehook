"""ChromaDB indexing functions for session markdown files."""

from pathlib import Path

COLLECTION_NAME = "thehook_sessions"


def get_chroma_client(project_dir: Path):
    """Return a PersistentClient pointing at .thehook/chromadb/.

    Args:
        project_dir: Project root directory (contains .thehook/).

    Returns:
        chromadb.ClientAPI: Configured PersistentClient instance.
    """
    import chromadb

    chroma_path = project_dir / ".thehook" / "chromadb"
    return chromadb.PersistentClient(path=str(chroma_path))


def index_session_file(project_dir: Path, session_path: Path) -> None:
    """Add a session markdown file to the ChromaDB index.

    Parses YAML frontmatter from the session file, extracts the body, and
    upserts the document into the ChromaDB collection. The operation is
    idempotent — calling it twice for the same session_id overwrites rather
    than raising a duplicate error.

    Silently returns (no exception) when:
    - The file does not contain frontmatter delimiters (malformed).
    - The body after frontmatter is empty or whitespace only.

    Uses filename stem as ChromaDB document ID if session_id is missing from
    frontmatter — the filename is guaranteed unique by write_session_file().

    Args:
        project_dir: Project root directory (contains .thehook/).
        session_path: Path to the session .md file to index.
    """
    import yaml

    content = session_path.read_text()
    parts = content.split("---", 2)
    if len(parts) < 3:
        return  # malformed: no frontmatter delimiters

    fm = yaml.safe_load(parts[1]) or {}
    body = parts[2].strip()
    if not body:
        return  # empty body — skip to avoid bad embeddings

    session_id = fm.get("session_id") or session_path.stem
    raw_ts = fm.get("timestamp", "")
    # PyYAML parses ISO 8601 timestamps as datetime objects; use isoformat() to
    # round-trip back to the canonical string form (preserves the 'T' separator).
    if hasattr(raw_ts, "isoformat"):
        timestamp = raw_ts.isoformat()
    else:
        timestamp = str(raw_ts)

    client = get_chroma_client(project_dir)
    collection = client.get_or_create_collection(COLLECTION_NAME)
    collection.upsert(
        documents=[body],
        metadatas=[{
            "session_id": session_id,
            "type": "session",
            "timestamp": timestamp,
        }],
        ids=[session_id],
    )


def reindex(project_dir: Path) -> int:
    """Drop and recreate the ChromaDB index from all session markdown files.

    Deletes the existing collection (if any), creates a fresh one, then reads
    all .md files from .thehook/sessions/, parses frontmatter + body, and
    batch-adds all valid documents in a single collection.add() call.

    Skips files where:
    - Frontmatter delimiters are missing (malformed).
    - Body after frontmatter is empty or whitespace only.

    Returns 0 gracefully when:
    - The sessions directory does not exist.
    - The sessions directory contains no .md files.

    Args:
        project_dir: Project root directory (contains .thehook/).

    Returns:
        int: Number of session files successfully indexed.
    """
    import yaml

    client = get_chroma_client(project_dir)

    # Drop existing collection to start fresh
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass  # collection didn't exist yet — that's fine

    collection = client.get_or_create_collection(COLLECTION_NAME)

    sessions_dir = project_dir / ".thehook" / "sessions"
    if not sessions_dir.exists():
        return 0

    md_files = sorted(sessions_dir.glob("*.md"))
    if not md_files:
        return 0

    documents = []
    metadatas = []
    ids = []

    for md_file in md_files:
        content = md_file.read_text()
        parts = content.split("---", 2)
        if len(parts) < 3:
            continue  # malformed, skip

        fm = yaml.safe_load(parts[1]) or {}
        body = parts[2].strip()
        if not body:
            continue  # empty body, skip

        session_id = fm.get("session_id") or md_file.stem
        raw_ts = fm.get("timestamp", "")
        # PyYAML parses ISO 8601 timestamps as datetime objects; use isoformat() to
        # round-trip back to the canonical string form (preserves the 'T' separator).
        if hasattr(raw_ts, "isoformat"):
            timestamp = raw_ts.isoformat()
        else:
            timestamp = str(raw_ts)

        documents.append(body)
        metadatas.append({
            "session_id": session_id,
            "type": "session",
            "timestamp": timestamp,
        })
        ids.append(session_id)

    if documents:
        collection.add(documents=documents, metadatas=metadatas, ids=ids)

    return len(documents)


def get_index_count(project_dir: Path) -> int:
    """Return the number of documents in the ChromaDB collection, or 0 if none.

    Useful to verify that the index is populated (e.g. thehook status).
    """
    try:
        client = get_chroma_client(project_dir)
        collection = client.get_collection(COLLECTION_NAME)
        return collection.count()
    except Exception:
        return 0
