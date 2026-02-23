# Pitfalls Research

**Domain:** AI coding agent memory / local RAG CLI tool (Python, ChromaDB, Claude Code hooks)
**Researched:** 2026-02-23
**Confidence:** HIGH (Claude Code hooks: official docs verified; ChromaDB: GitHub issues + official cookbook; subprocess: Python tracker + official docs; RAG patterns: multiple credible sources)

---

## Critical Pitfalls

### Pitfall 1: SessionEnd Hook Races the 120s Timeout

**What goes wrong:**
The SessionEnd hook has a hard 120-second timeout. Inside that window, TheHook must: parse the transcript, call `claude -p` to summarize (which itself is an LLM call), write markdown, and index into ChromaDB. In practice, `claude -p` alone can take 30-90 seconds on a large transcript. If the hook reaches 120s, the process is killed mid-write, leaving truncated markdown files and a partially-updated ChromaDB index.

**Why it happens:**
Developers test with short transcripts where `claude -p` finishes in 10s, then deploy against real long sessions (100+ turns, 50k+ tokens). The summarization LLM call time is not constant — it scales with input size. Additionally, `claude -p` may queue behind other Claude Code processes.

**How to avoid:**
- Budget the 120s explicitly: transcript read (~1s) + `claude -p` call (budget max 90s, enforce with `subprocess timeout=85`) + markdown write (~1s) + ChromaDB index (~2s) = 94s comfortable ceiling.
- Use `async: true` on the SessionEnd hook if capture can be deferred — but note async hooks cannot read the transcript at session end reliably (it may be finalized after the hook fires).
- Add a hard subprocess timeout of 85 seconds on the `claude -p` call with graceful degradation: if timeout fires, write a stub summary ("Session captured but summarization timed out") and index the raw session metadata (date, project, session_id) instead. Never block on a hard failure.
- Test with transcripts that are realistically large (300+ turns).

**Warning signs:**
- Hook script exits with non-zero status (visible in Claude Code debug mode `Ctrl+O`).
- Markdown files exist with 0 bytes or incomplete content (cut off mid-sentence).
- ChromaDB index has entries that point to missing/empty markdown files.
- Hook consistently completes fine on short sessions but fails silently on long ones.

**Phase to address:** Phase 1 (Hook infrastructure) — build timeout budgeting and graceful degradation from day one, not as an afterthought.

---

### Pitfall 2: `claude -p` Subprocess Hanging Due to PIPE Buffer Overflow

**What goes wrong:**
When calling `claude -p` via Python's `subprocess` with `stdout=PIPE` and `stderr=PIPE`, the process hangs indefinitely if the stdout/stderr buffer fills (approximately 65KB on most systems). This happens silently — the hook process appears to be running but never returns. Since the hook timeout is at the Claude Code level (120s), the Python process may hang inside that window and prevent any output from being written.

**Why it happens:**
Python's `subprocess.run()` with `capture_output=True` and `timeout` has a known bug where the timeout cleanup itself can hang if the child process has spawned grandchildren that still hold the pipe open. `claude` is a Node.js process that spawns child processes. After the parent is killed, grandchildren may keep pipes open, causing `communicate()` to wait forever.

**How to avoid:**
- Always use `subprocess.Popen` with `proc.communicate(timeout=N)` wrapped in a try/except `TimeoutExpired`, then explicitly call `proc.kill()` followed by `proc.communicate()` to drain remaining output.
- Use `start_new_session=True` to prevent grandchild processes from inheriting the pipe handles, and use `os.killpg(os.getpgid(proc.pid), signal.SIGKILL)` to kill the entire process group on timeout.
- Avoid `shell=True` — it adds an intermediary shell process that complicates process group management.
- Set `--max-turns 3` on `claude -p` to bound how much it can do, reducing output size and execution time.

**Warning signs:**
- Hook never completes (no output files, no ChromaDB entries) even though Claude Code shows it "running."
- Hook occasionally completes for short sessions but never for sessions with verbose output.
- `ps aux` shows zombie `claude` processes after the hook timeout fires.

