# Project Research Summary

**Project:** TheHook
**Domain:** Local RAG memory CLI tool for AI coding agents (Claude Code / Cursor)
**Researched:** 2026-02-23
**Confidence:** HIGH

## Executive Summary

TheHook is a local-only, zero-API-key memory layer for AI coding agents that captures session knowledge at session end and injects relevant context at session start via Claude Code and Cursor lifecycle hooks. The market has direct competitors (claude-mem, supermemory, mem0, Pieces), but none combine local-only storage, human-readable markdown as source of truth, structured convention and architecture decision extraction, and ChromaDB semantic retrieval in a single tool. The recommended approach is a Python CLI built on Typer + ChromaDB + pydantic-settings, using the "markdown primary, ChromaDB secondary" invariant: every knowledge unit is written to a `.md` file first, then upserted to ChromaDB, so the vector index is always a disposable and rebuildable cache.

The two lifecycle hooks are the entire integration surface. `SessionEnd` triggers capture: parse the JSONL transcript, call `claude -p` headlessly to extract conventions and decisions, write structured markdown, index into ChromaDB. `SessionStart` triggers retrieval: query ChromaDB for semantically relevant chunks and inject them via `hookSpecificOutput.additionalContext`. The CLI commands (`init`, `recall`, `status`, `reindex`) wrap these core flows for user control. The build order is strictly bottom-up: storage layer first, core services second, hook entrypoints third, CLI commands last.

The three critical risks are all in Phase 1 and must be solved before any other feature is built: (1) the SessionEnd hook subprocess handling — `claude -p` must use `Popen + killpg` with an 85-second hard timeout and graceful degradation, never `subprocess.run` with `capture_output`; (2) the LLM hallucination/false-memory problem — extraction prompts must constrain factual output and store provenance (`session_id`, `transcript_path`) in frontmatter; (3) context window overflow at `SessionStart` — injected context must be hard-capped at 2,000 tokens regardless of knowledge base size. None of these are addressable as afterthoughts; they must be architectural invariants from the first working hook.

---

## Key Findings

### Recommended Stack

The stack is fully resolved with HIGH confidence. All versions verified against PyPI as of 2026-02-23. The minimum Python version is **3.11** (driven by `asyncio.timeout()` and the project requirement, not by individual package constraints). **uv** replaces pip/pipx/poetry as the package manager; `uv tool install thehook` is the end-user install path.

**Core technologies:**
- **Python 3.11+** — runtime; `asyncio.timeout()` (3.11+) required for subprocess timeout handling
- **Typer 0.24.1** — CLI framework; type-hint-driven subcommands, Click under the hood
- **ChromaDB 1.5.1** — local vector store; `PersistentClient(path=".thehook/chromadb/")` with default all-MiniLM-L6-v2 embeddings; no server required
- **pydantic-settings 2.13.1 + pydantic-settings-yaml** — YAML config loading with schema validation; prevents silent misconfiguration
- **Rich 14.3.3** — terminal output; spinners, tables, progress for CLI UX
- **mistune 3.2.0** — markdown parsing for session file extraction (3-4x faster than alternatives)
- **uv** — package manager; `uv tool install` for end-users, `uv sync` for dev

**What to avoid:** LangChain (unnecessary abstraction over direct ChromaDB API), explicit sentence-transformers dependency (ChromaDB manages it), OpenAI/Anthropic API for embeddings (violates zero-config constraint), `argparse` or bare Click (Typer is strictly better here).

### Expected Features

**Must have (table stakes — launch blockers):**
- `thehook init` — wires SessionEnd and SessionStart hooks into `~/.claude/settings.json`; without this nothing works
- Automatic `SessionEnd` capture — reads `transcript_path`, calls `claude -p`, writes structured markdown
- Convention and architecture decision extraction — the primary differentiator; LLM prompt targeting specific knowledge types, not raw capture
- ChromaDB indexing of session summaries — required for semantic retrieval
- `SessionStart` context injection — queries ChromaDB, outputs `hookSpecificOutput.additionalContext` JSON; closes the loop
- `thehook recall` — natural language search; required for user trust and visibility into stored memory
- `thehook status` — shows session count, last capture timestamp/status, ChromaDB health, detected LLM engine
- `thehook reindex` — rebuilds ChromaDB from markdown; the recovery path for nearly every failure mode
- Local-only, zero API key — design decision, not a feature; but removing this removes the entire value proposition

