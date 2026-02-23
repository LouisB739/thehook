# Architecture Research

**Domain:** Local RAG memory system for AI coding agents (Python CLI)
**Researched:** 2026-02-23
**Confidence:** HIGH (Claude Code hooks: official docs verified; ChromaDB: official docs verified; JSONL format: multiple community sources verified)

## Standard Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    Claude Code / Cursor IDE                       │
│  SessionEnd fires → stdin JSON (session_id, transcript_path)     │
│  SessionStart fires → stdout JSON (additionalContext injected)    │
└───────────────────────────┬─────────────────────────────────────┘
                            │ hooks (shell command)
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                        TheHook CLI                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │  Hook Runner │  │  Capture Cmd │  │   Retrieve Cmd       │   │
│  │  (entrypoint)│  │  (SessionEnd)│  │   (SessionStart)     │   │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘   │
│         │                 │                      │               │
│         └─────────────────┴──────────────────────┘               │
│                           │                                      │
│  ┌────────────────────────▼─────────────────────────────────┐   │
│  │                  Core Services Layer                       │   │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────┐             │   │
│  │  │ Transcript│  │Extraction │  │ Retrieval │             │   │
│  │  │  Parser   │  │  Engine   │  │  Engine   │             │   │
│  │  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘             │   │
│  └────────┼──────────────┼──────────────┼────────────────────┘   │
│           │              │              │                        │
│  ┌────────▼──────────────▼──────────────▼────────────────────┐   │
│  │                  Storage Layer                              │   │
│  │  ┌─────────────────────────┐  ┌──────────────────────┐    │   │
│  │  │  Markdown Store         │  │  ChromaDB Index       │    │   │
│  │  │  .thehook/sessions/     │  │  .thehook/chroma/     │    │   │
│  │  │  .thehook/knowledge/    │  │  (disposable cache)   │    │   │
│  │  └─────────────────────────┘  └──────────────────────┘    │   │
│  └────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| Hook Runner | Entrypoint invoked by Claude Code/Cursor. Reads stdin JSON, routes to Capture or Retrieve based on event. | Python CLI command (`thehook capture`, `thehook retrieve`) |
| Transcript Parser | Reads the JSONL transcript file at `transcript_path`. Extracts human-readable conversation text from typed message records. | Python JSON parser over JSONL lines; filters `type: user` and `type: assistant` entries |
| Extraction Engine | Calls headless LLM CLI (`claude -p`) with extraction prompt to pull conventions, decisions, and summaries from conversation text. | Subprocess call with prompt piped to stdin; parses structured output (markdown) |
| Retrieval Engine | Embeds the current session's initial context query, queries ChromaDB for top-k similar chunks, formats context for injection. | ChromaDB query with `n_results=5`; formats as markdown context block for stdout |
| Markdown Store | Source-of-truth files. One file per session summary (`sessions/`), cumulative knowledge files (`knowledge/`). ChromaDB is rebuilt from these files via `reindex`. | Plain `.md` files written by Extraction Engine; human-readable and git-committable |
| ChromaDB Index | Vector search index over markdown chunks. Disposable — rebuilt from Markdown Store at any time. | `chromadb.PersistentClient(path=".thehook/chroma")` with default embedding function |
| Consolidation Engine | Merges N session files into a cumulative knowledge document. Triggered every N captures. | LLM call merging existing knowledge + new sessions into updated knowledge file |
| CLI Commands | User-facing interface: `init`, `status`, `recall`, `reindex`. | Click or argparse CLI commands |

## Recommended Project Structure

