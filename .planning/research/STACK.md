# Stack Research

**Domain:** Python CLI tool with local RAG (ChromaDB), markdown storage, YAML config, and Claude Code / Cursor hook integration
**Researched:** 2026-02-23
**Confidence:** HIGH (all key choices verified against PyPI, official docs, and Claude Code hooks reference)

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.11+ | Runtime | ChromaDB 1.5.x requires >=3.9; `asyncio.timeout()` (used for subprocess calls) is cleanest on 3.11+; PROJECT.md mandates 3.11+ |
| Typer | 0.24.1 | CLI framework | Built on Click, uses type hints for zero-boilerplate subcommands; current as of 2026-02-21; the industry standard for new Python CLIs; now requires Python >=3.10 which aligns with our constraint |
| ChromaDB | 1.5.1 | Local vector store | Project-specified; default embedding (all-MiniLM-L6-v2, ~300MB) is sufficient; persistent client stores to `.thehook/chromadb/`; `chroma.PersistentClient(path=...)` is the local-only API |
| pydantic-settings | 2.13.1 | YAML config loading + validation | Type-safe config with schema validation; supports YAML source via `pydantic-settings-yaml`; requires Python >=3.10; avoids silent misconfiguration bugs |
| PyYAML | 6.0.3 | YAML parsing | Dependency of pydantic-settings-yaml; the standard Python YAML library; no compelling alternative exists |
| Rich | 14.3.3 | Terminal output | Colors, tables, progress bars, spinners for CLI feedback; the de facto standard for Python CLI UX; required for `thehook status` output |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| mistune | 3.2.0 | Markdown parsing | Extracting structure from `.md` session files; fastest Python markdown parser (benchmarks show 3-4x faster than python-markdown); not CommonMark-compliant but that is fine for internal structured markdown we control; updated 2025-12-23 |
| pydantic-settings-yaml | latest | YAML settings source for pydantic-settings | Required to load `.thehook/config.yaml` into a pydantic-settings model; thin adapter, no downside |
| pytest | 9.0.2 | Testing | The Python testing standard; requires >=3.10; use for unit tests on extraction logic, CLI commands, and ChromaDB integration |
| pytest-asyncio | latest | Async test support | Required if any async code is tested (subprocess calls use asyncio); use with pytest |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| uv | Package manager + virtualenv + build + publish | Replaces pip, pipx, poetry, pyenv, twine in one Rust-based tool; 10-100x faster than pip; `uv tool install thehook` is the recommended install path for end users; use `uv init`, `uv add`, `uv build`, `uv publish` throughout development |
| pyproject.toml | Project metadata and dependency declaration | The only supported format for modern Python packaging; replaces setup.py and requirements.txt; use version ranges (`>=x.y,<x+1`) not exact pins for library dependencies |
| ruff | Linter + formatter | Replaces flake8 + black + isort; Rust-based, fast; configured in pyproject.toml |

---

## Installation

```bash
# End-user install (recommended — isolated environment, on PATH)
uv tool install thehook

# Dev environment setup
uv sync

# Core runtime dependencies (pyproject.toml)
uv add typer rich chromadb pydantic-settings pyyaml mistune pydantic-settings-yaml

# Dev dependencies
uv add --dev pytest pytest-asyncio ruff
```

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| Typer 0.24.1 | Click 8.x directly | If you need very custom argument parsing behavior Typer does not expose; Typer is Click under the hood so you can drop to Click APIs when needed |
| pydantic-settings + PyYAML | Dynaconf | If you need layered multi-environment config (dev/staging/prod) with environment variable overrides in a web service context; overkill for a single-user CLI tool with one config file |
| mistune | markdown-it-py | If CommonMark compliance matters (nested inline parsing edge cases); acceptable swap if mistune causes parsing issues; slightly slower |
| mistune | python-markdown | If you need extensions ecosystem (tables, footnotes, etc.); python-markdown is ~3x slower than mistune; acceptable if performance is not a concern |
| ChromaDB PersistentClient | Qdrant (local) / LanceDB | If you need sub-millisecond query latency at scale (thousands of sessions); ChromaDB is perfectly adequate for the hundreds-of-documents scale of per-project memory; Qdrant and LanceDB add operational complexity with no benefit here |
| uv | poetry | If your team is already fully committed to poetry and cannot change; uv is the modern standard as of 2025-2026 and is dramatically faster |
| uv | pipx | For end-user installs, `uv tool install` is the direct replacement for `pipx install`; recommend uv in docs but pipx works identically |
| asyncio.create_subprocess_exec | subprocess.run | For the `claude -p` / `cursor-agent -p` invocation; asyncio is required because we need a 600-second timeout boundary that does not block the process, and asyncio.timeout() (3.11+) is the cleanest way to implement this |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| argparse | Verbose, imperative, no type safety; requires manual help text; poor subcommand ergonomics | Typer |
| Click alone (without Typer) | Typer is Click with type hints; no reason to use Click directly unless you need its lower-level APIs | Typer (which exposes Click internals when needed) |
| LangChain | Massive dependency tree, frequent breaking changes, abstracts away things that are simple in direct ChromaDB API calls; TheHook's RAG needs are simple (embed → store → query) | Direct ChromaDB API |
| sentence-transformers (explicit) | ChromaDB's default embedding function already wraps all-MiniLM-L6-v2 via sentence-transformers; adding the dependency explicitly creates version conflicts | Let ChromaDB manage it via `chromadb.utils.embedding_functions.DefaultEmbeddingFunction()` |
| OpenAI / Anthropic API for embeddings | Requires API key setup (violates zero-config constraint); adds network dependency; costs money per embed | ChromaDB default local embeddings |
| requirements.txt | Replaced by pyproject.toml + uv.lock; mixing both creates confusion | pyproject.toml for declarations, uv.lock for reproducibility |
| setup.py | Deprecated Python packaging format | pyproject.toml |

