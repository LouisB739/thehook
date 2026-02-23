# Phase 3: Storage - Research

**Researched:** 2026-02-23
**Domain:** ChromaDB vector indexing, markdown frontmatter parsing, CLI storage commands
**Confidence:** HIGH

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| STOR-01 | Session knowledge is written as structured markdown files in `.thehook/sessions/` | Already implemented by `write_session_file()` in `capture.py`; Phase 3 must call that function and ensure ChromaDB indexing follows every successful write |
| STOR-02 | Markdown files include frontmatter with session_id, timestamp, and source transcript path | Already implemented: `write_session_file()` writes `---\nsession_id: …\ntimestamp: …\ntranscript_path: …\n---`; reindex must parse this with PyYAML (already a dep) |
| STOR-03 | ChromaDB indexes all markdown knowledge with metadata (session_id, type, timestamp) | `chromadb.PersistentClient` + `collection.add(documents=…, metadatas=…, ids=…)` — verified in Context7 and official docs |
| STOR-04 | ChromaDB uses `PersistentClient` with local storage in `.thehook/chromadb/` | `chromadb.PersistentClient(path=str(project_dir / ".thehook" / "chromadb"))` — confirmed API; chromadb 1.5.1 available for Python 3.13 |
| STOR-05 | User can run `thehook reindex` to drop and recreate ChromaDB from all markdown files in `.thehook/sessions/` | `client.delete_collection(name)` then `get_or_create_collection` then iterate `.thehook/sessions/*.md`, parse frontmatter, `collection.add()` — all APIs confirmed |

</phase_requirements>

---

## Summary

Phase 3 has two responsibilities: (1) index every newly-written session file into ChromaDB immediately after it is written (called inside the capture pipeline), and (2) provide a `thehook reindex` CLI command that rebuilds the full ChromaDB index from scratch by scanning all existing markdown files in `.thehook/sessions/`. The markdown writing itself (STOR-01, STOR-02) is already implemented by `write_session_file()` in `capture.py` — Phase 3 adds the ChromaDB step after that write.

ChromaDB's `PersistentClient` stores the entire database as local files in a specified directory — no server process, no network calls. The project already specifies `.thehook/chromadb/` as the storage path (created by `thehook init`). Documents are indexed with metadata; the embedding is computed automatically using the default `all-MiniLM-L6-v2` sentence-transformer model (bundled with chromadb). Reindex is implemented by `client.delete_collection()` followed by `get_or_create_collection()` followed by `collection.add()` for each markdown file — the index is always fully reconstructible from the markdown source of truth.

Frontmatter parsing for reindex does not require a new library: the existing `pyyaml` dependency (already in `pyproject.toml`) can split on `---` delimiters and parse the frontmatter block with `yaml.safe_load()`. The pattern is two lines: `_, fm, body = content.split("---", 2)` followed by `yaml.safe_load(fm)`.

**Primary recommendation:** Add `chromadb>=1.0` to `pyproject.toml` dependencies. Create `src/thehook/storage.py` with `index_session_file()` and `reindex()` functions. Call `index_session_file()` from `run_capture()` after a successful `write_session_file()` call. Add `thehook reindex` as a Click subcommand in `cli.py`.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `chromadb` | >=1.0 (latest: 1.5.1) | Vector database — PersistentClient, collections, add, query, delete_collection | Official Chroma Python client; only client with PersistentClient for local-file storage; no server required |
| `pyyaml` | >=6.0 (already a dep) | Parse YAML frontmatter from session markdown files | Already in pyproject.toml; `yaml.safe_load()` is all that's needed for frontmatter parsing |
| `pathlib` | stdlib | Glob `.thehook/sessions/*.md`, resolve chromadb path | Already the project pattern; Path.glob() is the clean approach for directory scanning |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `click` | >=8.1 (already a dep) | Register `thehook reindex` subcommand | Already the CLI framework; one `@main.command()` decorator needed |
| Python `datetime` | stdlib | Parse/validate timestamp from frontmatter for metadata | Already imported in `capture.py`; needed to normalise timestamps |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `chromadb` default embedding (all-MiniLM-L6-v2) | OpenAI / Cohere embeddings | Default model runs fully offline; no API key; no cost; sufficient quality for project-scoped recall. Requirements explicitly call this out of scope. |
| `pyyaml` manual split | `python-frontmatter` library | `python-frontmatter` is cleaner but adds a dep; PyYAML manual split is 3 lines and sufficient given fixed frontmatter format |
| `chromadb.PersistentClient` | `chromadb.HttpClient` (server mode) | HttpClient requires a running server process; PersistentClient is embedded with no server — matches STOR-04 requirement exactly |

