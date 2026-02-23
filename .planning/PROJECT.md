# TheHook

## What This Is

A self-improving long-term memory for AI coding agents. TheHook hooks into Claude Code and Cursor's native lifecycle events to capture conversation summaries, extract project conventions and architecture decisions, index them in a local RAG (ChromaDB), and provide intelligent context retrieval at each new session. It's a Python CLI tool installed via pip, targeting developers who use AI coding assistants daily.

## Core Value

The agent remembers what matters — conventions, decisions, and project history — without the developer lifting a finger. Every session makes the memory smarter.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Capture conversation summaries via hooks at session end
- [ ] Extract conventions and architecture decisions from conversations
- [ ] Store session summaries as structured markdown files
- [ ] Index knowledges in local ChromaDB for vector search
- [ ] Auto-inject relevant context at conversation start
- [ ] Manual search with natural language queries (`thehook recall`)
- [ ] Auto-consolidate sessions into cumulative knowledge files
- [ ] Detect and use available CLI (claude or cursor-agent) as LLM engine
- [ ] Project-scoped storage in `.thehook/` directory
- [ ] Configurable retrieval behavior via YAML config
- [ ] `thehook init` sets up hooks and directory structure
- [ ] `thehook status` shows memory state
- [ ] `thehook reindex` rebuilds ChromaDB from markdown files

### Out of Scope

- Web interface / dashboard — CLI-first, keep it simple
- Cross-project memory (global `~/.thehook/`) — per-project only for MVP
- Dedicated embedding model — ChromaDB default embeddings are sufficient
- Knowledge scoring / decay — auto-consolidation handles freshness
- Multi-user / collaboration — single developer workflow
- Cloud sync — everything stays local
- Cursor rules integration — Claude Code hooks first, Cursor CLI support via `cursor-agent -p`

## Context

- **Team stack**: Ruby app, but TheHook is a standalone Python CLI tool (install once, use everywhere)
- **Claude Code hooks**: `SessionEnd` provides `transcript_path` in stdin JSON; `SessionStart` can inject context via stdout JSON
- **Cursor CLI**: `cursor-agent -p` exists but has known stability issues (hangs); we detect and surface errors to user
- **Markdown as source of truth**: All knowledge stored as readable `.md` files; ChromaDB is a disposable search index rebuilt from them
- **LLM engine**: Zero API key config — piggyback on existing Claude Code / Cursor subscriptions via headless CLI mode (`claude -p` / `cursor-agent -p`)

## Constraints

- **Python 3.11+**: ChromaDB requires it, and it's the natural fit for the ML/embeddings ecosystem
- **Local only**: No network dependencies beyond the CLI tool itself (which the user already has)
- **Zero config API keys**: Must work with existing Claude Code or Cursor subscription, no additional setup
- **Hook timeout**: SessionEnd hooks have 120s timeout; capture must complete within that window

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Python over Ruby/TS | ChromaDB is native Python; team doesn't maintain this tool, they use it | — Pending |
| Markdown + ChromaDB dual storage | Markdown is human-readable truth; ChromaDB is disposable search index | — Pending |
| CLI headless as LLM engine | Zero config, uses existing subscription, no API key needed | — Pending |
| Per-project `.thehook/` | Project isolation, no cross-contamination, can gitignore or commit | — Pending |
| Auto-consolidation every N sessions | Keeps knowledge base compact without manual intervention | — Pending |
| Claude Code hooks (not MCP) | Simplest integration, native lifecycle events, zero friction | — Pending |

---
*Last updated: 2026-02-23 after initialization*
