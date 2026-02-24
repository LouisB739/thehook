# Phase 4: Retrieval - Research

**Researched:** 2026-02-24
**Domain:** ChromaDB similarity search, Claude Code SessionStart hook output protocol, token budgeting, CLI subcommand wiring
**Confidence:** HIGH

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| RETR-01 | SessionStart hook queries ChromaDB for context relevant to the current project | ChromaDB `collection.query(query_texts=..., n_results=N)` — `cwd` from hook stdin provides project scope; lazy import pattern from Phase 3 applies |
| RETR-02 | Injected context is hard-capped at 2,000 tokens regardless of knowledge base size | `DEFAULT_CONFIG["token_budget"] = 2000` already set; simple chars/4 estimator sufficient; truncate assembled context string before emitting |
| RETR-03 | SessionStart outputs valid `hookSpecificOutput.additionalContext` JSON to stdout — Claude Code accepts it without error | Verified from official docs: `{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "..."}}` on stdout + exit 0 |
| RETR-04 | `thehook recall <query>` returns most relevant stored knowledge for natural language query, printed to terminal | Same `collection.query()` call; Click subcommand mirrors `reindex` pattern; print documents to stdout |
</phase_requirements>

---

## Summary

Phase 4 closes the memory loop by adding two retrieval paths: an automatic SessionStart hook that queries ChromaDB and injects relevant context into every new session, and a `thehook recall` CLI subcommand for on-demand natural language search. Both paths share a single query function built on the `collection.query()` API already established in Phase 3.

The SessionStart hook has a strict output contract: it must write a JSON object with `hookSpecificOutput.hookEventName = "SessionStart"` and an `additionalContext` string to stdout, then exit 0. The official Claude Code documentation confirms this structure verbatim. Known bugs around stdout being dropped were fixed in Claude Code v2.0.76.

Token budgeting is implemented via the existing `DEFAULT_CONFIG["token_budget"] = 2000` (in `config.py`). No external tokenizer is needed — dividing character count by 4 (standard approximation) or using a simple word-count multiplier is sufficient. The query function assembles candidate documents and truncates the assembled string to fit the budget before serialising the JSON output.

**Primary recommendation:** Add `query_sessions()` to `storage.py`, wire it to `run_retrieve()` in a new `retrieve.py`, add `thehook retrieve` and `thehook recall` to `cli.py`. No new dependencies.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| chromadb | >=1.0 (already in pyproject.toml) | Vector similarity search over session documents | Already installed, PersistentClient established |
| click | >=8.1 (already in pyproject.toml) | `recall` subcommand with argument | Already used for all CLI commands |
| json (stdlib) | stdlib | Serialize `hookSpecificOutput` to stdout | Zero dependency |
| sys (stdlib) | stdlib | Read stdin (hook input), write stdout (hook output) | Already pattern-matched in `capture.py` |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pathlib (stdlib) | stdlib | Resolve `cwd` from hook input to `project_dir` | Same pattern as `capture.py` / `storage.py` |
| pyyaml | >=6.0 (already present) | `load_config()` to read `token_budget` | Already used |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| chars/4 token estimate | tiktoken | tiktoken is accurate but adds a dependency; chars/4 is sufficient for a soft cap on context strings that are all ASCII-heavy markdown |
| Lazy `import chromadb` inside function | Top-level import | Phase 3 decision — lazy import avoids ~1s startup cost; keep consistent |

**Installation:** No new packages required.

---

## Architecture Patterns

### Recommended Project Structure

```
src/thehook/
├── retrieve.py          # NEW: run_retrieve(), query_sessions(), format_context()
├── storage.py           # EXISTING: add query_sessions() here (alternative)
├── cli.py               # EXISTING: add `retrieve` and `recall` subcommands
├── capture.py           # EXISTING: unchanged
├── config.py            # EXISTING: DEFAULT_CONFIG["token_budget"] already defined
└── init.py              # EXISTING: hook already registered as "thehook retrieve"
```

**Preferred approach:** Add `query_sessions()` to `storage.py` (it is a pure storage/retrieval concern) and keep `run_retrieve()` + `format_context()` in a new `retrieve.py`. This mirrors the `capture.py` / `storage.py` split from Phase 3: storage module owns data access, retrieve module owns the hook pipeline orchestration.

### Pattern 1: Query ChromaDB and Assemble Context