**Installation:**
```bash
pip install "chromadb>=1.0"
```

In `pyproject.toml`:
```toml
dependencies = [
    "click>=8.1",
    "pyyaml>=6.0",
    "chromadb>=1.0",
]
```

---

## Architecture Patterns

### Recommended Project Structure

```
src/thehook/
├── cli.py          # add: @main.command() def reindex(...)
├── storage.py      # NEW: index_session_file(), reindex(), get_chroma_client(), COLLECTION_NAME
├── capture.py      # existing — call index_session_file() after write_session_file()
├── init.py         # existing
└── config.py       # existing

tests/
├── test_storage.py # NEW: covers STOR-01 through STOR-05
└── test_capture.py # existing — may need update if run_capture now calls storage
```

### Pattern 1: PersistentClient Initialization

**What:** Create a ChromaDB client that stores data on disk in `.thehook/chromadb/`
**When to use:** Called at the start of both `index_session_file()` and `reindex()`

```python
# Source: Context7 /chroma-core/chroma — PersistentClient docs
import chromadb
from pathlib import Path

COLLECTION_NAME = "thehook_sessions"

def get_chroma_client(project_dir: Path) -> chromadb.PersistentClient:
    chroma_path = project_dir / ".thehook" / "chromadb"
    return chromadb.PersistentClient(path=str(chroma_path))
```

### Pattern 2: Index a Single Session File

**What:** Add one session markdown document to ChromaDB with its metadata
**When to use:** Called by `run_capture()` immediately after `write_session_file()` succeeds

```python
# Source: Context7 /chroma-core/chroma — collection.add() with documents + metadatas + ids
def index_session_file(project_dir: Path, session_path: Path) -> None:
    """Add a session markdown file to the ChromaDB index.

    Args:
        project_dir: Project root directory (contains .thehook/).
        session_path: Path to the session .md file to index.
    """
    content = session_path.read_text()
    # Parse YAML frontmatter: content starts with "---\n...\n---\n\nbody"
    parts = content.split("---", 2)
    if len(parts) < 3:
        return  # malformed file, skip silently

    import yaml
    fm = yaml.safe_load(parts[1]) or {}
    body = parts[2].strip()

    session_id = fm.get("session_id", str(session_path.stem))
    timestamp = str(fm.get("timestamp", ""))

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
```

**Note on `upsert` vs `add`:** Use `upsert` (not `add`) when indexing single files to make the operation idempotent — if `run_capture()` is called twice for the same session, the second call overwrites rather than raising a duplicate-ID error.

### Pattern 3: Full Reindex

**What:** Drop and recreate the ChromaDB collection from all markdown files in `.thehook/sessions/`
**When to use:** `thehook reindex` command — the index is always fully reconstructible

