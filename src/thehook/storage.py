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


def _parse_markdown_file(path: Path) -> tuple[dict, str] | None:
    """Parse TheHook markdown file and return (frontmatter, body)."""
    import yaml

    content = path.read_text()
    parts = content.split("---", 2)
    if len(parts) < 3:
        return None
    fm = yaml.safe_load(parts[1]) or {}
    body = parts[2].strip()
    if not body:
        return None
    return fm, body


def _normalize_timestamp(raw_ts) -> str:
    if hasattr(raw_ts, "isoformat"):
        return raw_ts.isoformat()
    return str(raw_ts)


def _build_doc_id(frontmatter: dict, fallback_stem: str, default_type: str) -> str:
    if default_type == "knowledge":
        return frontmatter.get("knowledge_id") or fallback_stem
    return frontmatter.get("session_id") or fallback_stem


def index_markdown_file(project_dir: Path, path: Path, default_type: str = "session") -> None:
    """Upsert a TheHook markdown document into ChromaDB.

    Supports both session docs and consolidated knowledge docs.
    """
    parsed = _parse_markdown_file(path)
    if not parsed:
        return

    frontmatter, body = parsed
    doc_type = frontmatter.get("type") or default_type
    doc_id = _build_doc_id(frontmatter, path.stem, default_type)
    timestamp = _normalize_timestamp(frontmatter.get("timestamp", ""))

    metadata = {
        "type": str(doc_type),
        "timestamp": timestamp,
    }
    if "session_id" in frontmatter:
        metadata["session_id"] = str(frontmatter.get("session_id"))
    if "knowledge_id" in frontmatter:
        metadata["knowledge_id"] = str(frontmatter.get("knowledge_id"))

    client = get_chroma_client(project_dir)
    collection = client.get_or_create_collection(COLLECTION_NAME)
    collection.upsert(documents=[body], metadatas=[metadata], ids=[str(doc_id)])


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
    index_markdown_file(project_dir, session_path, default_type="session")


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
    client = get_chroma_client(project_dir)

    # Drop existing collection to start fresh
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass  # collection didn't exist yet — that's fine

    collection = client.get_or_create_collection(COLLECTION_NAME)

    sessions_dir = project_dir / ".thehook" / "sessions"
    knowledge_dir = project_dir / ".thehook" / "knowledge"

    documents = []
    metadatas = []
    ids = []

    all_files: list[tuple[Path, str]] = []
    if sessions_dir.exists():
        all_files.extend((path, "session") for path in sorted(sessions_dir.glob("*.md")))
    if knowledge_dir.exists():
        all_files.extend((path, "knowledge") for path in sorted(knowledge_dir.glob("*.md")))
    if not all_files:
        return 0

    for md_file, default_type in all_files:
        parsed = _parse_markdown_file(md_file)
        if not parsed:
            continue
        fm, body = parsed
        doc_type = fm.get("type") or default_type
        doc_id = _build_doc_id(fm, md_file.stem, default_type)
        timestamp = _normalize_timestamp(fm.get("timestamp", ""))

        metadata = {
            "type": str(doc_type),
            "timestamp": timestamp,
        }
        if "session_id" in fm:
            metadata["session_id"] = str(fm.get("session_id"))
        if "knowledge_id" in fm:
            metadata["knowledge_id"] = str(fm.get("knowledge_id"))

        documents.append(body)
        metadatas.append(metadata)
        ids.append(str(doc_id))

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
