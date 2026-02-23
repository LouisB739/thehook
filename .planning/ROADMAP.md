# Roadmap: TheHook

## Overview

TheHook is built in four phases that follow the natural dependency chain of the tool: initialize the project structure and configuration, wire the capture pipeline that reads transcripts and extracts knowledge, persist that knowledge to markdown and ChromaDB, then close the loop with context retrieval at session start. Each phase delivers one complete, verifiable capability. After Phase 4, the full memory loop is working — capture at SessionEnd, index to ChromaDB, inject at SessionStart, recall on demand.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Setup** - `thehook init` wires hooks and creates project structure; config loads with sensible defaults (completed 2026-02-23)
- [x] **Phase 2: Capture** - SessionEnd hook reads transcript, calls `claude -p`, and extracts structured knowledge with graceful degradation (completed 2026-02-23)
- [ ] **Phase 3: Storage** - Extracted knowledge is written to markdown files and indexed in ChromaDB; reindex rebuilds from markdown
- [ ] **Phase 4: Retrieval** - SessionStart injects relevant context; `thehook recall` enables natural language search

## Phase Details

### Phase 1: Setup
**Goal**: The tool is installable and a developer can initialize it in any project with one command
**Depends on**: Nothing (first phase)
**Requirements**: SETUP-01, SETUP-02, SETUP-03, SETUP-04
**Success Criteria** (what must be TRUE):
  1. Running `thehook init` in a project root creates `.thehook/` with `sessions/`, `knowledge/`, and `chromadb/` subdirectories
  2. Running `thehook init` registers SessionEnd and SessionStart hooks in `~/.claude/settings.json` and the user sees confirmation
  3. TheHook works without any `thehook.yaml` file present — sensible defaults are applied silently
  4. A `thehook.yaml` file with custom values (token budget, consolidation threshold, active hooks) is loaded and applied over defaults
**Plans**: 2 plans
- [x] 01-01-PLAN.md — Package scaffold + config system (SETUP-03, SETUP-04)
- [x] 01-02-PLAN.md — Init command + hook registration (SETUP-01, SETUP-02)

### Phase 2: Capture
**Goal**: At every Claude Code session end, conversation knowledge is automatically extracted and ready to store
**Depends on**: Phase 1
**Requirements**: CAPT-01, CAPT-02, CAPT-03, CAPT-04, CAPT-05, CAPT-06
**Success Criteria** (what must be TRUE):
  1. After a Claude Code session ends, the SessionEnd hook reads the `transcript_path` from stdin JSON and parses the JSONL transcript without error
  2. The extraction produces a structured markdown document with SUMMARY, CONVENTIONS, DECISIONS, and GOTCHAS sections — not raw transcript content
  3. Both user message content (string) and assistant message content (array of blocks) are parsed correctly
  4. If `claude -p` hangs or exceeds the 85-second timeout, a stub summary is written with transcript metadata and the hook exits cleanly — no silent failures
  5. The extraction prompt targets conventions and architecture decisions specifically, not general observations
**Plans**: 3 plans
Plans:
- [x] 02-01-PLAN.md — JSONL transcript parsing with TDD (CAPT-01, CAPT-02)
- [x] 02-02-PLAN.md — LLM extraction subprocess and graceful degradation with TDD (CAPT-03, CAPT-05)
- [ ] 02-03-PLAN.md — Extraction prompt, capture orchestration, and CLI wiring (CAPT-04, CAPT-06)

### Phase 3: Storage
**Goal**: Extracted knowledge is durably persisted as human-readable markdown and semantically indexed in ChromaDB
**Depends on**: Phase 2
**Requirements**: STOR-01, STOR-02, STOR-03, STOR-04, STOR-05
**Success Criteria** (what must be TRUE):
  1. Each captured session produces a markdown file in `.thehook/sessions/` with frontmatter containing `session_id`, `timestamp`, and `source_transcript_path`
  2. Every session markdown file is indexed in ChromaDB with metadata fields (`session_id`, `type`, `timestamp`) enabling filtered queries
  3. ChromaDB is stored locally in `.thehook/chromadb/` using `PersistentClient` — no server process required
  4. Running `thehook reindex` drops the ChromaDB collection and recreates it from all markdown files in `.thehook/sessions/` — the index is always fully reconstructible
**Plans**: 2 plans
Plans:
- [ ] 03-01-PLAN.md — ChromaDB storage module with TDD (STOR-02, STOR-03, STOR-04, STOR-05)
- [ ] 03-02-PLAN.md — CLI reindex command and capture pipeline integration (STOR-01, STOR-03, STOR-05)

### Phase 4: Retrieval
**Goal**: The memory loop is closed — relevant past knowledge is automatically injected at session start and searchable on demand
**Depends on**: Phase 3
**Requirements**: RETR-01, RETR-02, RETR-03, RETR-04
**Success Criteria** (what must be TRUE):
  1. At the start of a new Claude Code session, the SessionStart hook queries ChromaDB and injects relevant context into the conversation automatically
  2. The injected context is hard-capped at 2,000 tokens regardless of how large the knowledge base has grown
  3. The hook outputs valid `hookSpecificOutput.additionalContext` JSON to stdout — Claude Code accepts it without error
  4. Running `thehook recall "how do we handle auth"` returns the most relevant stored knowledge matching the natural language query, printed to the terminal
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Setup | 2/2 | Complete   | 2026-02-23 |
| 2. Capture | 3/3 | Complete   | 2026-02-23 |
| 3. Storage | 0/2 | Not started | - |
| 4. Retrieval | 0/TBD | Not started | - |