**What:** Call `collection.query()` with a project-scoped query string, retrieve top-N documents, assemble into a single context string, truncate to token budget.

**When to use:** Both the hook pipeline (`run_retrieve`) and the recall CLI call this path.

**Example:**
```python
# Source: ChromaDB official docs (context7 /chroma-core/chroma)
def query_sessions(project_dir: Path, query_text: str, n_results: int = 5) -> list[str]:
    """Return document strings from ChromaDB matching query_text.

    Returns [] when collection does not exist, is empty, or n_results > count.
    """
    from thehook.storage import get_chroma_client, COLLECTION_NAME
    try:
        client = get_chroma_client(project_dir)
        collection = client.get_collection(COLLECTION_NAME)
        count = collection.count()
        if count == 0:
            return []
        actual_n = min(n_results, count)  # CRITICAL: n_results must not exceed count
        results = collection.query(query_texts=[query_text], n_results=actual_n)
        return results["documents"][0]  # list of str, one per result
    except Exception:
        return []  # collection missing, empty, or query error — degrade silently
```

**Key insight:** ChromaDB raises an exception (log warning + potentially `ValueError`) when `n_results > count`. Always cap with `min(n_results, count)` after checking `count > 0`.

### Pattern 2: SessionStart Hook Output Protocol

**What:** Write JSON to stdout with the exact structure Claude Code expects, then exit 0.

**When to use:** `run_retrieve()` — the function invoked by `thehook retrieve`.

**Example:**
```python
# Source: Official Claude Code hooks reference (code.claude.com/docs/en/hooks)
import json
import sys

def run_retrieve() -> None:
    hook_input = read_hook_input()   # same pattern as capture.py
    cwd = hook_input.get("cwd", ".")
    project_dir = Path(cwd)

    documents = query_sessions(project_dir, query_text="project conventions decisions gotchas")
    context = format_context(documents, token_budget=2000)

    if context:
        output = {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": context,
            }
        }
        print(json.dumps(output))
    # Exit 0 implicitly — no context means no output (Claude Code handles empty stdout gracefully)
```

### Pattern 3: Token Budget Enforcement

**What:** Assemble candidate documents into a string, truncate to fit within the token budget using chars/4 approximation.

**When to use:** `format_context()` called from both `run_retrieve()` and `recall` CLI.

**Example:**
```python
def format_context(documents: list[str], token_budget: int = 2000) -> str:
    """Assemble documents into a context string, capped at token_budget tokens.

    Uses chars/4 as token estimate (standard approximation for ASCII markdown).
    """
    MAX_CHARS = token_budget * 4
    parts = []
    total = 0
    for doc in documents:
        doc_chars = len(doc)
        if total + doc_chars > MAX_CHARS:
            # Trim the document to fit remaining budget
            remaining = MAX_CHARS - total
            if remaining > 0:
                parts.append(doc[:remaining])
            break
        parts.append(doc)
        total += doc_chars
    return "\n\n---\n\n".join(parts)
```

### Pattern 4: `thehook recall` CLI Subcommand

**What:** Click command with a positional `query` argument. Calls `query_sessions()` directly and prints to stdout.

**When to use:** `recall` subcommand — user-initiated, interactive.

**Example:**
```python
# Source: Click docs, mirrors existing reindex pattern in cli.py
@main.command()
@click.argument("query")
@click.option("--path", default=".", help="Project root directory")
def recall(query, path):
    """Search stored knowledge for QUERY and print matching results."""
    from thehook.retrieve import query_sessions, format_context
    project_dir = Path(path).resolve()
    documents = query_sessions(project_dir, query_text=query)
    if not documents:
        click.echo("No relevant knowledge found.")
        return
    click.echo(format_context(documents, token_budget=2000))
```

### Anti-Patterns to Avoid