```python
# Source: Context7 /chroma-core/chroma — delete_collection, get_or_create_collection, add
def reindex(project_dir: Path) -> int:
    """Drop and recreate the ChromaDB index from all session markdown files.

    Returns:
        int: Number of files indexed.
    """
    client = get_chroma_client(project_dir)

    # Drop existing collection if it exists
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass  # collection didn't exist; that's fine

    collection = client.get_or_create_collection(COLLECTION_NAME)

    sessions_dir = project_dir / ".thehook" / "sessions"
    md_files = sorted(sessions_dir.glob("*.md"))

    documents = []
    metadatas = []
    ids = []

    import yaml
    for md_file in md_files:
        content = md_file.read_text()
        parts = content.split("---", 2)
        if len(parts) < 3:
            continue  # malformed, skip

        fm = yaml.safe_load(parts[1]) or {}
        body = parts[2].strip()
        if not body:
            continue  # empty body, skip

        session_id = fm.get("session_id", str(md_file.stem))
        timestamp = str(fm.get("timestamp", ""))

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
```

**Note:** Batch `collection.add()` all at once is more efficient than calling `add()` per file. Use `add` (not `upsert`) after a fresh delete — no duplicates possible after the drop.

### Pattern 4: CLI Reindex Subcommand

**What:** Register `thehook reindex` as a Click command
**When to use:** STOR-05 — user-facing command

```python
# Source: Phase 1/2 cli.py pattern (already established)
@main.command()
@click.option("--path", default=".", help="Project root directory")
def reindex(path):
    """Rebuild the ChromaDB index from all session markdown files."""
    from thehook.storage import reindex as do_reindex
    project_dir = Path(path).resolve()
    count = do_reindex(project_dir)
    click.echo(f"Reindexed {count} session files.")
```

### Pattern 5: Integration with run_capture

**What:** Call `index_session_file()` after every successful `write_session_file()` call in `run_capture()`
**When to use:** STOR-03 — every captured session is immediately indexed

```python
# In capture.py — run_capture() additions (after existing write calls)
from thehook.storage import index_session_file

# After: session_path = write_session_file(sessions_dir, ...)
try:
    index_session_file(project_dir, session_path)
except Exception:
    pass  # ChromaDB failure must never break the capture pipeline
```

**Critical:** ChromaDB errors must be swallowed in `run_capture()` — the capture pipeline is a SessionEnd hook and must never crash. The markdown file is the source of truth; ChromaDB failure can be recovered with `thehook reindex`.

### Anti-Patterns to Avoid

- **Calling `collection.add()` without checking for duplicate IDs:** `add()` raises a `DuplicateIDError` (chromadb >=0.4) or silently fails if the same `id` is added twice. Use `upsert()` for single-file indexing from `run_capture()`.
- **Using `session_path.stem` as the ChromaDB document ID:** The stem is `YYYY-MM-DD-{8-char-session-id}`. Two sessions on the same day with the same first 8 chars of session_id (extremely unlikely but possible) would collide. Use the full `session_id` from frontmatter as the ChromaDB ID — it is unique by design.
- **Letting ChromaDB errors propagate out of `run_capture()`:** The SessionEnd hook must exit cleanly. Any exception from `index_session_file()` must be caught and swallowed. Recovery via `thehook reindex` is the designed fallback.
- **Passing `Path` objects to ChromaDB:** The `path` parameter for `PersistentClient` must be a `str`, not a `Path`. Use `str(chroma_path)`.
- **Forgetting to handle empty sessions dir in reindex:** If `.thehook/sessions/` doesn't exist or has no `.md` files, `reindex()` should return 0 gracefully, not raise a `FileNotFoundError`.
- **Importing chromadb at module level in `capture.py`:** Chromadb is a heavy import (~1s). Import it lazily inside the function to keep the capture command's startup fast. Better: keep all ChromaDB logic in `storage.py` and only import `index_session_file` inside the function.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Vector embeddings for semantic search | Custom embedding pipeline | ChromaDB default (all-MiniLM-L6-v2 via sentence-transformers) | Downloaded and cached automatically on first use; no model management code needed |
| Persistent local vector store | SQLite + FAISS manually | `chromadb.PersistentClient` | ChromaDB handles HNSW index, persistence, metadata filtering, and serialization; building this manually is 100+ LOC of complex index management |
| YAML frontmatter parsing | Custom string split logic | `yaml.safe_load()` after `content.split("---", 2)` | PyYAML handles all YAML edge cases; the split is 1 line; no new dep needed |
| Deduplication during reindex | Custom ID tracking / hash map | `delete_collection()` then fresh `add()` | Drop-and-recreate is simpler than diff-and-patch; markdown is the source of truth; correct by construction |

