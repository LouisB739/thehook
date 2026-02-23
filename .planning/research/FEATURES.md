# Feature Research

**Domain:** AI coding agent memory / knowledge management CLI tool
**Researched:** 2026-02-23
**Confidence:** HIGH (primary findings verified against official Claude Code docs and multiple competitor sources)

---

## Competitor Landscape

Before categorizing features, understand the existing tools TheHook competes with and learns from:

| Tool | Storage | Approach | Local? | Hook Integration |
|------|---------|----------|--------|-----------------|
| **claude-mem** | SQLite + ChromaDB | Captures all tool calls, AI-compresses, injects last N sessions | Yes | All 5 major lifecycle hooks |
| **supermemory** | Cloud API | Codebase indexing, team memory, signal-based extraction | No (requires API key) | SessionStart + SessionEnd |
| **mem0** | Vector DB (cloud) | Extracts key facts, semantic search via MCP | No (cloud) | MCP server, not hooks |
| **Pieces for Developers** | Local encrypted | OS-level capture across all tools (IDE + browser), 9-month memory | Yes | OS service, not code-level |
| **Anthropic native memory** | File-based `/memories/` | Agent writes files it deems worth saving; CLAUDE.md auto-loads | Yes | Not hooks-based; agent-initiated |

**TheHook's unique position:** Local-only + ChromaDB RAG + Markdown-as-truth + convention/decision extraction + hooks-based (not agent-initiated) + zero API key config.

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist. Missing these = product feels incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Automatic capture at session end | All competitors do this; manual capture is friction-killer | MEDIUM | Claude Code `SessionEnd` hook receives `transcript_path`; 120s timeout window is the constraint |
| Context injection at session start | The entire value prop; without this it's just a logger | MEDIUM | `SessionStart` hook outputs `additionalContext` via `hookSpecificOutput.additionalContext`; must be fast (keep hooks fast per docs) |
| Local-only storage | 64% of developers worried about sharing code with cloud providers (StackOverflow 2025); this is now expected | LOW | `.thehook/` per-project directory; no network calls |
| Natural language search / recall | Users expect to query their own history without SQL or regex | MEDIUM | `thehook recall "how did we handle auth"` — queries ChromaDB, returns relevant chunks |
| Zero-config installation | If setup takes >5 minutes, adoption dies | MEDIUM | `thehook init` wires hooks, creates directory structure, done |
| `status` command | Users need to know it's working | LOW | `thehook status` shows session count, last capture, index health |
| Persistent structured storage | Not just raw logs — searchable, organized | MEDIUM | Markdown files + ChromaDB dual storage; markdown is human-readable truth |
| Works with existing subscription | No new API keys = zero friction to try | HIGH | Headless `claude -p` / `cursor-agent -p` as LLM engine; this is the core differentiator vs cloud tools |

### Differentiators (Competitive Advantage)