- **Querying with n_results > collection count:** ChromaDB raises a `ValueError` / `NotEnoughElementsException`. Always `min(n_results, count)` and guard `count == 0`.
- **Top-level chromadb import in retrieve.py:** Phase 3 decision was lazy imports inside function bodies to avoid ~1s startup cost. Keep that pattern.
- **get_collection() on non-existent collection:** `get_collection()` raises `InvalidCollectionException` if the collection has never been created. Wrap in try/except, or use `get_or_create_collection()`. Prefer `get_collection()` + except to avoid creating an empty collection on first query.
- **Printing anything besides the JSON to stdout in run_retrieve():** Claude Code parses the entire stdout as JSON. Any extra print() call will break JSON parsing. Use stderr for debug output.
- **Not flushing stdout:** If the hook process is killed before the buffer flushes, Claude Code receives no JSON. Use `print(..., flush=True)` or `sys.stdout.flush()`.
- **Querying on session resume / clear / compact:** The HOOK_CONFIG in `init.py` already uses `matcher: "startup"`, so the hook only fires on new sessions. Do not change this — querying on every resume would spam context.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Semantic similarity search | Custom cosine-similarity over stored embeddings | `collection.query(query_texts=...)` | ChromaDB embeds via all-MiniLM-L6-V2 and handles HNSW index; rebuilding this is weeks of work |
| Token counting | Tiktoken integration or custom BPE | chars/4 character estimate | The 2,000-token cap is a soft UX limit, not a hard API constraint. ±20% accuracy is fine. Adding tiktoken adds a dependency and import time. |
| Hook stdin parsing | Custom JSON parser | `read_hook_input()` already in `capture.py` — reuse it | DRY; same shape of stdin JSON for all hooks |

**Key insight:** The query function is four lines. The complexity is in knowing the pitfalls (empty collection, n_results capping, stdout purity, flush). Invest research time there, not in reimplementing vector search.

---

## Common Pitfalls

### Pitfall 1: Querying Empty or Nonexistent Collection

**What goes wrong:** `collection.query()` raises an exception when `n_results > count`, or `get_collection()` raises `InvalidCollectionException` if ChromaDB has never indexed anything.

**Why it happens:** ChromaDB requires data before it can build the HNSW index. On a fresh project or after `thehook init` before any session completes, the collection does not exist.

**How to avoid:**
1. Use `get_collection()` inside a try/except — catch all exceptions, return `[]`.
2. Call `collection.count()` before querying; return `[]` if count == 0.
3. Use `min(n_results, count)` to cap the query.

**Warning signs:** `ValueError: Number of requested results N is greater than number of elements in index M` in logs; `chromadb.errors.InvalidCollectionException` on first run.

### Pitfall 2: Non-JSON Stdout Breaking Hook Parsing

**What goes wrong:** Claude Code fails to parse the hook output if stdout contains anything other than the JSON object.

**Why it happens:** Python's default print buffering, logging to stdout, or a stray `print()` for debugging.

**How to avoid:**
- All debug output goes to `sys.stderr`.
- Only one `print(json.dumps(output))` call (or none if context is empty).
- `flush=True` on that print.

**Warning signs:** Claude Code silently ignores the hook (no context injection). Confirmed fix: upgrade to Claude Code >= v2.0.76 (bug in v2.0.65 dropped valid JSON — fixed in v2.0.76).

### Pitfall 3: Hook Fires on Resume/Clear/Compact

**What goes wrong:** If matcher is removed or widened, `thehook retrieve` fires on every `/clear` or `/compact`, injecting stale context into a fresh session reset.

**Why it happens:** Changing `matcher: "startup"` to `""` or omitting it.

**How to avoid:** Keep `matcher: "startup"` in `HOOK_CONFIG` in `init.py`. This is already wired from Phase 1. Do not touch it in Phase 4.

**Warning signs:** Context injection appears after `/clear`.

### Pitfall 4: Query String Is Too Generic

**What goes wrong:** Using a static query string like `"project"` returns low-relevance results because all documents relate to the project.

**Why it happens:** ChromaDB ranks by embedding distance. Generic queries return the nearest documents to a generic centroid, which is unpredictable.

**How to avoid:** Use a richer static query string that captures the most commonly useful retrieval targets: `"project conventions decisions gotchas architecture"`. This is a heuristic — no user input is available at SessionStart.

**Warning signs:** Injected context seems unrelated to the actual session work.

### Pitfall 5: Token Budget Config Not Loaded

**What goes wrong:** `run_retrieve()` uses hardcoded 2000 instead of user-configured `token_budget`.

**Why it happens:** Forgetting to call `load_config()` and pass the budget to `format_context()`.

**How to avoid:** Call `load_config(project_dir)` in `run_retrieve()` and pass `config["token_budget"]` to `format_context()`. This mirrors the design intent of RETR-02 (configurable via `thehook.yaml`).