```
thehook/
├── thehook/                  # main package
│   ├── __init__.py
│   ├── cli.py                # Click CLI entrypoint (all commands)
│   ├── hooks/
│   │   ├── capture.py        # SessionEnd handler: parse + extract + store
│   │   └── retrieve.py       # SessionStart handler: query + inject context
│   ├── core/
│   │   ├── transcript.py     # JSONL parser, conversation text extraction
│   │   ├── extractor.py      # Headless LLM calls (claude -p / cursor-agent -p)
│   │   ├── store.py          # Markdown file read/write (.thehook/sessions/, knowledge/)
│   │   ├── indexer.py        # ChromaDB client wrapper, upsert, query, reindex
│   │   └── consolidator.py   # N-session merging logic
│   ├── config.py             # YAML config loading (.thehook/config.yaml)
│   └── detector.py           # Detect which CLI is available (claude vs cursor-agent)
├── tests/
│   ├── fixtures/             # Sample JSONL transcripts, markdown files
│   ├── test_transcript.py
│   ├── test_extractor.py
│   ├── test_indexer.py
│   └── test_retrieval.py
├── pyproject.toml            # pip-installable package
└── README.md
```

### Structure Rationale

- **hooks/:** Thin entry points for lifecycle events. Each is a one-function module that orchestrates core services. No business logic here.
- **core/:** All business logic. Each module has a single concern. Easy to test in isolation with fixture files.
- **cli.py:** All Click commands in one file initially. Split if it grows past 300 lines.
- **config.py:** All config access through one module. Prevents config-reading scattered across codebase.
- **detector.py:** Isolated LLM CLI detection logic. When Cursor fixes stability issues, this module is the only change point.

## Architectural Patterns

### Pattern 1: Dual-Write (Markdown Primary, ChromaDB Secondary)

**What:** Every knowledge unit is written to a `.md` file first, then upserted to ChromaDB. ChromaDB is never the source of truth.
**When to use:** Always. This is the core invariant of TheHook.
**Trade-offs:** Slightly slower writes (two stores). Enormously valuable: `thehook reindex` can reconstruct the entire search index from markdown files alone. No data loss if ChromaDB corrupts.

**Example:**
```python
# store.py
def save_session(session_id: str, content: str, base_path: Path) -> Path:
    path = base_path / "sessions" / f"{session_id}.md"
    path.write_text(content)
    return path

# indexer.py
def upsert_document(doc_path: Path, collection: chromadb.Collection) -> None:
    chunks = chunk_markdown(doc_path.read_text())
    for i, chunk in enumerate(chunks):
        collection.upsert(
            ids=[f"{doc_path.stem}_{i}"],
            documents=[chunk],
            metadatas=[{"source": str(doc_path), "session": doc_path.stem}]
        )
```

### Pattern 2: Subprocess LLM Extraction with Timeout Guard

**What:** Call `claude -p` as a subprocess, pipe the transcript + extraction prompt to stdin, capture stdout as structured markdown. Always enforce timeout <= 100s (SessionEnd hook has 120s total budget).
**When to use:** Extraction Engine and Consolidation Engine only.
**Trade-offs:** Adds ~10-30s latency per session capture. Unavoidable — this is the zero-API-key design requirement.

**Example:**
```python
# extractor.py
import subprocess

EXTRACTION_PROMPT = """
Analyze this coding session transcript and extract:
1. SUMMARY: 2-3 sentence session summary
2. CONVENTIONS: Any coding conventions or style decisions
3. DECISIONS: Architecture or approach decisions made
4. GOTCHAS: Bugs found, traps to avoid

Return as markdown with ## headings.
"""

def extract(transcript_text: str, timeout: int = 90) -> str:
    prompt = EXTRACTION_PROMPT + "\n\n---\n" + transcript_text
    result = subprocess.run(
        ["claude", "-p", prompt],
        capture_output=True, text=True, timeout=timeout
    )
    if result.returncode != 0:
        raise RuntimeError(f"claude -p failed: {result.stderr}")
    return result.stdout
```

### Pattern 3: Metadata-Rich ChromaDB Upserts

**What:** Every ChromaDB document includes metadata: `source` (file path), `session_id`, `doc_type` (`session` vs `knowledge`), `project` (cwd), `timestamp`. This enables filtered retrieval.
**When to use:** All upserts.
**Trade-offs:** Slightly larger index. Enables future features (project isolation, date-range filtering) without schema changes.