Features that set the product apart. Not required, but valued.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Convention and architecture decision extraction | Competitors capture raw tool calls or conversation turns; TheHook extracts *meaning* — coding conventions, arch decisions — as structured knowledge | HIGH | Requires LLM pass over transcript to identify and extract decisions; stored as semantic knowledge, not raw text |
| Markdown as human-readable source of truth | claude-mem uses SQLite (opaque); supermemory uses cloud; TheHook's `.thehook/` is readable/grep-able/committable markdown | LOW | Differentiates on transparency and git-friendly workflows |
| ChromaDB reindex from markdown | ChromaDB is a disposable index — if corrupted, `thehook reindex` rebuilds from markdown; no data loss | MEDIUM | `thehook reindex` command; reflects "markdown is truth, vector DB is cache" philosophy |
| Auto-consolidation of sessions | Prevents index bloat; keeps knowledge base compact without manual curation; Mem0 does this but only in cloud | HIGH | Every N sessions, LLM consolidates session summaries into cumulative knowledge files; removes redundancy |
| Semantic relevance scoring at injection | Inject the *most relevant* context, not the most recent N sessions; claude-mem injects last 10 sessions regardless of relevance | MEDIUM | ChromaDB cosine similarity against current project state / recent prompt |
| Cursor CLI support (with fallback) | Extends to Cursor users without requiring a separate tool | HIGH | `cursor-agent -p` is unstable (known hanging issues per PROJECT.md); must detect, use, and surface errors gracefully |
| Project-scoped isolation | No cross-project contamination; can gitignore or commit `.thehook/` selectively | LOW | Per-project `.thehook/` vs global `~/.thehook/`; this is a deliberate design choice |
| YAML-configurable retrieval behavior | Power users can tune how much context gets injected, which hook points are active, consolidation frequency | MEDIUM | `thehook.yaml` config file; sensible defaults that require no changes for basic use |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Web dashboard / UI | "I want to visualize my memory" | Adds non-trivial maintenance surface; CLI-first users don't need it; creates GUI dependency for a background tool | `thehook status` + human-readable markdown files serve this need |
| Cross-project global memory | "Remember things across all my projects" | Context contamination; Rails project conventions polluting a Go project; privacy risk with project A context in project B session | Per-project `.thehook/` with explicit user opt-in to cross-reference if they choose |
| Cloud sync / backup | "I want my memory everywhere" | Requires auth, server ops, API keys, privacy policy; contradicts the zero-config local-only value prop | Git-commit `.thehook/` if you want it synced via your existing git workflow |
| Real-time capture (every tool call) | "Don't miss anything" | 120s timeout on `SessionEnd`; capturing every PostToolUse adds complexity and noise; claude-mem's approach bloats storage with low-signal data | Capture `SessionEnd` transcript only; transcript includes the full session anyway |
| Knowledge scoring / decay | "Old memories should matter less" | Adds algorithmic complexity without clear user benefit for coding conventions (arch decisions don't decay); Mem0 does this well at scale, but it's overkill for local single-dev use | Auto-consolidation handles freshness by synthesizing current understanding |
| Multi-user / team collaboration | "Share memory across the team" | Authentication, access control, conflict resolution — entirely different product scope; supermemory already does this | Single-developer workflow; team use can be achieved by committing `.thehook/md` files to the repo |
| Dedicated embedding model | "Better embeddings = better recall" | Adds setup complexity, GPU requirements, or API costs; contradicts zero-config design | ChromaDB default embeddings (all-MiniLM-L6-v2) are sufficient for code-related semantic search |
| Cursor rules integration | "Auto-update `.cursorrules` from memory" | Cursor rules are a different system with different semantics; managing them automatically creates conflict risk | Claude Code hooks are the primary integration; Cursor CLI is secondary |
| Interactive memory editor | "Let me edit/delete specific memories" | Markdown files are already editable directly; building a TUI editor duplicates functionality | Users edit `.thehook/*.md` directly; `thehook reindex` rebuilds the vector index after changes |

---

## Feature Dependencies

```
[thehook init]
    └──enables──> [SessionEnd hook]
                      └──captures──> [Transcript processing]
                                         └──produces──> [Session summaries (markdown)]
                                                            └──enables──> [ChromaDB indexing]
                                                                              └──enables──> [SessionStart injection]
                                                                              └──enables──> [thehook recall]

[Session summaries (markdown)]
    └──accumulates──> [Auto-consolidation]
                          └──produces──> [Cumulative knowledge files (markdown)]
                                             └──feeds──> [ChromaDB indexing]

[thehook reindex]
    └──reads──> [All markdown files in .thehook/]
                    └──rebuilds──> [ChromaDB index]

[LLM engine detection]
    └──enables──> [Convention extraction]
    └──enables──> [Auto-consolidation]
    └──enables──> [Session summarization]

[ChromaDB indexing] ──requires──> [LLM engine detection] (for convention extraction step)
[Auto-consolidation] ──requires──> [Session summaries (markdown)] (needs N sessions first)
[Cursor CLI support] ──conflicts with── [stable operation] (known hanging; must handle gracefully)
```

### Dependency Notes

- **`SessionStart` injection requires `ChromaDB indexing`:** Nothing to inject until at least one session has been captured and indexed. Handle gracefully on first run (inject nothing, log message).
- **`Auto-consolidation` requires `N sessions`:** Configure threshold (e.g., every 5 sessions); before threshold, operate in raw-summary mode.
- **`Convention extraction` requires `LLM engine`:** If neither `claude` nor `cursor-agent` is available, skip extraction and store raw summary only; degrade gracefully.
- **`thehook recall` requires `ChromaDB index`:** If index is empty, return helpful message rather than error.
- **`thehook reindex` unlocks recovery:** Dependency on markdown as source of truth makes this safe to run anytime.

---

## MVP Definition

### Launch With (v1)

Minimum viable product — what's needed to validate the concept.

- [ ] **`thehook init`** — Sets up `.thehook/` directory structure and wires `SessionEnd` + `SessionStart` hooks into `.claude/settings.json`. Without this, nothing works.
- [ ] **`SessionEnd` capture** — Reads `transcript_path` from hook stdin, runs LLM summarization via `claude -p`, writes structured markdown to `.thehook/sessions/`. This is the core value.
- [ ] **ChromaDB indexing** — Indexes all session markdown files on write. Required for semantic retrieval.
- [ ] **`SessionStart` context injection** — Queries ChromaDB for relevant past context, injects via `hookSpecificOutput.additionalContext`. This closes the loop.
- [ ] **`thehook recall`** — CLI command for manual natural language search. Required for trust-building; users need to see what's stored.
- [ ] **`thehook status`** — Shows session count, last capture, ChromaDB health, detected LLM engine.
- [ ] **`thehook reindex`** — Safety net; rebuild ChromaDB from markdown if index is corrupted.
- [ ] **Convention/decision extraction** — LLM prompt specifically targeting coding conventions and architecture decisions from transcript. This is what makes TheHook different from raw-capture tools.

### Add After Validation (v1.x)

Features to add once core is working.

- [ ] **Auto-consolidation** — Trigger: user reports that `recall` is getting slow or returning too much noise. Consolidate every N sessions into a single cumulative knowledge file.
- [ ] **YAML config** — Trigger: users want to tune injection token budget, consolidation frequency, or disable specific hooks. Add `thehook.yaml` with documented defaults.
- [ ] **Cursor CLI support** — Trigger: Cursor users request it. Add `cursor-agent -p` detection and fallback logic. The hanging issue must be handled with timeout + error surfacing.
- [ ] **`thehook forget`** — Trigger: user wants to delete a specific session or convention. Edit markdown + `thehook reindex`.

### Future Consideration (v2+)

Features to defer until product-market fit is established.

- [ ] **Cross-project memory (opt-in)** — Defer until users explicitly ask; requires careful isolation design. Very different use case from per-project memory.
- [ ] **MCP server interface** — Expose TheHook as an MCP tool so other agents can query it. Interesting but adds surface area; validate core value first.
- [ ] **Knowledge graph** — Replace flat ChromaDB with entity-relationship graph (like Vesper memory). Significant complexity; only worthwhile if recall quality is insufficient.
- [ ] **Diff-aware capture** — Only capture sessions with meaningful code changes. Requires git integration; may over-optimize early.

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| `thehook init` | HIGH | LOW | P1 |
| `SessionEnd` capture + summarization | HIGH | MEDIUM | P1 |
| Convention/decision extraction | HIGH | MEDIUM | P1 |
| ChromaDB indexing | HIGH | MEDIUM | P1 |
| `SessionStart` context injection | HIGH | MEDIUM | P1 |
| `thehook recall` | HIGH | LOW | P1 |
| `thehook status` | MEDIUM | LOW | P1 |
| `thehook reindex` | MEDIUM | LOW | P1 |
| Local-only, zero API key | HIGH | LOW (design decision) | P1 |
| Auto-consolidation | MEDIUM | HIGH | P2 |
| YAML config | MEDIUM | MEDIUM | P2 |
| Cursor CLI support | MEDIUM | HIGH (stability risk) | P2 |
| `thehook forget` | LOW | LOW | P2 |
| MCP server interface | LOW | HIGH | P3 |
| Cross-project memory | LOW | HIGH | P3 |
| Knowledge graph | LOW | HIGH | P3 |

**Priority key:**
- P1: Must have for launch
- P2: Should have, add when possible
- P3: Nice to have, future consideration

---

## Competitor Feature Analysis

| Feature | claude-mem | supermemory | mem0 | TheHook |
|---------|------------|-------------|------|---------|
| Storage | SQLite + ChromaDB (local) | Cloud API | Cloud vector DB | Markdown + ChromaDB (local) |
| Hook integration | All 5 lifecycle hooks (deep) | SessionStart + SessionEnd | MCP only | SessionEnd + SessionStart |
| Capture granularity | Every tool call (all tool usage) | Conversation turns | Extracted facts | Session transcript (end of session) |
| Extraction strategy | AI compression of raw observations | Signal keyword detection | Fact extraction | Convention + decision extraction |
| Context injection | Last N sessions (recency-based) | Up to 5 memories (recency) | Semantic retrieval | Semantic retrieval (ChromaDB) |
| Natural language search | Yes (3-layer: search → timeline → get) | Yes (`super-search` command) | Yes (semantic) | Yes (`thehook recall`) |
| Local / private | Yes | No (requires API key) | No (cloud) | Yes |
| Human-readable storage | No (SQLite is opaque) | No (cloud) | No (cloud) | Yes (markdown files) |
| Reindex / recovery | Not documented | Not applicable | Not applicable | Yes (`thehook reindex`) |
| Zero API key | Yes (plugin, uses Claude subscription) | No | No | Yes |
| Auto-consolidation | No (Endless Mode beta) | No | Partial (fact dedup) | Yes (planned v1.x) |
| Per-project scoping | Yes | Yes | Partial | Yes (`.thehook/` directory) |
| Cursor support | No | No | Via MCP | Yes (planned v1.x) |
| Team/shared memory | No | Yes (team memory) | Yes | No (single dev) |
| Web UI | Yes (localhost:8000) | No | Yes (cloud dashboard) | No (anti-feature) |

**TheHook's strongest differentiation:** Human-readable markdown truth + convention/decision extraction + fully local with zero new accounts.

---

## Sources

- [Claude Code Hooks Reference (official)](https://code.claude.com/docs/en/hooks) — HIGH confidence; defines all hook events, input schemas, and decision control options
- [claude-mem GitHub repository](https://github.com/thedotmack/claude-mem) — HIGH confidence; direct competitor feature analysis
- [claude-mem on BetterStack](https://betterstack.com/community/guides/ai/claude-mem/) — MEDIUM confidence; third-party analysis of claude-mem features
- [claude-supermemory GitHub repository](https://github.com/supermemoryai/claude-supermemory) — HIGH confidence; direct competitor feature analysis
- [Pieces for Developers — Long-Term Memory](https://pieces.app/features/long-term-memory) — MEDIUM confidence; established competitor
- [Mem0 — Universal Memory Layer](https://github.com/mem0ai/mem0) — MEDIUM confidence; infrastructure-level memory competitor
- [Mem0 OpenMemory](https://mem0.ai/openmemory) — MEDIUM confidence; MCP-based approach comparison
- [Top AI Memory Products 2026 — Medium](https://medium.com/@bumurzaqov2/top-10-ai-memory-products-2026-09d7900b5ab1) — LOW confidence (Medium, single author); ecosystem overview
- [Best AI Memory Systems — Pieces blog](https://pieces.app/blog/best-ai-memory-systems) — MEDIUM confidence; market overview from established player
- [10 Things Developers Want from Agentic IDEs (RedMonk, 2025)](https://redmonk.com/kholterhoff/2025/12/22/10-things-developers-want-from-their-agentic-ides-in-2025/) — MEDIUM confidence; analyst perspective on developer expectations
- [StackOverflow Developer Survey privacy concerns](https://privacydev.org/posts/ai-programming-tools) — MEDIUM confidence; privacy as table-stakes requirement
- [Memory in the Age of AI Agents (arxiv 2512.13564)](https://arxiv.org/abs/2512.13564) — MEDIUM confidence; academic framing of memory types
- [Building AI Memory Beyond RAG — Tracardi](https://tracardi.com/index.php/2025/12/20/building-ai-memory-a-new-approach-beyond-rag/) — LOW confidence; single source; useful for consolidation design patterns

---

*Feature research for: AI coding agent memory / knowledge management CLI tool (TheHook)*
*Researched: 2026-02-23*