**Should have (competitive differentiators — add after v1 validates):**
- Auto-consolidation — every N sessions, LLM merges session summaries into a cumulative knowledge file; prevents retrieval noise degradation
- YAML config (`thehook.yaml`) — lets power users tune token budget, consolidation threshold, active hooks
- Cursor CLI support — `cursor-agent -p` with timeout + graceful fallback; known hanging issues must be handled explicitly
- `thehook forget` — delete specific sessions from markdown + reindex

**Defer (v2+):**
- Cross-project memory — different use case, context contamination risk
- MCP server interface — exposes TheHook to other agents; validates core value first
- Knowledge graph — only justified if recall quality is demonstrably insufficient at scale
- Diff-aware capture — git integration; over-optimization before product-market fit

**Anti-features to avoid building:** web dashboard, cloud sync, real-time per-tool-call capture, interactive TUI memory editor, dedicated embedding model configuration.

### Architecture Approach

The architecture is two pipelines orchestrated by lifecycle hooks. The capture pipeline (SessionEnd) flows: Hook Runner → Transcript Parser → Extraction Engine → Markdown Store → ChromaDB Indexer → optional Consolidation Engine. The retrieval pipeline (SessionStart) flows: Hook Runner → Retrieval Engine → stdout JSON. The CLI commands (`init`, `recall`, `status`, `reindex`) are thin wrappers over these same core services. The "dual-write" invariant — markdown written first, ChromaDB upserted second — is the single most important architectural decision; it makes `thehook reindex` a safe, complete recovery mechanism and keeps all stored knowledge human-readable and git-committable.

**Major components:**
1. **Transcript Parser** (`core/transcript.py`) — pure function; reads JSONL at `transcript_path`, handles both string and array content shapes, returns plain conversation text
2. **Extraction Engine** (`core/extractor.py`) — subprocess `claude -p` call with `Popen + killpg + 85s timeout`; returns structured markdown with SUMMARY / CONVENTIONS / DECISIONS / GOTCHAS sections
3. **Markdown Store** (`core/store.py`) — writes `.thehook/sessions/{session_id}.md` and `.thehook/knowledge/*.md`; source of truth
4. **ChromaDB Indexer** (`core/indexer.py`) — `PersistentClient` wrapper; upserts with rich metadata (`session_id`, `doc_type`, `project`, `timestamp`); query with metadata filtering; reindex via drop-and-recreate
5. **Retrieval Engine** (within `core/indexer.py`) — ChromaDB query; hard cap at 2,000 injection tokens; formats as context block
6. **Hook Entrypoints** (`hooks/capture.py`, `hooks/retrieve.py`) — thin orchestrators; no business logic
7. **CLI Commands** (`cli.py`) — Typer app; all user-facing commands; Rich output

### Critical Pitfalls

1. **`claude -p` subprocess hang from PIPE buffer overflow** — Use `subprocess.Popen` + `proc.communicate(timeout=85)` + `os.killpg(os.getpgid(proc.pid), signal.SIGKILL)` on `TimeoutExpired`. Never use `subprocess.run(..., capture_output=True)`. Always pass `--max-turns 3` to bound LLM execution. This is Phase 1 work; getting this wrong causes silent hook failures that are hard to diagnose.

2. **SessionEnd timeout race** — Budget: transcript read (~1s) + `claude -p` (85s max) + markdown write (~1s) + ChromaDB index (~2s) = 89s. Hook timeout is 600s (not 120s as noted in some project docs), but the `claude -p` subprocess is the constraint. Always write a stub summary on timeout rather than failing silently — never leave a zero-byte markdown file.

3. **False memory snowball (hallucinated facts compound)** — LLM hallucinations in session summaries become injected context, which Claude treats as authoritative in future sessions. Prevention: constrain extraction prompts to short factual output (conventions, commands, decisions — not narrative); store `session_id` + `transcript_path` in markdown frontmatter for traceability; implement `thehook status --verbose` so users can inspect what will be injected.

4. **Context window overflow at SessionStart** — As the knowledge base grows, retrieved chunks grow too. Hard-cap injected context at 2,000 tokens in the retrieval pipeline, not just at `n_results=5`. Truncate at the token limit, not the document count. Design this constraint into the retrieval engine in Phase 2, not retrofitted later.