**Example:**
```python
collection.upsert(
    ids=[chunk_id],
    documents=[chunk_text],
    metadatas=[{
        "source": str(doc_path),
        "session_id": session_id,
        "doc_type": "session",  # or "knowledge"
        "project": cwd,
        "timestamp": iso_timestamp,
    }]
)
```

### Pattern 4: SessionStart Context Injection via stdout JSON

**What:** The retrieve hook writes a JSON object to stdout. Claude Code reads `additionalContext` from `hookSpecificOutput` and prepends it to Claude's context window before the user's first prompt.
**When to use:** SessionStart retrieve hook only.
**Trade-offs:** Context injection is transparent to the user. Keep injected context under 2000 tokens to avoid eating context window.

**Example:**
```python
# hooks/retrieve.py
import json, sys

def run(hook_input: dict) -> None:
    context = retrieve_relevant_context(hook_input["cwd"])
    output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context
        }
    }
    print(json.dumps(output))
    sys.exit(0)
```

## Data Flow

### Capture Flow (SessionEnd)

```
Claude Code SessionEnd fires
    ↓ stdin JSON: {session_id, transcript_path, cwd, ...}
Hook Runner (thehook capture)
    ↓
Transcript Parser
    reads transcript_path (JSONL file at ~/.claude/projects/.../session.jsonl)
    filters lines where type == "user" | "assistant"
    extracts text content from message.content blocks
    concatenates into plain conversation text
    ↓
Extraction Engine
    builds prompt: EXTRACTION_PROMPT + conversation_text
    subprocess: echo "$prompt" | claude -p (timeout 90s)
    returns structured markdown with SUMMARY / CONVENTIONS / DECISIONS / GOTCHAS
    ↓
Markdown Store
    writes .thehook/sessions/{session_id}.md
    ↓
ChromaDB Indexer
    chunks markdown into 500-token chunks
    upserts to "thehook" collection with metadata
    ↓
Consolidation Check
    if session_count % N == 0:
        → Consolidator merges last N sessions + existing knowledge
        → writes .thehook/knowledge/project-knowledge.md
        → reindexes knowledge file in ChromaDB
    ↓
exit 0 (Claude Code session terminates normally)
```

### Retrieve Flow (SessionStart)

```
Claude Code SessionStart fires
    ↓ stdin JSON: {session_id, transcript_path, cwd, source: "startup", ...}
Hook Runner (thehook retrieve)
    ↓
Retrieval Engine
    reads .thehook/config.yaml for retrieval settings
    embeds query: "{project_name} conventions decisions recent context"
    chromadb.query(query_texts=[query], n_results=5, where={"project": cwd})
    formats top-k chunks into context markdown block
    ↓
stdout JSON:
    {hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: "..."}}
    ↓
Claude Code injects additionalContext into Claude's context window
    ↓ Claude's first response has full project memory
```

### Manual Recall Flow (thehook recall "query")

```
User: thehook recall "authentication approach"
    ↓
Retrieval Engine
    same query flow as SessionStart retrieve
    prints formatted results to terminal (not JSON)
```

### Reindex Flow (thehook reindex)

```
User: thehook reindex
    ↓
Indexer
    deletes .thehook/chroma/ directory
    creates fresh PersistentClient
    walks .thehook/sessions/*.md + .thehook/knowledge/*.md
    upserts all documents with metadata
    prints summary: "Reindexed N documents"
```

## Claude Code Hooks: Verified Architecture Details

**HIGH confidence — sourced from official Claude Code hooks reference docs.**

### SessionEnd hook input (stdin JSON):
```json
{
  "session_id": "abc123",
  "transcript_path": "/Users/.../.claude/projects/.../transcript.jsonl",
  "cwd": "/Users/.../my-project",
  "permission_mode": "default",
  "hook_event_name": "SessionEnd",
  "reason": "other"
}
```

