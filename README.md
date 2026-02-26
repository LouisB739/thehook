# TheHook

> Self-improving long-term memory for AI coding agents.

TheHook gives your AI coding assistant (Claude Code, Cursor) a **persistent memory** across sessions. It automatically captures what you learn, decides, and build together — then brings back the right context when you need it.

**The problem:** Every new session starts from zero. Your agent forgets the conventions you agreed on, the bugs you already solved, the architecture decisions you made. You end up repeating yourself.

**The fix:** TheHook hooks into your agent's lifecycle. End of session: it extracts the important stuff. Start of session: it injects what's relevant. You also get a manual `/save` and `recall` for full control.

## How it works

```
Session ends
  → TheHook captures the transcript
  → LLM extracts: summary, conventions, decisions, gotchas
  → Saves as markdown + indexes in ChromaDB

Session starts
  → TheHook queries the index for relevant context
  → Injects it into the new session automatically

You can also:
  → /save to manually store knowledge
  → thehook recall "..." to search your memory
```

Markdown files are the source of truth. ChromaDB is just a search index — disposable, rebuildable anytime. You can read, edit, or delete any memory by hand.

## Quick start

### 1. Install

```bash
# With pip
pip install thehook

# With uv (recommended)
uv pip install thehook

# From source
git clone https://github.com/LouisB739/thehook.git
cd thehook
pip install -e .
```

Requires **Python 3.11+**.

### 2. Initialize in your project

```bash
cd your-project
thehook init
```

This creates:

```
your-project/
├── .thehook/
│   ├── sessions/     # Captured knowledge (markdown files) — indexed in ChromaDB, shared via git
│   ├── knowledge/    # Optional consolidated docs (not indexed by default; for future use)
│   ├── chromadb/     # Search index (local only, gitignored)
│   └── .gitignore    # Excludes local runtime artifacts
├── .claude/
│   └── settings.local.json   # Claude Code hooks (auto-configured)
└── .cursor/
    └── hooks.json             # Cursor hooks (auto-configured)
```

That's it. TheHook is now active. It injects memory at session start and before each prompt, captures lightweight memory during long sessions, and captures full structured memory at session end.

### Team usage

Knowledge is **shared by default**. Session files in `.thehook/sessions/` are committed to git, so the whole team benefits from captured conventions, decisions, and gotchas. The ChromaDB index is local-only (gitignored) — each developer rebuilds it automatically on first use, or manually with `thehook reindex`.

### 3. Add `/save` to your CLAUDE.md (recommended)

Add this to your project's `CLAUDE.md` so you can manually save knowledge mid-session:

```markdown
## /save

When the user says `/save`, extract knowledge from the current conversation and save it:

1. Review the conversation and extract:
   - **Summary**: What was accomplished
   - **Conventions**: Coding patterns, naming standards, structural rules established
   - **Decisions**: Architecture choices, technology selections, and reasoning
   - **Gotchas**: Non-obvious pitfalls, edge cases, or bugs discovered

2. Pipe the extracted markdown to `thehook save`:

\```bash
cat << 'EOF' | thehook save
## Summary
<what was accomplished>

## Conventions
<patterns and rules established>

## Decisions
<choices made and why>

## Gotchas
<pitfalls and edge cases discovered>
EOF
\```

3. Confirm to the user what was saved.

Only include sections that have meaningful content. Skip empty sections.
```

## Commands

### `thehook init`

Initialize TheHook in your project. Creates the `.thehook/` directory and registers hooks for Claude Code and Cursor. Safe to run multiple times (idempotent).

```bash
thehook init
thehook init --path /path/to/project
```

### `thehook recall`

Search your project's memory. Finds the most relevant stored knowledge using semantic search.

```bash
thehook recall "how did we set up authentication"
thehook recall "database migration strategy"
thehook recall "naming conventions" --path /path/to/project
```

### `thehook save`

Manually save knowledge. Reads markdown from stdin, stores it as a session file, and indexes it.

```bash
cat << 'EOF' | thehook save
## Summary
Implemented JWT auth with refresh token rotation.

## Decisions
- Chose jose over jsonwebtoken for better security defaults
- 15-min access tokens, 7-day refresh tokens

## Gotchas
- Token refresh must happen BEFORE expiry, not after
EOF
```

### `thehook status`

Show how many session/knowledge files you have and how many documents are in the ChromaDB index. Use this to verify that retrieval is ready.

```bash
thehook status
# sessions:   48 .md files
# knowledge:  0 .md files (not indexed by default)
# chromadb:   48 documents indexed
# Retrieval:  run 'thehook recall "your query"' to test.
```

If you have sessions but `chromadb: 0`, run `thehook reindex`.

### `thehook reindex`

Rebuild the ChromaDB index from scratch. Useful if you manually edited or deleted session files.

```bash
thehook reindex
thehook reindex --path /path/to/project
```

### `thehook capture`

Called automatically by the SessionEnd hook. Reads the session transcript from stdin, runs full LLM extraction, and saves the result. You don't need to call this manually.