5. **ChromaDB HNSW memory growth after reindex** — Implement `thehook reindex` as full collection drop-and-recreate, not soft-delete-and-readd. Set `allow_replace_deleted=True` at collection creation. This makes reindex safe and prevents memory bloat over long-running sessions.

---

## Implications for Roadmap

Based on the architectural build order (storage → services → hooks → CLI) and the Phase 1 pitfall cluster, four phases are suggested:

### Phase 1: Foundation — Hook Infrastructure and Storage

**Rationale:** Every other feature depends on the hooks working reliably and the storage layer being correct. The three most critical pitfalls (subprocess hang, timeout race, false memory) must all be solved here. If Phase 1 is skipped or shortcuts are taken, all subsequent phases are built on a broken foundation.

**Delivers:**
- `thehook init` command (creates `.thehook/` directory structure, writes `.gitignore`, registers SessionEnd + SessionStart hooks in `~/.claude/settings.json`)
- Transcript JSONL parser handling both string and array content shapes
- Subprocess wrapper with correct `Popen + killpg + timeout` implementation
- Extraction prompt producing SUMMARY / CONVENTIONS / DECISIONS / GOTCHAS in structured markdown
- Markdown store writing session files with frontmatter (session_id, transcript_path, timestamp)
- `.thehook/last_capture_status` file written after every hook run (foundation for `status` command)
- `.thehook/` gitignore entry written by `init` with a loud warning if the directory is tracked

**Addresses features:** `thehook init`, SessionEnd capture, convention/decision extraction, local-only storage, zero API key, graceful degradation

**Avoids pitfalls:** subprocess PIPE buffer overflow (Pitfall 2), SessionEnd timeout race (Pitfall 1), hallucinated facts (Pitfall 4), silent hook failures (UX pitfall), `.thehook/` committed to git (security pitfall)

**Research flag:** STANDARD PATTERNS — subprocess process group management is well-documented in Python; Claude Code hooks protocol is fully specified in official docs. No additional research needed.

---

### Phase 2: Semantic Storage and Retrieval

**Rationale:** Once capture is reliable, the retrieval loop must be closed. This phase adds ChromaDB indexing of captured markdown and the SessionStart injection, making TheHook functionally complete for its core value proposition. The ChromaDB memory management pitfall and context window overflow pitfall must both be addressed here.

**Delivers:**
- ChromaDB indexer with rich metadata (`session_id`, `doc_type`, `project`, `timestamp`) on every upsert
- `thehook reindex` command as drop-and-recreate (not soft-delete); serves as universal recovery mechanism
- `allow_replace_deleted=True` set at collection creation
- SessionStart retrieval hook: query ChromaDB by `cwd`, format top-k chunks, hard-cap at 2,000 injection tokens, output `hookSpecificOutput.additionalContext` JSON
- `thehook recall "query"` — same retrieval flow, printed to terminal
- `thehook status` — session count, last capture timestamp/status, ChromaDB document count, detected LLM engine
- Batch size guard on `chroma.add()` (≤5,000 per call)
- Project isolation via `where={"project": cwd}` metadata filter in all queries

**Addresses features:** ChromaDB indexing, SessionStart context injection, `thehook recall`, `thehook status`, `thehook reindex`

**Avoids pitfalls:** ChromaDB HNSW memory growth (Pitfall 3), context window overflow (Pitfall 5), cross-project contamination (performance trap), no-dedup injection (tech debt)

**Research flag:** STANDARD PATTERNS — ChromaDB PersistentClient API is well-documented; retrieval patterns are established. Token counting for context cap uses `len(text.split()) * 1.3` as a rough proxy or tiktoken if precision is needed.

---

### Phase 3: CLI Polish and Observability

**Rationale:** The core pipeline works after Phase 2. Phase 3 makes the tool usable and trustworthy: users need visibility into what is captured and injected, the ability to delete bad memories, and rich terminal output. This phase has no new architectural risk — it is pure CLI and UX work on top of the storage and retrieval layers already built.