**Key facts:**
- `transcript_path` points to a JSONL file (one JSON object per line)
- Default hook timeout is 600 seconds for command hooks (not 120s — the 120s figure was incorrect in project context)
- SessionEnd **cannot block** session termination — it is side-effects only
- exit 2 on SessionEnd only shows stderr to user, does not block

### SessionStart hook output (stdout JSON):
```json
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "## Project Memory\n..."
  }
}
```

**Key facts:**
- stdout is added as Claude's context
- `additionalContext` is the structured field for discrete context injection
- SessionStart fires on `startup`, `resume`, `clear`, and `compact` — use matcher `startup` to only inject on new sessions
- SessionStart **only supports `type: "command"` hooks** (not prompt or agent hooks)

### Transcript JSONL format:
```jsonl
{"type":"user","message":{"role":"user","content":"Hello"},"timestamp":"2025-06-02T18:46:59.937Z"}
{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Hi!"}]},"timestamp":"..."}
```

**Key facts:**
- Each line is a typed record: `user`, `assistant`, tool calls, tool results, summaries, git snapshots
- `content` can be a string (user) or an array of content blocks (assistant)
- Text blocks have `{"type": "text", "text": "..."}` structure
- Tool use blocks have `{"type": "tool_use", "name": "...", "input": {...}}` structure
- Transcript parser must handle both string and array content shapes

## Anti-Patterns

### Anti-Pattern 1: Blocking SessionEnd with Heavy Processing

**What people do:** Run the full extraction + embedding pipeline synchronously inside SessionEnd, taking 30-90 seconds.
**Why it's wrong:** While default timeout is 600s (not 120s), long blocking hooks degrade UX — the user sees Claude Code "hanging" on exit. If the LLM CLI hangs (known Cursor bug), the session never closes cleanly.
**Do this instead:** Respect a self-imposed 90s timeout on the `claude -p` subprocess. Surface errors gracefully — write a "capture failed" marker file and let the session close. Recovery can happen via `thehook reindex`.

### Anti-Pattern 2: Treating ChromaDB as Source of Truth

**What people do:** Only store knowledge in ChromaDB; delete or not write markdown files.
**Why it's wrong:** ChromaDB's local SQLite/DuckDB backing store can corrupt. Upgrading ChromaDB can break the index schema. No human-readable audit trail.
**Do this instead:** Markdown files are always primary. ChromaDB is always derived. `thehook reindex` rebuilds from markdown.

### Anti-Pattern 3: Single Monolithic ChromaDB Collection Without Metadata

**What people do:** Upsert all documents without metadata, query with no filters.
**Why it's wrong:** Retrieval mixes context from different projects. No way to filter by recency, doc_type, or project. `reindex` can't selectively rebuild.
**Do this instead:** Always include `project`, `doc_type`, `timestamp`, `session_id` in metadata. Use `where` filters in queries.

### Anti-Pattern 4: Re-parsing Transcript on Every SessionStart

**What people do:** Read the previous session's transcript on SessionStart, re-extract knowledge before injecting.
**Why it's wrong:** SessionStart blocks Claude's first response. Re-extraction adds 30-90s before the user can interact.
**Do this instead:** Extraction happens at SessionEnd (async to user experience). SessionStart only queries the already-indexed ChromaDB — this is fast (<1s).

### Anti-Pattern 5: Injecting All Stored Context at SessionStart