**Key insight:** ChromaDB does the hardest work (embedding, HNSW index, persistence). The Phase 3 code is thin orchestration: parse frontmatter → call add/upsert → CLI wrapper.

---

## Common Pitfalls

### Pitfall 1: ChromaDB First-Run Model Download Blocks the Hook

**What goes wrong:** On first use, ChromaDB downloads the `all-MiniLM-L6-v2` sentence-transformer model (~90MB). This happens synchronously inside `collection.add()`. If `run_capture()` calls `index_session_file()`, the very first hook invocation can stall for 10-60 seconds waiting for model download.
**Why it happens:** ChromaDB's default embedding function uses `sentence-transformers` which auto-downloads models to `~/.cache/huggingface/hub/`. The download is transparent and happens on first use.
**How to avoid:** Two options: (a) accept the one-time delay — the model is cached after first download and subsequent calls are fast (~0.1s); (b) run `thehook reindex` once after install to trigger the download outside the hook context. Document this behavior clearly. The `thehook init` command is a natural place to pre-warm the model.
**Warning signs:** First SessionEnd hook call hangs for 30-60 seconds. Subsequent calls are fast. Check `~/.cache/huggingface/hub/` to see if model files exist.

### Pitfall 2: ChromaDB DuplicateIDError on Re-capture

**What goes wrong:** `run_capture()` is called twice for the same session (e.g., hook fires twice, or user manually re-runs capture). `collection.add()` with the same `session_id` raises a `DuplicateIDError` in chromadb >=0.4.
**Why it happens:** `add()` does not accept duplicate IDs. The duplicate check uses the exact `id` string passed.
**How to avoid:** Use `collection.upsert()` instead of `collection.add()` in `index_session_file()`. `upsert` is idempotent: it inserts on new IDs and updates on existing IDs.
**Warning signs:** `chromadb.errors.DuplicateIDError` in the hook output. Only manifests on duplicate runs.

### Pitfall 3: Empty Document Body Causes ChromaDB Embedding Failure

**What goes wrong:** A stub session file has an empty body (only frontmatter). Calling `collection.add(documents=[""])` with an empty string may cause the embedding model to fail or return a zero vector.
**Why it happens:** Stub files use `"None this session."` for each section body, so they won't be empty — but if a file is malformed or the body gets stripped to empty, ChromaDB may reject it or silently store a bad embedding.
**How to avoid:** In `reindex()` and `index_session_file()`, skip documents where `body.strip()` is falsy. Log or silently skip; do not raise.
**Warning signs:** `ValueError` or `InvalidArgumentError` from chromadb during embedding.

### Pitfall 4: Session ID Collision in ChromaDB IDs

**What goes wrong:** Two different sessions produce the same frontmatter `session_id` value, causing the second `add()` in `reindex()` to fail (or the `upsert()` to silently overwrite the first).
**Why it happens:** `session_id` comes from the Claude Code hook input. If the hook input is missing or malformed, `session_id` defaults to `"unknown"` (set in `run_capture()`). Multiple stub files could all have `session_id: unknown`.
**How to avoid:** In `reindex()`, use the markdown filename as a fallback ID: `ids.append(fm.get("session_id") or md_file.stem)`. The filename `YYYY-MM-DD-{8chars}.md` is guaranteed unique by construction (datetime + session_id prefix).
**Warning signs:** ChromaDB collection has fewer documents than the number of markdown files in `.thehook/sessions/`. `session_id: unknown` in multiple files.