**Delivers:**
- `thehook status --verbose` showing exactly what would be injected in the next session
- Rich terminal output throughout (spinners during indexing, tables for status, progress during reindex)
- `thehook forget <session-id>` — deletes session markdown + triggers reindex
- Hook installation verification in `thehook init` (confirms hook appears in Claude Code settings, prints hook file paths)
- Reindex progress streaming to stderr ("Indexed 47/200 sessions...")
- `--max-turns` passed to `claude -p` calls (bounds LLM tool-using loops)
- Session stub summary on extraction timeout (ensures `thehook status` reports "capture timeout" not "success")

**Addresses features:** `thehook status`, `thehook forget`, full CLI UX via Rich

**Avoids pitfalls:** silent hook failures, no visibility into injected context, reindex with no progress output, `thehook init` with no confirmation

**Research flag:** STANDARD PATTERNS — Rich library patterns are well-documented; no research needed.

---

### Phase 4: Auto-Consolidation and Configuration

**Rationale:** After validation that the core loop works, auto-consolidation prevents knowledge base degradation over time. YAML config gives power users control without requiring code changes. Cursor CLI support, if added, belongs here because of its known instability — it must not be introduced until the stable Claude path is proven. These are all P2 features in the prioritization matrix.

**Delivers:**
- Auto-consolidation: every N sessions, `claude -p` merges session summaries + existing knowledge into updated `.thehook/knowledge/project-knowledge.md`; N is configurable
- `thehook.yaml` config loaded via pydantic-settings: `max_injection_tokens`, `consolidation_threshold`, `active_hooks`, `llm_timeout`
- Detector module (`core/detector.py`) — finds `claude` or `cursor-agent` binary on PATH
- Cursor CLI support: `cursor-agent -p` with same `Popen + killpg + timeout` wrapper; surfaces hanging errors to user via stderr; falls back to no-LLM stub summary
- Consolidation conflict detection (flag contradictions in merged knowledge rather than blindly overwriting)

**Addresses features:** auto-consolidation, YAML config, Cursor CLI support

**Avoids pitfalls:** extraction quality degradation at scale (Pitfall scaling note), cursor-agent hanging (known instability), consolidation running inline blocking hooks (performance trap)

**Research flag:** NEEDS RESEARCH — `cursor-agent -p` CLI stability and exact flag compatibility should be verified against the current Cursor release before implementation. The hanging issue is documented but the current state may have changed.

---

### Phase Ordering Rationale

- **Phase 1 before everything:** Hook infrastructure failures are silent and compound. A broken subprocess wrapper or missing graceful degradation means months of false-positive "it's working" signals. The pitfalls research explicitly maps five pitfalls to Phase 1.
- **Phase 2 before Phase 3:** The CLI polish in Phase 3 depends on the storage and retrieval layer existing. `thehook status --verbose` requires ChromaDB to be queryable.
- **Phase 3 before Phase 4:** Consolidation writes to the same markdown + ChromaDB pipeline that must be observable and debuggable before adding another LLM-call layer on top.
- **Cursor in Phase 4:** Cursor CLI support is explicitly P2 and has known stability issues. Introducing it in Phase 1 or 2 would contaminate the critical path with instability that makes the core loop harder to debug.

### Research Flags

**Phases needing deeper research during planning:**
- **Phase 4 (Cursor CLI):** `cursor-agent -p` stability status needs verification against current Cursor release; the hanging behavior documented in PITFALLS.md was current as of research date but may have changed
- **Phase 4 (Consolidation prompt):** The LLM prompt for conflict-aware consolidation (detecting contradictions between old and new knowledge) has no well-documented pattern; needs prompt engineering research or experimentation

**Phases with standard patterns (skip research-phase):**
- **Phase 1:** Claude Code hooks protocol fully specified in official docs; Python subprocess process group management is well-documented
- **Phase 2:** ChromaDB PersistentClient API is official and stable; RAG retrieval patterns are established
- **Phase 3:** Rich library, Typer CLI patterns — all standard

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All versions verified against PyPI; hook integration verified against official Claude Code docs |
| Features | HIGH | Competitor analysis grounded in real repo inspection (claude-mem); hook schemas verified against official docs |
| Architecture | HIGH | Hook input/output schemas verified against official docs; ChromaDB API verified against official docs; data flow is deterministic |
| Pitfalls | HIGH | Subprocess hang sourced from Python issue tracker; ChromaDB memory issues sourced from official GitHub issues; hook timeout verified against official docs |