### `thehook capture-lite`

Called automatically by Stop/PreCompact hooks. Runs a faster, shorter extraction intended for in-session memory updates. It is throttled and deduplicated to avoid noisy writes.

### `thehook retrieve`

Called automatically by SessionStart and UserPromptSubmit hooks. Queries the index and outputs context for the agent. You don't need to call this manually.

## Configuration

Create a `thehook.yaml` at your project root to customize behavior:

```yaml
# Maximum tokens of context to inject at session start (default: 2000)
token_budget: 2000

# Maximum number of documents returned by retrieval (default: 5)
retrieval_n_results: 5

# Only retrieve sessions from the last N days (default: 0 = disabled)
retrieval_recency_days: 0

# If recency filter returns nothing, retry globally (default: true)
retrieval_recency_fallback_global: true

# Number of sessions before auto-consolidation (default: 5)
consolidation_threshold: 5

# Enable in-session lightweight memory capture (default: true)
intermediate_capture_enabled: true

# Timeout for lightweight capture extraction (default: 20)
intermediate_capture_timeout_seconds: 20

# Minimum seconds between lightweight captures (default: 180)
intermediate_capture_min_interval_seconds: 180

# Transcript character budget for lightweight capture (default: 12000)
intermediate_capture_max_transcript_chars: 12000

# Which hooks are active (default: all configured hooks)
active_hooks:
  - SessionEnd
  - SessionStart
  - UserPromptSubmit
  - Stop
  - PreCompact
```

All settings are optional — defaults are applied for anything you don't specify.

## What gets captured

Each session is saved as a markdown file in `.thehook/sessions/` with this structure:

```markdown
---
session_id: abc123def456
timestamp: 2026-02-24T10:00:00+00:00
transcript_path: /path/to/transcript.jsonl
---

## SUMMARY
Implemented the user authentication system with JWT tokens.

## CONVENTIONS
- All auth logic lives in the auth/ module
- Tests colocated in __tests__/ directories
- Input validation with Zod at route boundaries

## DECISIONS
- Chose JWT over sessions for statelessness
- jose library over jsonwebtoken for security defaults

## GOTCHAS
- Clock skew between servers can invalidate tokens
- Must refresh tokens BEFORE they expire
```

These files are plain markdown. You can read, edit, or delete them freely. Run `thehook reindex` after manual changes to update the search index.

## Supported agents

| Agent | Final Capture (SessionEnd) | Intermediate Capture (Stop/PreCompact) | Retrieval (SessionStart/UserPrompt) | Manual save/recall |
|-------|-----------------------------|---------------------------------------|-------------------------------------|-------------------|
| Claude Code | Auto-configured | Auto-configured | Auto-configured | Via CLAUDE.md |
| Cursor | Auto-configured | Auto-configured | Auto-configured | Via rules |

Both agents are configured automatically by `thehook init`. The hooks call `thehook capture`, `thehook capture-lite`, and `thehook retrieve` behind the scenes.

## Architecture

```
┌─────────────────────────────────────┐
│  CAPTURE (Stop/PreCompact + End)    │
│  - capture-lite during session      │
│  - capture full at SessionEnd       │
└──────────────┬──────────────────────┘
               │ .thehook/sessions/*.md
┌──────────────▼──────────────────────┐
│         INDEXATION                   │
│  markdown = source of truth         │
│  ChromaDB = disposable search index │
└──────────────┬──────────────────────┘
               │ semantic search
┌──────────────▼──────────────────────┐
│         RETRIEVAL                    │
│  Auto: SessionStart + UserPrompt    │
│  Manual: thehook recall "..."       │
└─────────────────────────────────────┘
```

**Key design principles:**

- **Markdown is truth** — ChromaDB can be deleted and rebuilt anytime with `thehook reindex`
- **Hooks never crash** — All hook code is wrapped in try/except. A failure in TheHook never breaks your session
- **No server needed** — ChromaDB runs as a local embedded database
- **Embedding** — ChromaDB uses its default: **all-MiniLM-L6-v2** (ONNX). No API key; model is cached locally (e.g. `~/.cache/chroma/`).
- **Fast startup** — Heavy dependencies (ChromaDB) are lazy-imported to keep CLI snappy

## Troubleshooting

**ChromaDB permission error (`~/.cache/chroma/` owned by root)**

```bash
sudo chown -R $(whoami) ~/.cache/chroma/
```

**Empty results from `recall`**

Make sure you've had at least one session captured, or used `thehook save` to store knowledge. Check that `.thehook/sessions/` contains `.md` files.

**Index out of sync after manual edits**

```bash
thehook reindex
```

**Hook not firing**

Verify the hooks are registered:
- Claude Code: check `.claude/settings.local.json`
- Cursor: check `.cursor/hooks.json`

Re-run `thehook init` if needed.

## Development

```bash
git clone https://github.com/LouisB739/thehook.git
cd thehook
pip install -e ".[dev]"
pytest tests/ -v
```

## License

MIT