### Pitfall 5: ChromaDB Path Must Be a String

**What goes wrong:** `chromadb.PersistentClient(path=Path(...))` raises a `TypeError` or `ValidationError` because chromadb validates the `path` parameter as a string.
**Why it happens:** The project uses `pathlib.Path` consistently (good Python practice). ChromaDB's `PersistentClient` signature accepts `Union[str, Path]` in newer versions but may not in all 1.x releases.
**How to avoid:** Always pass `str(chroma_path)` to `PersistentClient`. Costs nothing, eliminates ambiguity.
**Warning signs:** `pydantic.ValidationError: 1 validation error for PersistentClient / path` — type is str but got Path.

### Pitfall 6: Reindex Called When Sessions Dir Doesn't Exist

**What goes wrong:** `thehook reindex` is called before any sessions have been captured. `sessions_dir.glob("*.md")` raises `FileNotFoundError` if the directory doesn't exist.
**Why it happens:** `thehook init` creates `.thehook/sessions/` but a fresh project with no captured sessions may have had the directory deleted or never created.
**How to avoid:** In `reindex()`, check `if not sessions_dir.exists(): return 0` before calling `glob()`.
**Warning signs:** `FileNotFoundError: .thehook/sessions` when running `thehook reindex` on a fresh project.

---

## Code Examples

Verified patterns from official sources:

### PersistentClient Initialization and Collection Creation

```python
# Source: Context7 /chroma-core/chroma — local_persistence.ipynb example
import chromadb

client = chromadb.PersistentClient(path="/path/to/.thehook/chromadb")
collection = client.get_or_create_collection(name="thehook_sessions")
```

### Adding Documents with Metadata

```python
# Source: Context7 /chroma-core/chroma — collection.add() with metadatas
collection.add(
    documents=["session markdown body text here"],
    metadatas=[{
        "session_id": "abc12345-...",
        "type": "session",
        "timestamp": "2026-02-23T10:00:00+00:00",
    }],
    ids=["abc12345-..."],  # unique string ID per document
)
```

### Upsert (Idempotent Add)

```python
# Source: Context7 /chroma-core/chroma — upsert docs
collection.upsert(
    documents=["session body"],
    metadatas=[{"session_id": "abc", "type": "session", "timestamp": "..."}],
    ids=["abc"],
)
```

### Delete and Recreate Collection

```python
# Source: Context7 /chroma-core/chroma — delete_collection docs + cookbook.chromadb.dev/core/collections
try:
    client.delete_collection("thehook_sessions")
except Exception:
    pass  # didn't exist yet
collection = client.get_or_create_collection("thehook_sessions")
```

### Parse YAML Frontmatter with PyYAML