**Overall confidence:** HIGH

### Gaps to Address

- **Transcript JSONL content shape variation:** The JSONL parser must handle both string content (user messages) and array content blocks (assistant messages). Community sources confirm this dual shape but the full schema should be verified with a real transcript early in Phase 1 development. Mitigation: use a short real transcript as a test fixture from day one.

- **SessionStart hook `source` matching:** SessionStart fires on `startup`, `resume`, `clear`, and `compact`. The architecture recommends using the `startup` matcher to inject context only on new sessions. This behavior should be verified during Phase 1 hook setup — injecting context on `resume` may double-inject on resumed sessions.

- **`cursor-agent -p` current stability:** The hanging issue is well-documented but was last verified during research date. By the time Phase 4 is reached, the Cursor CLI may have been fixed or may have broken differently. Do not design around the current behavior; design around the timeout pattern and verify actual behavior during implementation.

- **Token counting approach:** The retrieval injection cap (2,000 tokens) requires counting tokens before output. ChromaDB returns raw text; a simple `len(text.split()) * 1.3` approximation is acceptable for MVP but may under-count code-heavy context (code has many tokens per word). Consider tiktoken for Phase 2 if precision matters.

---

## Sources

### Primary (HIGH confidence)
- [Claude Code Hooks Reference — Official Docs](https://code.claude.com/docs/en/hooks) — SessionStart/SessionEnd schemas, timeout behavior, stdout injection format, hook configuration location
- [ChromaDB PyPI](https://pypi.org/project/chromadb/) — version 1.5.1, Python >=3.9
- [Typer PyPI](https://pypi.org/project/typer/) — version 0.24.1, Python >=3.10
- [pydantic-settings PyPI](https://pypi.org/project/pydantic-settings/) — version 2.13.1
- [ChromaDB HNSW Issue #2594](https://github.com/chroma-core/chroma/issues/2594) — HNSW index memory never shrinks
- [ChromaDB Memory Issue #5843](https://github.com/chroma-core/chroma/issues/5843) — memory not freed after deletes
- [Python subprocess timeout bug — CPython Issue #81605](https://github.com/python/cpython/issues/81605) — `subprocess.run` + `capture_output` hang
- [ChromaDB Cookbook — Memory Management](https://cookbook.chromadb.dev/strategies/memory-management/) — `allow_replace_deleted` pattern
- [ChromaDB Cookbook — Rebuilding](https://cookbook.chromadb.dev/strategies/rebuilding/) — drop-and-recreate pattern
- [Memory Injection Attacks on LLM Agents — arXiv 2503.03704](https://arxiv.org/abs/2503.03704) — prompt injection via memory security risk

### Secondary (MEDIUM confidence)
- [claude-mem GitHub repository](https://github.com/thedotmack/claude-mem) — competitor feature analysis; direct inspiration for hook architecture
- [claude-supermemory GitHub repository](https://github.com/supermemoryai/claude-supermemory) — competitor feature analysis
- [ChromaDB Embedding Functions — Official Docs](https://docs.trychroma.com/docs/embeddings/embedding-functions) — default embedding model is all-MiniLM-L6-v2
- [Claude Code transcript JSONL format — Simon Willison](https://simonwillison.net/2025/Dec/25/claude-code-transcripts/) — community-verified JSONL structure
- [uv official docs](https://docs.astral.sh/uv/) — uv tool install, build, publish patterns
- [Seven RAG Pitfalls — Label Studio](https://labelstud.io/blog/seven-ways-your-rag-system-could-be-failing-and-how-to-fix-them/) — context window overflow and retrieval noise patterns
- [SessionStart Hooks Infinite Hang — Claude Code GitHub Issue #9542](https://github.com/anthropics/claude-code/issues/9542) — SessionStart blocking confirmed issue

### Tertiary (LOW confidence)
- [Top AI Memory Products 2026 — Medium](https://medium.com/@bumurzaqov2/top-10-ai-memory-products-2026-09d7900b5ab1) — ecosystem overview; used only for market framing
- [Building AI Memory Beyond RAG — Tracardi](https://tracardi.com/index.php/2025/12/20/building-ai-memory-a-new-approach-beyond-rag/) — consolidation design patterns; single source

---
*Research completed: 2026-02-23*
*Ready for roadmap: yes*
