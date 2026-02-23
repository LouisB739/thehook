# TheHook — MVP Design

> Self-improving long-term memory for AI coding agents (Claude Code & Cursor)

## Problem

1. **Context loss between sessions** — The agent forgets everything at each new conversation
2. **Noisy memory files** — Solutions like `CLAUDE.md` or Cursor rules become an unusable catch-all
3. **No experience capitalization** — Patterns, errors, and solutions discovered during dev are never captured in a reusable way

## Target Users

- Primary: The team (Claude Code + Cursor users)
- Secondary: Any developer using AI coding assistants (public open-source project)

## Architecture

Three-layer pipeline: Capture → Indexation → Retrieval

```
┌─────────────────────────────────────┐
│         CAPTURE (hooks)             │
│  conversation_end → LLM summary    │
│  extraction: conventions, ADRs     │
└──────────────┬──────────────────────┘
               │ markdown files
┌──────────────▼──────────────────────┐
│         INDEXATION                   │
│  .thehook/knowledges/*.md (truth)   │
│  ChromaDB local (search index)      │
│  Auto-consolidation every N sessions│
└──────────────┬──────────────────────┘
               │ retrieval
┌──────────────▼──────────────────────┐
│         RETRIEVAL                    │
│  Auto: hook conversation_start      │
│  Manual: /recall command            │
│  Configurable per user              │
└─────────────────────────────────────┘
```

### Key Principle

Markdown is the source of truth. ChromaDB is a disposable search index, rebuilt from `.md` files. A dev can always read, edit, or delete a knowledge by hand.

## Capture

### Trigger

The `conversation_end` hook (Claude Code) or Cursor equivalent triggers the capture pipeline.

### Process

1. Retrieve the conversation transcript
2. Launch the detected CLI (`claude -p` or `cursor-agent -p`) with a structured prompt
3. The LLM produces 3 extractions in a single pass:
   - **Session summary**: what was done, problems encountered, decisions made
   - **Conventions detected**: project patterns and practices
   - **Architecture decisions**: ADRs with context, alternatives, rationale

### Output Format

```markdown
## Session Summary
- **Date**: 2026-02-23
- **What was done**: Implemented JWT auth system
- **Problems encountered**: Conflict between Express middleware and...
- **Decisions made**: Chose jose over jsonwebtoken because...

## Conventions Detected
- `[convention]` Tests colocated in `__tests__/` next to source files
- `[convention]` Input validation with Zod at route entry

## Architecture Decisions
- `[ADR]` JWT with refresh token rotation over server sessions
  - **Context**: Stateless app, multi-instance deployment
  - **Alternatives considered**: Redis sessions, httpOnly cookies
  - **Rationale**: Operational simplicity, no shared state
```

### Storage

Each session produces a file: `.thehook/sessions/YYYY-MM-DD-HHmm-<slug>.md`

### Error Handling

If the CLI hangs or fails (60s timeout), the raw transcript is saved to `.thehook/sessions/failed/` and a warning is shown to the dev at next startup.

## Indexation & Consolidation

### ChromaDB Indexation

After each capture, the script indexes the new session into ChromaDB:

- Each section (summary, convention, ADR) becomes a **separate document** in ChromaDB
- Metadata: `type` (summary|convention|adr), `date`, `project`, `tags`
- Embeddings generated via the CLI (`claude -p`) — no separate embedding model for MVP

### File Structure

```
.thehook/
├── config.yaml              # User config
├── sessions/                # Raw session summaries
│   ├── 2026-02-23-1430-auth-jwt.md
│   └── failed/              # Unprocessed transcripts
├── knowledges/              # Consolidated memory
│   ├── conventions.md       # Project conventions
│   ├── architecture.md      # Cumulated arch decisions
│   └── history.md           # Condensed project summary
└── .chromadb/               # Search index (disposable)
```

### Auto-Consolidation

Triggered **every N sessions** (configurable, default: 5):

1. Read unconsolidated sessions + existing knowledges
2. LLM call merges: deduplicates conventions, updates ADRs if decisions changed, condenses summaries into history
3. Write updated knowledges
4. Re-index ChromaDB from markdowns

Raw sessions are **kept** (archive), but `knowledges/` is authoritative for retrieval.

## Retrieval

### Automatic (conversation_start)

The `conversation_start` hook runs the retrieval script:

1. Detect current context (working directory, recently modified files, git branch)
2. Search ChromaDB for most relevant knowledges
3. Inject result into a context file (`.thehook/context.md` regenerated at each start)

### Injected Context Example

```markdown
# TheHook — Project Memory

## Active Conventions
- Tests colocated in __tests__/
- Zod validation at route entry
- Migration naming: YYYYMMDD_description.sql

## Recent Architecture Decisions
- JWT with refresh token rotation (2026-02-20)
- PostgreSQL with Drizzle ORM (2026-02-18)

## Relevant History
- Auth system is complete and tested
- Migration from Express to Hono in progress
```

### Manual Retrieval (`/recall`)

Dev can search memory with a natural language query:

```
/recall how did we configure the auth system?
```

The script searches ChromaDB, retrieves relevant documents (raw sessions + knowledges), and returns the context.

### Configuration (`.thehook/config.yaml`)

```yaml
retrieval:
  auto_inject: true          # false to disable auto-inject
  max_context_lines: 50      # limit injected context size
  include:
    - conventions
    - architecture
    - history
consolidation:
  every_n_sessions: 5
  cli: auto                  # auto | claude | cursor-agent
```

## LLM Engine

- Zero API key config — TheHook detects the available CLI (`claude` or `cursor-agent`)
- Uses headless mode (`claude -p` / `cursor-agent -p`)
- If the CLI fails or hangs, the error is surfaced to the user
- `cli: auto` in config detects environment; can be overridden manually

## MVP Scope

### IN

- Capture hook: script triggered at `conversation_end`, summary via headless CLI
- Markdown storage: raw sessions + consolidated knowledges in `.thehook/`
- ChromaDB indexation: local index, rebuilt from markdowns
- Auto retrieval: injection at `conversation_start` via context file
- Manual retrieval: `/recall` command to search memory
- Auto-consolidation: merge every N sessions
- YAML config: retrieval and consolidation settings
- Claude Code + Cursor support: auto-detection of available CLI
- Install script: `thehook init` to set up hooks and directory

### OUT

- Web interface / dashboard
- Cross-project memory (global)
- Dedicated embedding model
- Knowledge scoring / decay
- Multi-user / collaboration
- Cloud sync

## Tech Stack

| Component | Choice |
|-----------|--------|
| Language | **Python** — ChromaDB is native Python, solid ML ecosystem |
| Storage | **Markdown** (truth) + **ChromaDB** (index) |
| LLM | **Detected CLI** (`claude -p` / `cursor-agent -p`) |
| Config | **YAML** |
| Distribution | **pip install thehook** (PyPI) |
| Hooks | **Shell scripts** generated by `thehook init` |

## CLI Commands (MVP)

```bash
thehook init          # Setup hooks + .thehook/ directory
thehook recall "..."  # Manual search
thehook consolidate   # Force a consolidation
thehook reindex       # Rebuild ChromaDB from .md files
thehook status        # Memory state (nb sessions, knowledges, etc.)
```
