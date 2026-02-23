# Requirements: TheHook

**Defined:** 2026-02-23
**Core Value:** The agent remembers what matters — conventions, decisions, and project history — without the developer lifting a finger.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Setup

- [x] **SETUP-01**: User can run `thehook init` to wire SessionEnd and SessionStart hooks into Claude Code settings
- [x] **SETUP-02**: `thehook init` creates `.thehook/` directory structure (sessions/, knowledge/, chromadb/)
- [x] **SETUP-03**: User can configure behavior via `thehook.yaml` (token budget, consolidation threshold, active hooks)
- [x] **SETUP-04**: Config has sensible defaults — tool works without any YAML file present

### Capture

- [x] **CAPT-01**: SessionEnd hook reads `transcript_path` from stdin JSON and parses JSONL transcript
- [x] **CAPT-02**: JSONL parser handles both string content (user messages) and array-of-blocks content (assistant messages)
- [ ] **CAPT-03**: LLM extraction calls `claude -p` via subprocess (Popen + killpg process group, 85s hard timeout)
- [ ] **CAPT-04**: Extraction produces structured markdown: session summary, conventions discovered, architecture decisions
- [ ] **CAPT-05**: On timeout or LLM failure, a stub summary is written with raw transcript metadata (graceful degradation)
- [ ] **CAPT-06**: Extraction prompt targets specific knowledge types (conventions, ADRs) — not raw observation capture

### Storage

- [ ] **STOR-01**: Session knowledge is written as structured markdown files in `.thehook/sessions/`
- [ ] **STOR-02**: Markdown files include frontmatter with session_id, timestamp, and source transcript path
- [ ] **STOR-03**: ChromaDB indexes all markdown knowledge with metadata (session_id, type, timestamp)
- [ ] **STOR-04**: ChromaDB uses `PersistentClient` with local storage in `.thehook/chromadb/`
- [ ] **STOR-05**: User can run `thehook reindex` to drop and recreate ChromaDB from markdown files

### Retrieval

- [ ] **RETR-01**: SessionStart hook queries ChromaDB for context relevant to the current project
- [ ] **RETR-02**: Injected context is hard-capped at 2,000 tokens regardless of knowledge base size
- [ ] **RETR-03**: SessionStart outputs valid `hookSpecificOutput.additionalContext` JSON to stdout
- [ ] **RETR-04**: User can run `thehook recall <query>` for natural language search over stored knowledge

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Observability

- **OBS-01**: `thehook status` shows session count, last capture timestamp/status, ChromaDB health, detected LLM engine
- **OBS-02**: Source provenance tracking — session_id and transcript_path in all extracted knowledge for traceability

### Memory Management

- **MGMT-01**: Auto-consolidation every N sessions merges session summaries into cumulative knowledge files
- **MGMT-02**: `thehook forget <session>` deletes specific sessions from markdown and reindexes

### Platform Support

- **PLAT-01**: Auto-detect and use `cursor-agent -p` as alternative LLM engine with timeout fallback
- **PLAT-02**: Cursor CLI hook integration (when cursor-agent stability improves)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Web dashboard / TUI editor | CLI-first, keep it simple |
| Cross-project memory (~/.thehook/) | Context contamination risk, per-project only |
| Dedicated embedding model config | ChromaDB default (all-MiniLM-L6-v2) is sufficient |
| Cloud sync | Everything stays local, zero network dependencies |
| Knowledge scoring / decay | Auto-consolidation handles freshness (v2) |
| Multi-user / collaboration | Single developer workflow |
| MCP server interface | Validate core value first |
| Real-time per-tool-call capture | Over-engineering; session-level is sufficient |
| Knowledge graph | Only justified if recall quality insufficient at scale |
| Diff-aware git capture | Over-optimization before product-market fit |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| SETUP-01 | Phase 1 | Complete |
| SETUP-02 | Phase 1 | Complete |
| SETUP-03 | Phase 1 | Complete |
| SETUP-04 | Phase 1 | Complete |
| CAPT-01 | Phase 2 | Complete |
| CAPT-02 | Phase 2 | Complete |
| CAPT-03 | Phase 2 | Pending |
| CAPT-04 | Phase 2 | Pending |
| CAPT-05 | Phase 2 | Pending |
| CAPT-06 | Phase 2 | Pending |
| STOR-01 | Phase 3 | Pending |
| STOR-02 | Phase 3 | Pending |
| STOR-03 | Phase 3 | Pending |
| STOR-04 | Phase 3 | Pending |
| STOR-05 | Phase 3 | Pending |
| RETR-01 | Phase 4 | Pending |
| RETR-02 | Phase 4 | Pending |
| RETR-03 | Phase 4 | Pending |
| RETR-04 | Phase 4 | Pending |

**Coverage:**
- v1 requirements: 19 total
- Mapped to phases: 19
- Unmapped: 0

---
*Requirements defined: 2026-02-23*
*Last updated: 2026-02-23 after roadmap creation*
