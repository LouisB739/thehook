---
phase: 03-storage
plan: 01
subsystem: database
tags: [chromadb, pyyaml, vector-indexing, onnx, embeddings]

# Dependency graph
requires:
  - phase: 02-capture
    provides: write_session_file() with YAML frontmatter format confirmed

provides:
  - COLLECTION_NAME constant ('thehook_sessions')
  - get_chroma_client(project_dir) — PersistentClient pointed at .thehook/chromadb/
  - index_session_file(project_dir, session_path) — idempotent upsert to ChromaDB
  - reindex(project_dir) — drop-and-recreate index from all .thehook/sessions/*.md files
  - tests/test_storage.py — 10 test cases covering all storage behaviors

affects:
  - 03-02 (CLI reindex command — will call reindex())
  - 03-03 (integration with run_capture — will call index_session_file after write_session_file)

# Tech tracking
tech-stack:
  added:
    - chromadb>=1.0 (PersistentClient, EphemeralClient, get_or_create_collection, upsert, add, delete_collection)
  patterns:
    - Lazy import of chromadb inside function bodies (heavy import ~1s; keep module startup fast)
    - EphemeralClient for tests — shared singleton backend; must delete_collection between tests
    - isoformat() on PyYAML-parsed timestamps (PyYAML converts ISO 8601 to datetime objects)
    - ONNX model cache redirected via DOWNLOAD_PATH monkeypatch in conftest (root-owned cache dir workaround)

key-files:
  created:
    - src/thehook/storage.py
    - tests/test_storage.py
  modified:
    - pyproject.toml (added chromadb>=1.0 dependency)
    - tests/conftest.py (added autouse chromadb_onnx_cache fixture)

key-decisions:
  - "chromadb>=1.0 added to pyproject.toml dependencies; installed in project Python (3.11 from pytest shebang)"
  - "chromadb imported lazily inside each function body to keep module-level import overhead near zero"
  - "upsert used in index_session_file (idempotent for re-capture), add used in reindex (no duplicates after drop)"
  - "filename stem used as fallback ChromaDB ID when frontmatter session_id is absent — stem is unique by construction"
  - "PyYAML parses ISO 8601 timestamps to datetime objects; use isoformat() to preserve T-separator in metadata"
  - "EphemeralClient shares a singleton backend across instances; fixture deletes collection pre/post test for isolation"
  - "ONNX model download path redirected to /tmp/chromadb_test_onnx via monkeypatch — root-owned ~/.cache/chroma workaround"

patterns-established:
  - "Lazy chromadb import: import inside function body, not at module top"
  - "Timestamp normalisation: use hasattr(ts, 'isoformat') check before calling isoformat()"
  - "ChromaDB test isolation: delete_collection in fixture setup AND teardown"

requirements-completed: [STOR-02, STOR-03, STOR-04, STOR-05]

# Metrics
duration: 13min
completed: 2026-02-24
---

# Phase 03 Plan 01: Storage Summary

**ChromaDB indexing module with get_chroma_client, index_session_file (upsert), and reindex (drop+recreate) — 10 tests green, lazy imports, PyYAML datetime fix**

## Performance

- **Duration:** 13 min
- **Started:** 2026-02-24T10:10:16Z
- **Completed:** 2026-02-24T10:23:00Z
- **Tasks:** 1 (TDD: RED + GREEN phases)
- **Files modified:** 4

## Accomplishments

- `src/thehook/storage.py` with `COLLECTION_NAME`, `get_chroma_client()`, `index_session_file()`, and `reindex()` — all with lazy chromadb imports
- `tests/test_storage.py` with 10 test cases covering all specified behaviors: path construction, upsert idempotency, malformed skip, empty-body skip, filename fallback, drop-and-recreate, missing dir, empty dir, empty-body reindex skip
- `chromadb>=1.0` added to `pyproject.toml` and installed; full suite (50 tests) green with no regressions
- `conftest.py` updated with autouse fixture to redirect ONNX model downloads past the root-owned cache directory

## Task Commits

TDD flow produced two task commits:

1. **RED phase: failing tests** - `362718c` (test)
2. **GREEN phase: storage implementation** - `f000704` (feat)

## Files Created/Modified

- `src/thehook/storage.py` - ChromaDB indexing module: COLLECTION_NAME, get_chroma_client, index_session_file, reindex
- `tests/test_storage.py` - 10 TDD test cases for storage module
- `pyproject.toml` - added `chromadb>=1.0` to dependencies
- `tests/conftest.py` - added `chromadb_onnx_cache` autouse fixture for ONNX path redirect

## Decisions Made

- **Lazy chromadb imports:** chromadb is imported inside each function body (not at module level) to avoid a ~1-second startup cost whenever any thehook module is imported. This is especially important for the hook runner path.
- **upsert vs add:** `index_session_file` uses `collection.upsert()` (idempotent) so re-capture of the same session does not raise `DuplicateIDError`. `reindex` uses `collection.add()` after a fresh `delete_collection` — no duplicates possible.
- **Filename stem as fallback ID:** `fm.get("session_id") or session_path.stem` — the stem (`YYYY-MM-DD-{8chars}`) is unique by construction from `write_session_file()`, so it is safe as a fallback ChromaDB document ID.
- **PyYAML timestamp parsing:** PyYAML parses ISO 8601 strings (`2026-02-24T10:00:00+00:00`) as Python `datetime` objects. Calling `str()` on them produces `'2026-02-24 10:00:00+00:00'` (space separator). Fixed by checking `hasattr(ts, "isoformat")` and calling `.isoformat()` to preserve the canonical `T`-separated form.
- **ONNX cache redirect:** The system's `~/.cache/chroma/onnx_models` directory was owned by root, causing `PermissionError` on model download. Fixed by adding an autouse pytest fixture that monkeypatches `ONNXMiniLM_L6_V2.DOWNLOAD_PATH` to `/tmp/chromadb_test_onnx` (where the model was pre-downloaded during investigation).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] chromadb not installed; system cache owned by root**
- **Found during:** GREEN phase (running tests)
- **Issue:** `chromadb` was not installed in the project Python environment. After installation, `~/.cache/chroma/onnx_models` was owned by root, causing `PermissionError` when chromadb tried to download the ONNX embedding model during tests.
- **Fix:** Installed `chromadb>=1.0` via pip. Downloaded the ONNX model to `/tmp/chromadb_test_onnx` as a writable location. Added autouse `chromadb_onnx_cache` fixture to `conftest.py` that monkeypatches `DOWNLOAD_PATH` to the writable location.
- **Files modified:** `pyproject.toml`, `tests/conftest.py`
- **Verification:** All 10 storage tests pass; full 50-test suite passes
- **Committed in:** `f000704` (GREEN phase commit)

**2. [Rule 1 - Bug] PyYAML timestamp round-trip breaks ISO 8601 T-separator**
- **Found during:** GREEN phase (first test run after fixing cache issue)
- **Issue:** `test_index_session_file_adds_document` failed because PyYAML parses `timestamp: 2026-02-24T10:00:00+00:00` as a Python `datetime` object, and `str(datetime)` produces `'2026-02-24 10:00:00+00:00'` (space, not T).
- **Fix:** Added `hasattr(raw_ts, "isoformat")` guard in both `index_session_file` and `reindex` to call `.isoformat()` on datetime values, preserving the canonical ISO 8601 form.
- **Files modified:** `src/thehook/storage.py`
- **Verification:** Timestamp assertion passes; both functions handle string and datetime inputs
- **Committed in:** `f000704` (GREEN phase commit)

**3. [Rule 1 - Bug] ChromaDB EphemeralClient shares singleton backend — tests leak state**
- **Found during:** GREEN phase (third test `test_index_session_file_skips_malformed` failed because it saw docs from test 1)
- **Issue:** `chromadb.EphemeralClient()` instances share an in-memory singleton backend. A new `EphemeralClient()` created in a subsequent test sees collections and documents from previous tests.
- **Fix:** Updated the `ephemeral_client` fixture to call `client.delete_collection(COLLECTION_NAME)` in both setup (pre-test) and teardown (post-test) to ensure isolation.
- **Files modified:** `tests/test_storage.py`
- **Verification:** All 10 tests pass in sequence with correct isolation
- **Committed in:** `f000704` (GREEN phase commit)

---

**Total deviations:** 3 auto-fixed (1 blocking dependency issue, 2 bugs)
**Impact on plan:** All three fixes were necessary to make tests pass in the target environment. The underlying storage logic is exactly as planned; only the test infrastructure required adaptation for the actual chromadb 1.5.1 runtime behavior.

## Issues Encountered

- Root-owned chromadb cache: `~/.cache/chroma/onnx_models` owned by root. Cannot fix with sudo in CI-like environment. Resolved by redirecting DOWNLOAD_PATH. See Deviations #1.
- EphemeralClient singleton: Not documented prominently in chromadb docs. Discovered empirically. Resolved via fixture cleanup. See Deviations #3.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `storage.py` is complete and tested — ready for plan 02 (CLI reindex command)
- `reindex()` is ready to be wired to `thehook reindex` CLI command
- `index_session_file()` is ready to be called from `run_capture()` after `write_session_file()`
- No blockers for plan 02 or plan 03

---
*Phase: 03-storage*
*Completed: 2026-02-24*

## Self-Check: PASSED

- FOUND: `src/thehook/storage.py`
- FOUND: `tests/test_storage.py`
- FOUND: `.planning/phases/03-storage/03-01-SUMMARY.md`
- FOUND: commit `362718c` (RED phase — failing tests)
- FOUND: commit `f000704` (GREEN phase — storage implementation)