**What people do:** Dump all knowledge files into the context at SessionStart.
**Why it's wrong:** Rapidly consumes context window. Large projects accumulate many sessions; injecting all of it defeats the purpose of RAG.
**Do this instead:** Query ChromaDB for top-5 semantically relevant chunks only. Cap injected context at ~1500 tokens. Trust the embedding search to surface what matters.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Claude Code | Hooks config in `~/.claude/settings.json` or `.claude/settings.json`; stdin/stdout JSON protocol | `thehook init` writes the hook config; SessionStart and SessionEnd events |
| `claude -p` CLI | Subprocess call with prompt on stdin; stdout is LLM response | Zero API key needed; uses existing Claude subscription; 90s self-imposed timeout |
| `cursor-agent -p` CLI | Same subprocess pattern as `claude -p` | Known stability/hang issues; wrap in timeout; surface errors cleanly |
| ChromaDB | `chromadb.PersistentClient(path=".thehook/chroma")` | Local SQLite-backed; no server needed; default embedding function (sentence-transformers) |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| CLI commands ↔ Core services | Direct Python function calls | No queues or async; CLI is synchronous |
| Transcript Parser → Extraction Engine | Plain text string (concatenated conversation) | Parser is pure function: `parse(path) -> str` |
| Extraction Engine → Markdown Store | Markdown string | Extractor returns str; store writes it |
| Markdown Store → ChromaDB Indexer | File path | Indexer reads from path, not from memory; enables reindex |
| Retrieval Engine → CLI / stdout | Formatted string | retrieve() returns str; CLI decides whether to print (recall) or JSON-encode (hook) |

## Suggested Build Order

Dependencies flow bottom-up: storage must exist before services can write to it; services must exist before hooks can orchestrate them; hooks must work before CLI commands that wrap them.

```
1. Storage Layer
   → config.py (read .thehook/config.yaml)
   → store.py (markdown read/write)
   → indexer.py (ChromaDB client, upsert, query, reindex)

2. Core Services
   → transcript.py (JSONL parser) — depends on nothing
   → detector.py (find claude/cursor-agent binary) — depends on nothing
   → extractor.py (subprocess LLM call) — depends on detector
   → consolidator.py (merge sessions) — depends on store + extractor
   → retrieval engine in indexer.py (query ChromaDB) — depends on indexer

3. Hook Entry Points
   → hooks/capture.py — depends on transcript + extractor + store + indexer
   → hooks/retrieve.py — depends on indexer (retrieval)

4. CLI Commands
   → cli.py init — depends on config + hooks config writer
   → cli.py status — depends on store + indexer
   → cli.py recall — depends on indexer (retrieval)
   → cli.py reindex — depends on store + indexer

5. Packaging
   → pyproject.toml with console_scripts entry point
   → thehook init writes hook config to ~/.claude/settings.json
```

## Scaling Considerations

This is a single-developer local tool. Scaling targets are different from server systems.

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 1-50 sessions | Default ChromaDB with sentence-transformers embeddings; single collection; no chunking complexity needed |
| 50-500 sessions | Consolidation becomes critical — without it, session files bloat retrieval noise. Tune N (sessions per consolidation) based on project velocity |
| 500+ sessions | ChromaDB query latency stays <100ms at this scale (local SQLite). Main concern is context quality: consolidation must produce tight, specific knowledge files or recall degrades |

### Scaling Priorities

1. **First bottleneck: extraction quality degrades.** As sessions accumulate, extraction prompts need to be more specific about what to extract vs what to skip (small talk, dead ends). Solution: improve extraction prompt, not architecture.
2. **Second bottleneck: ChromaDB recall precision drops.** More documents = more noise in top-k. Solution: metadata filtering by `doc_type: "knowledge"` (consolidated) vs `doc_type: "session"` (raw), or increasing consolidation frequency.

## Sources

- Claude Code Hooks Reference (official, verified 2026-02-23): https://code.claude.com/docs/en/hooks
- Claude Code transcript JSONL format (community-verified): https://simonwillison.net/2025/Dec/25/claude-code-transcripts/
- ChromaDB persistent client (official): https://www.trychroma.com/
- ChromaDB metadata filtering (official cookbook): https://cookbook.chromadb.dev/core/collections/
- AI agent memory architecture patterns: https://redis.io/blog/ai-agent-memory-stateful-systems/
- Local RAG architecture with ChromaDB: https://blog.gopenai.com/building-a-fully-local-rag-system-with-lm-studio-and-chromadb-197b025de54f

---
*Architecture research for: Local RAG memory system for AI coding agents (TheHook)*
*Researched: 2026-02-23*