---

## Code Examples

Verified patterns from official sources:

### SessionStart hookSpecificOutput Output

```python
# Source: code.claude.com/docs/en/hooks — SessionStart decision control
import json

output = {
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": "## Previous Session Knowledge\n\n- Use PersistentClient\n- ...",
    }
}
print(json.dumps(output), flush=True)
# Exit 0 (implicit)
```

### ChromaDB Collection Query

```python
# Source: context7 /chroma-core/chroma — Query API
results = collection.query(
    query_texts=["project conventions decisions gotchas architecture"],
    n_results=5,   # must be <= collection.count()
)
documents = results["documents"][0]  # list[str]
distances = results["distances"][0]  # list[float] — lower is more similar
```

### Empty Collection Guard

```python
# Source: chromadb GitHub issues #301, #657 — known behavior
try:
    collection = client.get_collection(COLLECTION_NAME)
    count = collection.count()
    if count == 0:
        return []
    results = collection.query(query_texts=[query_text], n_results=min(n_results, count))
    return results["documents"][0]
except Exception:
    return []
```

### Hook Stdin Reading (reuse from capture.py)

```python
# Source: thehook/capture.py — read_hook_input() — reuse as-is
from thehook.capture import read_hook_input
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| SessionStart stdout as plain text | `hookSpecificOutput.additionalContext` JSON structure | Claude Code v2.x | Plain text stdout is still supported per docs, but structured JSON is the canonical form and required for `hookEventName` field |
| Top-level chromadb import | Lazy import inside function body | Phase 3 decision | Keeps CLI startup fast (~1s savings) |

**Deprecated/outdated:**
- Claude Code v2.0.65: SessionStart hook stdout was silently dropped (bug). Fixed in v2.0.76. Code should work on current versions without workaround.

---

## Open Questions

1. **Query string for SessionStart**
   - What we know: No user input is available at session start; must use a static query.
   - What's unclear: Whether `"project conventions decisions gotchas architecture"` is the right static string or whether a configurable query would be valuable.
   - Recommendation: Use the static string for v1. Add `recall_query` to `thehook.yaml` config in v2 if recall quality is poor.

2. **n_results for SessionStart**
   - What we know: 2,000 tokens at ~4 chars/token = 8,000 chars. A typical session file body is 400–1,000 chars. So 5–10 results fit.
   - What's unclear: Whether fewer results (3–5) give better precision than more results (8–10).
   - Recommendation: Default to `n_results=5` in `run_retrieve()`. Expose as config in v2 if needed.

3. **`recall` output format**
   - What we know: Terminal output with `click.echo()`. Documents are raw markdown.
   - What's unclear: Whether to add distance scores or session metadata in the output.
   - Recommendation: Print formatted context string (same as `format_context()` output). Keep simple for v1.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x |
| Config file | `pyproject.toml` (tool.pytest.ini_options) |
| Quick run command | `pytest tests/test_retrieve.py -x` |
| Full suite command | `pytest tests/ -x` |
| Estimated runtime | ~20-30 seconds (ChromaDB ONNX model load) |

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| RETR-01 | `run_retrieve()` calls `query_sessions()` with `cwd` from hook input | unit | `pytest tests/test_retrieve.py::test_run_retrieve_calls_query_sessions -x` | Wave 0 gap |
| RETR-01 | `query_sessions()` returns documents from ChromaDB | integration | `pytest tests/test_retrieve.py::test_query_sessions_returns_documents -x` | Wave 0 gap |
| RETR-01 | `query_sessions()` returns `[]` on empty collection | integration | `pytest tests/test_retrieve.py::test_query_sessions_empty_collection -x` | Wave 0 gap |
| RETR-01 | `query_sessions()` returns `[]` when collection does not exist | unit | `pytest tests/test_retrieve.py::test_query_sessions_missing_collection -x` | Wave 0 gap |
| RETR-02 | `format_context()` truncates assembled string to token_budget | unit | `pytest tests/test_retrieve.py::test_format_context_truncates -x` | Wave 0 gap |
| RETR-02 | `run_retrieve()` reads `token_budget` from config | unit | `pytest tests/test_retrieve.py::test_run_retrieve_uses_config_token_budget -x` | Wave 0 gap |
| RETR-03 | `run_retrieve()` prints valid JSON with `hookSpecificOutput.additionalContext` | unit | `pytest tests/test_retrieve.py::test_run_retrieve_outputs_valid_json -x` | Wave 0 gap |
| RETR-03 | `run_retrieve()` prints nothing when no context found | unit | `pytest tests/test_retrieve.py::test_run_retrieve_no_output_on_empty -x` | Wave 0 gap |
| RETR-03 | `thehook retrieve` CLI command exits 0 | integration | `pytest tests/test_retrieve.py::test_cli_retrieve_command -x` | Wave 0 gap |
| RETR-04 | `thehook recall <query>` prints matching documents | integration | `pytest tests/test_retrieve.py::test_cli_recall_prints_results -x` | Wave 0 gap |
| RETR-04 | `thehook recall <query>` prints "No relevant knowledge found." on empty collection | integration | `pytest tests/test_retrieve.py::test_cli_recall_empty_collection -x` | Wave 0 gap |

### Nyquist Sampling Rate

- **Minimum sample interval:** After every committed task → run: `pytest tests/test_retrieve.py -x`
- **Full suite trigger:** Before merging final task of any plan wave → `pytest tests/ -x`
- **Phase-complete gate:** Full suite green before `/gsd:verify-work` runs
- **Estimated feedback latency per task:** ~20-30 seconds

### Wave 0 Gaps (must be created before implementation)

- [ ] `tests/test_retrieve.py` — covers RETR-01, RETR-02, RETR-03, RETR-04 (all tests listed above)
- [ ] `src/thehook/retrieve.py` — module stub with `run_retrieve()`, `query_sessions()`, `format_context()` (test-first: create the test file first, then the module)

*(Existing `tests/conftest.py` with `ephemeral_client` fixture and `chromadb_onnx_cache` autouse fixture is already adequate — reuse it.)*

---

## Sources

### Primary (HIGH confidence)

- `code.claude.com/docs/en/hooks` — Full SessionStart hook reference, `hookSpecificOutput.additionalContext` format, exit code behavior, stdin JSON schema. Fetched 2026-02-24.
- Context7 `/chroma-core/chroma` — `collection.query()` API, `n_results`, `query_texts`, response shape `results["documents"][0]`. Fetched 2026-02-24.
- `/Users/louisbarbier/thehook/src/thehook/storage.py` — `get_chroma_client()`, `COLLECTION_NAME`, lazy import pattern, `get_or_create_collection()` usage.
- `/Users/louisbarbier/thehook/src/thehook/init.py` — `HOOK_CONFIG` showing `thehook retrieve` already registered with `matcher: "startup"`, timeout 30.
- `/Users/louisbarbier/thehook/src/thehook/config.py` — `DEFAULT_CONFIG["token_budget"] = 2000`.
- `/Users/louisbarbier/thehook/src/thehook/cli.py` — Existing `reindex` CLI command pattern to mirror for `retrieve` and `recall`.
- `/Users/louisbarbier/thehook/tests/conftest.py` — `ephemeral_client` fixture and `chromadb_onnx_cache` autouse fixture reusable for Phase 4 tests.

### Secondary (MEDIUM confidence)

- GitHub issue #13650 (anthropics/claude-code) — SessionStart hook stdout silently dropped in v2.0.65, fixed in v2.0.76. WebFetch verified. 2026-02-24.
- GitHub issue #301 (chroma-core/chroma) — `n_results > count` behavior documented. WebSearch + context7 cross-verified.
- WebSearch: chars/4 as token estimate — standard industry approximation; consistent across multiple sources.

### Tertiary (LOW confidence)

- WebSearch: Static query string heuristic (`"project conventions decisions gotchas"`) — based on reasoning about ChromaDB embedding space, not empirical testing against real session data. Needs validation.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already installed; APIs verified via Context7 and official docs
- Architecture: HIGH — patterns derived directly from Phase 3 codebase and official Claude Code hook documentation
- Pitfalls: HIGH — empty collection behavior confirmed via GitHub issues; stdout purity confirmed via bug report and fix; token estimate is standard industry convention
- Test map: HIGH — test names and commands follow established project patterns; Wave 0 gap clearly identified as `tests/test_retrieve.py`

**Research date:** 2026-02-24
**Valid until:** 2026-03-24 (stable libraries, 30-day window)