---

## Stack Patterns by Variant

**For the SessionEnd hook handler (the capture script):**
- Use `asyncio.create_subprocess_exec` + `asyncio.timeout()` (3.11+) to call `claude -p` or `cursor-agent -p`
- The hook timeout from Claude Code docs is 600 seconds default for command hooks
- SessionEnd hooks cannot block session termination; run synchronously within the 600s window
- Read transcript JSONL from `transcript_path` in stdin JSON; each line is a JSON message record

**For the SessionStart hook handler (the inject script):**
- Use `chromadb.PersistentClient` to query the local index
- Output `{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "..."}}` to stdout on exit 0
- Keep this fast (target <2s); SessionStart hooks run on every session

**For the CLI (`thehook` commands):**
- Use Typer app with subcommands: `init`, `recall`, `status`, `reindex`
- Use Rich for all terminal output (spinners for indexing, tables for status)
- Config loaded from `.thehook/config.yaml` via pydantic-settings at startup

**If cursor-agent hangs:**
- PROJECT.md notes known stability issues with `cursor-agent -p`
- Wrap in `asyncio.wait_for()` with a hard timeout (suggest 90s, leaving buffer within 600s SessionEnd window)
- Catch `asyncio.TimeoutError` → surface error to user via stderr; fall back to no LLM extraction (store raw transcript only)

---

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| chromadb 1.5.1 | Python >=3.9 | Works on 3.11, 3.12, 3.13; avoid Python 3.14 (some C extension issues reported in GitHub issues as of research date) |
| typer 0.24.1 | Python >=3.10 | Raised minimum from 3.6 at 0.24.0; aligns with pydantic-settings >=3.10 requirement |
| pydantic-settings 2.13.1 | Python >=3.10 | Fine |
| pytest 9.0.2 | Python >=3.10 | Fine |
| mistune 3.2.0 | Python >=3.8 | Fine |
| PyYAML 6.0.3 | Python >=3.8 | Fine |
| rich 14.3.3 | Python >=3.8 | Fine |

**Minimum Python for the whole stack: 3.11** (asyncio.timeout() is available from 3.11; PROJECT.md mandates 3.11+; nothing in the stack conflicts with this)

---

## Hook Integration Details

From the official Claude Code hooks reference (verified 2026-02-23):

**SessionEnd input** (received on stdin):
```json
{
  "session_id": "abc123",
  "transcript_path": "~/.claude/projects/.../session.jsonl",
  "cwd": "/Users/.../project",
  "permission_mode": "default",
  "hook_event_name": "SessionEnd",
  "reason": "other"
}
```

**SessionStart stdout injection** (print on exit 0):
```json
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "Relevant memory from previous sessions..."
  }
}
```

**Hook configuration location:**
- Global: `~/.claude/settings.json` (recommended for TheHook — applies to all projects)
- Project: `.claude/settings.json` (alternative for project-scoped hooks)

**Transcript format:** JSONL — one JSON object per line, append-only. Fields include `type` (user/assistant/tool_result/summary), `message`, `timestamp`, `sessionId`, `uuid`, `parentUuid`. Parse with `json.loads()` per line.

**Default timeout:** 600 seconds for command hooks. SessionEnd hooks cannot block session termination.

---

## Sources

- [chromadb PyPI](https://pypi.org/project/chromadb/) — version 1.5.1, Python >=3.9 (HIGH confidence)
- [typer PyPI](https://pypi.org/project/typer/) — version 0.24.1, Python >=3.10 (HIGH confidence)
- [pydantic-settings PyPI](https://pypi.org/project/pydantic-settings/) — version 2.13.1, Python >=3.10 (HIGH confidence)
- [mistune PyPI](https://pypi.org/project/mistune/) — version 3.2.0, Python >=3.8 (HIGH confidence)
- [rich PyPI](https://pypi.org/project/rich/) — version 14.3.3, Python >=3.8 (HIGH confidence)
- [PyYAML PyPI](https://pypi.org/project/pyyaml/) — version 6.0.3, Python >=3.8 (HIGH confidence)
- [pytest PyPI](https://pypi.org/project/pytest/) — version 9.0.2, Python >=3.10 (HIGH confidence)
- [Claude Code Hooks Reference](https://code.claude.com/docs/en/hooks) — SessionStart/SessionEnd schemas, timeout behavior, stdout injection format (HIGH confidence — official Anthropic docs, fetched 2026-02-23)
- [ChromaDB Embedding Functions](https://docs.trychroma.com/docs/embeddings/embedding-functions) — default embedding model is all-MiniLM-L6-v2 via sentence-transformers (MEDIUM confidence — WebSearch verified against official Chroma docs)
- [uv official docs](https://docs.astral.sh/uv/) — uv tool install replaces pipx; uv build/publish for distribution (HIGH confidence)
- [Claude Code transcript format](https://databunny.medium.com/inside-claude-code-the-session-file-format-and-how-to-inspect-it-b9998e66d56b) — JSONL structure, message types (MEDIUM confidence — community article, consistent with hook reference docs)

---

*Stack research for: Python CLI tool with local RAG, markdown storage, YAML config, Claude Code / Cursor hook integration*
*Researched: 2026-02-23*