```python
# Source: PyYAML docs — yaml.safe_load() on split content
import yaml

content = session_path.read_text()
parts = content.split("---", 2)
# parts[0] = "" (before first ---)
# parts[1] = "\nsession_id: abc\ntimestamp: ...\ntranscript_path: ...\n"
# parts[2] = "\n\n## SUMMARY\n..."
fm = yaml.safe_load(parts[1]) or {}
body = parts[2].strip()
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `chromadb.Client()` (in-memory) | `chromadb.PersistentClient(path=...)` | chromadb ~0.4+ | In-memory client is for tests only; PersistentClient is the standard for local persistence |
| Manual SQLite + FAISS | `chromadb.PersistentClient` | 2023+ | ChromaDB bundles HNSW + SQLite + metadata filtering in one package |
| chromadb server mode (`HttpClient`) | `PersistentClient` for embedded use | Always | Server mode requires a running service; PersistentClient is embedded — no server, no config |
| `collection.add()` for all writes | `collection.upsert()` for idempotent writes | chromadb 0.4+ | `upsert` prevents DuplicateIDError on re-runs; now the recommended default for single-document indexing |

**Deprecated/outdated:**
- `chromadb.Client()` with no path argument: Creates an ephemeral in-memory DB. Data lost on process exit. Never use for production storage.
- `chromadb.EphemeralClient()`: Explicit in-memory alias. Good for tests only.

---

## Open Questions

1. **ChromaDB model download on first run inside a hook**
   - What we know: `all-MiniLM-L6-v2` is ~90MB and downloads to `~/.cache/huggingface/hub/` on first `collection.add()`. The download is blocking.
   - What's unclear: Whether the model is already cached on the developer's machine (likely if they have any LLM tooling installed). Whether the SessionEnd hook's 120-second timeout is sufficient to cover a first-run download.
   - Recommendation: Add a note to the `thehook init` output suggesting `thehook reindex` as a warmup step. In the plan, the `init` command could optionally warm the embedding model. Low urgency — the 120s hook timeout is generous.

2. **Whether to expose chromadb errors to the user in `thehook reindex`**
   - What we know: Reindex runs interactively (not in a hook), so errors CAN surface to the user.
   - What's unclear: Whether to let chromadb exceptions propagate (showing raw tracebacks) or catch and display friendly messages.
   - Recommendation: Let `click.echo` show a friendly count on success. Let exceptions propagate naturally for reindex (user is watching the terminal). Wrap only the `delete_collection` in try/except (it throws if collection doesn't exist).

3. **Session ID uniqueness assumption for ChromaDB IDs**
   - What we know: The `session_id` from Claude Code hook input is a UUID-like string. The fallback in `run_capture()` is `"unknown"` if the field is missing.
   - What's unclear: How frequently `session_id` is missing in practice.
   - Recommendation: Use filename stem (`YYYY-MM-DD-{8chars}`) as the ChromaDB ID, not `session_id`. The filename is guaranteed unique by the `write_session_file()` implementation. This also makes reindex consistent regardless of frontmatter quality. Document this as a plan decision.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.0+ |
| Config file | `pyproject.toml` — `[tool.pytest.ini_options]` (exists from Phase 1) |
| Quick run command | `pytest tests/ -x -q` |
| Full suite command | `pytest tests/ -v` |
| Estimated runtime | ~3-10 seconds (ChromaDB operations use EphemeralClient in tests to avoid disk I/O and model downloads) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| STOR-01 | `run_capture()` calls storage indexing after writing session file | unit (mocked) | `pytest tests/test_storage.py -x -k "capture_calls_index"` | Wave 0 gap |
| STOR-02 | `index_session_file()` correctly parses frontmatter (session_id, timestamp, transcript_path) | unit | `pytest tests/test_storage.py -x -k "parse_frontmatter"` | Wave 0 gap |
| STOR-03 | `index_session_file()` adds document to ChromaDB collection with correct metadata fields | unit | `pytest tests/test_storage.py -x -k "index_adds_metadata"` | Wave 0 gap |
| STOR-04 | `get_chroma_client()` uses PersistentClient with path pointing to `.thehook/chromadb/` | unit | `pytest tests/test_storage.py -x -k "persistent_client_path"` | Wave 0 gap |
| STOR-05 | `reindex()` drops collection then re-adds all markdown files from `.thehook/sessions/` | unit | `pytest tests/test_storage.py -x -k "reindex_drops_and_recreates"` | Wave 0 gap |
| STOR-05 | `thehook reindex` CLI command exists and prints indexed count | integration | `pytest tests/test_storage.py -x -k "cli_reindex"` | Wave 0 gap |
| STOR-05 | `reindex()` returns 0 gracefully when sessions dir is missing | unit | `pytest tests/test_storage.py -x -k "reindex_empty_dir"` | Wave 0 gap |

**Testing strategy for ChromaDB:** Use `chromadb.EphemeralClient()` (in-memory, no disk, no model download) in tests. The `get_chroma_client()` function should accept an optional `client` override parameter (or tests should monkeypatch it) to inject EphemeralClient. Alternatively, use `tmp_path` + real PersistentClient if the test machine has the model cached.

The safest pattern: mock `get_chroma_client` in unit tests to return a real `EphemeralClient` from chromadb. This exercises the real chromadb API without disk I/O or model downloads.

```python
# In tests/test_storage.py — EphemeralClient fixture
import chromadb
import pytest