**Phase to address:** Phase 1 (Hook infrastructure) — subprocess wrapper must be implemented with correct process group management before any feature building.

---

### Pitfall 3: ChromaDB HNSW Index Memory Never Shrinks After Deletes

**What goes wrong:**
ChromaDB's underlying HNSW index is append-only in terms of memory: when documents are deleted (e.g., during `thehook reindex` or session expiry), the C++ HNSW index retains the allocated memory. After enough delete-add cycles (e.g., repeated reindexing), memory usage grows unbounded. On a developer's laptop running Claude Code all day, this can exhaust RAM silently.

**Why it happens:**
ChromaDB's default `allow_replace_deleted=False` means deleted entries are soft-deleted in the graph but the index structure is not compacted. The HNSW index is cached in native C++ memory with no API to release it without process restart. This is a known limitation documented in ChromaDB GitHub issues (#2594, #5843).

**How to avoid:**
- Never implement "soft-delete + reindex" patterns — instead, implement `thehook reindex` as a full collection drop + recreate from markdown source files. This is correct architecture anyway (markdown is source of truth, ChromaDB is disposable).
- During `reindex`, create a new collection, populate it, then swap the reference atomically, then delete the old collection. This prevents the unbounded growth pattern.
- Set `allow_replace_deleted=True` in ChromaDB collection metadata at creation time — this allows the HNSW graph to reuse deleted slots.
- Document and test `thehook reindex` as a first-class operation from Phase 1 (it's the recovery path for many failure modes).

**Warning signs:**
- Process RSS memory grows over days of use.
- `thehook status` shows fewer documents than expected despite recent indexing.
- ChromaDB returns stale results that should have been replaced.

**Phase to address:** Phase 2 (ChromaDB indexing) — set `allow_replace_deleted=True` at collection creation; implement reindex as drop-and-recreate from day one.

---

### Pitfall 4: Hallucinated Facts Compound in Memory ("False Memory Snowball")

**What goes wrong:**
When `claude -p` summarizes a session, it may hallucinate details: wrong function names, incorrect architecture decisions, false "we decided X" statements. These hallucinations are then indexed and injected into future sessions as authoritative context. Claude reads them as ground truth and may act on them, generating more hallucinations that get persisted. Each cycle amplifies the error.

**Why it happens:**
LLMs hallucinate confidently, especially when summarizing long transcripts with technical details. There is no feedback loop to correct false memories once written. The problem compounds because the injected context looks identical to real context — future Claude sessions cannot distinguish between accurate and hallucinated memories.

**How to avoid:**
- Store the source `transcript_path` and `session_id` in every memory document's frontmatter. This allows tracing any injected fact back to its origin session.
- Include a "Confidence" or "Needs verification" field in the summary prompt, asking `claude -p` to flag anything it is uncertain about.
- Implement `thehook status` to show what memories are being injected — this gives developers visibility into what Claude sees.
- Keep summaries factual and short (decisions, conventions, commands) rather than narrative. The longer the summary, the more surface area for hallucination.
- Design the `thehook reindex` and manual override commands early — users need a way to delete bad memories.

**Warning signs:**
- Injected context contains statements that contradict the current codebase.
- Claude references conventions or decisions that developers don't recognize.
- The same wrong statement appears in multiple session summaries.

**Phase to address:** Phase 1 (Summary prompt design) and Phase 3 (Consolidation) — prompt engineering for factual summaries must happen in Phase 1; consolidation logic must detect conflicts rather than blindly merge.

---

### Pitfall 5: Context Window Overflow From Injected Memory at SessionStart

**What goes wrong:**
At SessionStart, TheHook injects retrieved context into Claude's context window. As the memory base grows (months of sessions), more documents are retrieved and the injected context balloons. Injecting too many tokens consumes Claude's context budget before the user types anything, leaving little room for the actual coding session. Worse, Claude Code may silently truncate the injected context, discarding the most relevant information.

**Why it happens:**
RAG retrieval returns the top-K documents regardless of their combined token count. As the knowledge base grows from 10 to 500 sessions, the same K=5 retrieval might return 500 tokens initially but 8,000 tokens later as each document grows longer through consolidation. Developers don't monitor token counts of injected context.

**How to avoid:**
- Set a hard token budget for injection: inject at most N tokens at SessionStart (e.g., 2,000 tokens = about 5 concise memory documents). Truncate at the token limit, not the document limit.
- Use tiered injection: inject a compact "always-on" summary (100 tokens) plus retrieved context (up to 1,900 tokens). The always-on summary covers critical conventions; retrieved context covers project-specific detail.
- Keep individual memory documents short: cap at 500 tokens per document during generation. Reject or truncate during indexing.
- Monitor and log injection token counts during development.

**Warning signs:**
- Claude Code sessions feel "slower" to start.
- Claude references outdated information from early sessions rather than recent decisions.
- `thehook status` shows injected context growing month over month.

**Phase to address:** Phase 2 (Retrieval) — token budget must be designed into the retrieval/injection pipeline, not added later.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| ChromaDB default embeddings (no custom model) | Zero setup, works out of box | Lower semantic precision for code-specific queries | MVP — acceptable, revisit if retrieval quality complaints |
| Synchronous `claude -p` call in SessionEnd hook | Simpler code | Risk of timeout on long sessions | Never in production — always enforce subprocess timeout |
| Single ChromaDB collection for all sessions | Simpler queries | Cannot scope searches by date/project easily | MVP only if project isolation via metadata filtering works |
| Writing markdown before indexing (no atomicity) | Simple implementation | Partial state on crash (markdown written, ChromaDB not updated) | Acceptable if `thehook reindex` is available as recovery |
| No deduplication of injected context | Simpler retrieval | Same fact injected multiple times wastes tokens | Never — basic deduplication by document ID is trivial |
| Shell-level `timeout 120 thehook capture` | Easy to implement | Kills process mid-write, corrupting files | Never — internal timeout with graceful degradation is required |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Claude Code `SessionEnd` hook | Reading `transcript_path` after process exits — path may not exist or may be incomplete | Read the transcript path immediately on hook invocation from stdin JSON; the path is provided in the hook input |
| Claude Code `SessionStart` hook | Printing plain text to stdout — it becomes Claude's context verbatim | Return structured JSON with `hookSpecificOutput.additionalContext` for controlled injection |
| `claude -p` headless | Using `subprocess.run(..., capture_output=True, timeout=N)` — hangs on large outputs | Use `Popen + communicate(timeout=N)` with explicit `killpg` on `TimeoutExpired` |
| `claude -p` headless | Calling `claude -p` without `--max-turns` — unbounded tool-using loop that never returns | Always set `--max-turns 2` or `--max-turns 3` for summarization tasks |
| ChromaDB `PersistentClient` | Assuming delete + re-add is equivalent to upsert for memory management | Use `upsert()` for updates; use full collection recreation for reindex |
| Claude Code hooks JSON output | Any non-JSON text on stdout pollutes the JSON decision parser | Ensure hook scripts have clean stdout; redirect all debug output to stderr |
| SessionEnd hook not firing | Expecting SessionEnd to fire on `ctrl+C` (user interrupt) — it fires on `other` reason, not on SIGKILL | Handle the `other` reason; do not assume graceful shutdown |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Indexing every token from transcript verbatim | ChromaDB slow, injection context noisy | Summarize first, index summaries only | Above ~50 sessions |
| No batch limit on `chroma.add()` | `InvalidArgumentError: batch size too large` crash | Batch at ≤5,000 embeddings per call | Any collection with >5,461 documents added at once |
| Retrieval without metadata filtering | Cross-session noise, irrelevant context injected | Filter by project path in metadata at query time | Immediately if user has multiple projects |
| Synchronous ChromaDB operations on the hot path | SessionStart latency spikes | ChromaDB embedded mode is fast for reads; only writes need care | Above ~10,000 documents |
| Consolidation running during session (online) | Blocks SessionStart/SessionEnd hooks with heavy compute | Run consolidation as a background job, not inline | Any session with large knowledge base |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Indexing secrets from transcript (API keys, passwords echoed in terminal) | Secrets persisted in `.thehook/` and readable by anyone with filesystem access | Apply a regex filter to transcripts before indexing to redact common secret patterns (`sk-`, `ghp_`, etc.) |
| Prompt injection via memory — attacker writes code to project that gets indexed | Future Claude sessions execute malicious injected instructions | Treat injected memory as user context, not system prompt; never inject with system-level authority |
| `thehook/` directory committed to git | Exposes all conversation history, architectural decisions, and secrets to public repos | Default `.gitignore` entry for `.thehook/` in `thehook init`; warn loudly if `.thehook/` is tracked |
| Running `claude -p` with `--dangerouslySkipPermissions` in hook | Hook runs with full permissions; malicious prompt in transcript could execute arbitrary code | Never use `--dangerouslySkipPermissions` in the summarization call; use `--allowedTools` with minimal tools (none for summarization) |

---

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Silent hook failures | User thinks memory is working; nothing is actually captured; they discover months later | Write a `.thehook/last_capture_status` file after every hook run with timestamp and success/failure; `thehook status` should show it |
| No visibility into injected context | User cannot debug why Claude is behaving strangely (based on stale memory) | `thehook status --verbose` shows exactly what would be injected in the next session |
| `thehook init` with no confirmation of hook installation | User runs init, hooks silently fail to register | After init, verify hook is in Claude Code settings and print confirmation with the hook file paths |
| Injecting context from wrong project | User works in project A; context from project B leaks in | Validate `cwd` at SessionStart against the `.thehook/` directory location; refuse injection if mismatch |
| Reindex takes minutes with no progress output | User assumes it crashed | Stream progress to stderr during reindex: "Indexed 47/200 sessions..." |

---

## "Looks Done But Isn't" Checklist

- [ ] **Hook registration:** `thehook init` writes the hook JSON but verify it appears in `claude /hooks` menu — Claude Code captures hooks at startup, so a freshly written hook only activates on next Claude Code launch.
- [ ] **SessionEnd capture:** Hook fires but transcript may not be complete — the transcript file is written by Claude Code; read it only after a small delay or verify file size stabilizes before parsing.
- [ ] **ChromaDB indexing:** `collection.add()` returns without error but documents may not be queryable until the HNSW index is built — verify with a test query immediately after add.
- [ ] **Context injection:** SessionStart hook output appears in debug mode but verify Claude actually receives it — use `--debug` flag and confirm the `additionalContext` field appears in Claude's initial context.
- [ ] **Graceful degradation:** The happy path works; verify the 85s timeout path: does it write a stub summary? Does `thehook status` correctly report "capture timeout" rather than "success"?
- [ ] **Project isolation:** `.thehook/` in project A returns nothing when Claude Code opens project B — test with two projects open simultaneously.

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Corrupted ChromaDB (crash mid-write) | LOW | `thehook reindex` rebuilds from markdown source of truth |
| Hallucinated facts in memory | LOW | `thehook forget <session-id>` deletes specific session; re-run consolidation |
| Hook timeout left stub summaries | LOW | Re-run `thehook capture --session <path>` manually against the transcript |
| HNSW memory bloat | LOW | `thehook reindex` (drop-and-recreate collection) |
| Secrets indexed in `.thehook/` | MEDIUM | Delete affected session markdown, `thehook reindex`, rotate the secret |
| Hook not firing (wrong Claude Code version) | MEDIUM | Verify Claude Code version supports SessionEnd; check `claude --version`; update if needed |
| Context window overflow from too many memories | MEDIUM | Reduce `max_injection_tokens` in config; `thehook reindex` after pruning old sessions |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| SessionEnd timeout race | Phase 1: Hook infrastructure | Test with synthetic 300-turn transcript; measure end-to-end time |
| `claude -p` subprocess hang | Phase 1: Hook infrastructure | Unit test subprocess wrapper with `killpg` on timeout |
| ChromaDB HNSW memory growth | Phase 2: ChromaDB indexing | Create collection with `allow_replace_deleted=True`; test reindex as drop-recreate |
| False memory snowball | Phase 1: Summary prompt design | Include factual constraints in prompt; test with known-false transcript content |
| Context window overflow | Phase 2: Retrieval pipeline | Assert injected token count ≤ 2,000 in retrieval tests |
| Silent hook failures | Phase 1: Hook infrastructure | `thehook status` shows last capture timestamp and status |
| Subprocess PIPE buffer overflow | Phase 1: Hook infrastructure | Test with >64KB `claude -p` output |
| Secrets in memory | Phase 1 + Phase 2 | Secret pattern redaction in transcript parser |
| `.thehook/` committed to git | Phase 1: `thehook init` | `thehook init` writes `.gitignore` entry; test with `git check-ignore` |

---

## Sources

- [Claude Code Hooks Reference — Official Docs](https://code.claude.com/docs/en/hooks) — HIGH confidence (official, current)
- [ChromaDB HNSW Index Pruning — GitHub Issue #2594](https://github.com/chroma-core/chroma/issues/2594) — HIGH confidence (official repo)
- [ChromaDB Memory Not Freed — GitHub Issue #5843](https://github.com/chroma-core/chroma/issues/5843) — HIGH confidence (official repo)
- [ChromaDB Resource Leak — GitHub Issue #3296](https://github.com/chroma-core/chroma/issues/3296) — HIGH confidence (official repo)
- [ChromaDB Memory Management — Chroma Cookbook](https://cookbook.chromadb.dev/strategies/memory-management/) — HIGH confidence (official cookbook)
- [ChromaDB Rebuilding — Chroma Cookbook](https://cookbook.chromadb.dev/strategies/rebuilding/) — HIGH confidence (official cookbook)
- [Claude-Mem Hook Architecture — DeepWiki](https://deepwiki.com/thedotmack/claude-mem/3.1.4-stop-and-sessionend-hooks) — MEDIUM confidence (third-party analysis of open-source project)
- [Claude-Mem GitHub Repo](https://github.com/thedotmack/claude-mem) — MEDIUM confidence (real-world analogous project, 97 open issues observed)
- [Python subprocess.run timeout bug — CPython Issue #81605](https://github.com/python/cpython/issues/81605) — HIGH confidence (official Python tracker)
- [Subprocess Hanging: PIPE is your enemy](https://thraxil.org/users/anders/posts/2008/03/13/Subprocess-Hanging-PIPE-is-your-enemy/) — MEDIUM confidence (well-known, multi-source corroborated)
- [Context Window Overflow — Redis Blog 2026](https://redis.io/blog/context-window-overflow/) — MEDIUM confidence (vendor blog, technically accurate)
- [Seven RAG Pitfalls — Label Studio](https://labelstud.io/blog/seven-ways-your-rag-system-could-be-failing-and-how-to-fix-them/) — MEDIUM confidence (practitioner guide, multiple sources agree)
- [ChromaDB Library Mode Stale Data — Medium](https://medium.com/@okekechimaobi/chromadb-library-mode-stale-rag-data-never-use-it-in-production-heres-why-b6881bd63067) — MEDIUM confidence (verified against ChromaDB docs)
- [Memory Injection Attacks on LLM Agents — arXiv 2503.03704](https://arxiv.org/abs/2503.03704) — HIGH confidence (peer-reviewed)
- [SessionStart Hooks Infinite Hang — Claude Code GitHub Issue #9542](https://github.com/anthropics/claude-code/issues/9542) — HIGH confidence (official repo issue)
- [Fixing Claude Code's Amnesia — blog.fsck.com](https://blog.fsck.com/2025/10/23/episodic-memory/) — MEDIUM confidence (practitioner, corroborated by claude-mem docs)

---
*Pitfalls research for: AI coding agent memory / local RAG CLI tool (TheHook)*
*Researched: 2026-02-23*