@pytest.fixture
def ephemeral_client():
    return chromadb.EphemeralClient()
```

### Nyquist Sampling Rate

- **Minimum sample interval:** After every committed task → run: `pytest tests/ -x -q`
- **Full suite trigger:** Before merging final task of any plan wave
- **Phase-complete gate:** Full suite green before `/gsd:verify-work` runs
- **Estimated feedback latency per task:** ~5-10 seconds

### Wave 0 Gaps (must be created before implementation)

- [ ] `tests/test_storage.py` — covers STOR-01 through STOR-05 (all gaps above)
- [ ] `src/thehook/storage.py` — skeleton with function signatures and docstrings, no implementation
- [ ] Install chromadb in project venv: `pip install "chromadb>=1.0"` and add to `pyproject.toml`

*(Existing `tests/conftest.py` with `tmp_project` fixture and `pyproject.toml` pytest config require no changes.)*

---

## Sources

### Primary (HIGH confidence)

- Context7 `/chroma-core/chroma` — `PersistentClient`, `get_or_create_collection`, `collection.add()`, `collection.upsert()`, `client.delete_collection()`, metadata field types; verified 2026-02-23
- `https://docs.trychroma.com/docs/collections/manage-collections` — Collection create/get/delete Python API; metadata key/value constraints (string keys, string/int/float/bool values); verified 2026-02-23
- `https://cookbook.chromadb.dev/core/clients/` — `PersistentClient` constructor parameters and path semantics; verified 2026-02-23
- `https://cookbook.chromadb.dev/core/collections/` — Full collection API including add, upsert, query, delete; verified 2026-02-23
- `https://pypi.org/project/chromadb/` — Latest version 1.5.1 (released 2026-02-19); Python >=3.9 required (project uses 3.13 — compatible); verified 2026-02-23
- PyYAML docs — `yaml.safe_load()` on manually split frontmatter; existing dep in pyproject.toml; stdlib pattern confirmed
- Existing `src/thehook/capture.py` — `write_session_file()` implementation confirms exact frontmatter format: `---\nsession_id: …\ntimestamp: …\ntranscript_path: …\n---\n\n{body}`

### Secondary (MEDIUM confidence)

- `https://pypi.org/project/chromadb/` install dry-run on project venv — confirmed chromadb 1.5.1 installs cleanly against Python 3.13.7 and ARM64 macOS; checked 2026-02-23
- ChromaDB sentence-transformer default embedding model (`all-MiniLM-L6-v2`) — confirmed from Context7 embedding functions docs and official Chroma docs; model downloads to `~/.cache/huggingface/hub/` on first use

### Tertiary (LOW confidence)

- First-run model download timing (~30-60 seconds) — based on general knowledge of model download speeds; not officially benchmarked

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — ChromaDB API verified via Context7 and official docs; version and Python compatibility verified by dry-run install against project venv
- Architecture: HIGH — All storage patterns (`PersistentClient`, `add`, `upsert`, `delete_collection`) verified from official sources; frontmatter parsing pattern is well-established PyYAML idiom
- Pitfalls: HIGH for DuplicateIDError, empty body, and path-type issues (verified against chromadb API); MEDIUM for first-run model download timing (known behavior, timing not benchmarked)

**Research date:** 2026-02-23
**Valid until:** 2026-03-23 (ChromaDB API is stable; embedding model default is stable; reassess if chromadb releases breaking changes)
