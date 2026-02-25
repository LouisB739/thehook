"""Retrieval functions for the SessionStart hook and recall CLI."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_RETRIEVAL_QUERY = "project conventions decisions gotchas architecture"


def _extract_documents(results: dict) -> list[str]:
    """Extract first query result list safely from ChromaDB response."""
    documents = results.get("documents", [])
    if not documents:
        return []
    return documents[0] or []


def _recency_where_clause(recency_days: int) -> dict | None:
    """Build a ChromaDB metadata filter for recent sessions."""
    if recency_days <= 0:
        return None
    cutoff = datetime.now(timezone.utc) - timedelta(days=recency_days)
    return {"timestamp": {"$gte": cutoff.isoformat()}}


def query_sessions(
    project_dir: Path,
    query_text: str,
    n_results: int = 5,
    recency_days: int = 0,
    recency_fallback_global: bool = True,
) -> list[str]:
    """Query ChromaDB for session documents matching query_text.

    Optional recency filtering limits retrieval to sessions newer than
    `recency_days`. If that returns no hits, a global fallback query can run.

    Returns [] when collection does not exist, is empty, or on any error.
    Uses lazy chromadb import to avoid ~1s startup cost.
    """
    try:
        from thehook.storage import get_chroma_client, COLLECTION_NAME
        client = get_chroma_client(project_dir)
        collection = client.get_collection(COLLECTION_NAME)
        count = collection.count()
        if count == 0:
            return []
        actual_n = min(max(1, n_results), count)
        where = _recency_where_clause(recency_days)
        if where:
            filtered_results = collection.query(
                query_texts=[query_text],
                n_results=actual_n,
                where=where,
            )
            filtered_docs = _extract_documents(filtered_results)
            if filtered_docs or not recency_fallback_global:
                return filtered_docs

        results = collection.query(query_texts=[query_text], n_results=actual_n)
        return _extract_documents(results)
    except Exception:
        return []


def format_context(documents: list[str], token_budget: int = 2000) -> str:
    """Assemble documents into a context string, capped at token_budget tokens.

    Uses chars/4 as token estimate (standard approximation for ASCII markdown).
    Documents are joined with '---' separators. If adding a document would
    exceed the budget, it is trimmed to fit the remaining space.
    """
    max_chars = token_budget * 4
    parts = []
    total = 0
    for doc in documents:
        doc_chars = len(doc)
        if total + doc_chars > max_chars:
            remaining = max_chars - total
            if remaining > 0:
                parts.append(doc[:remaining])
            break
        parts.append(doc)
        total += doc_chars
    return "\n\n---\n\n".join(parts)


def _query_from_hook_input(hook_input: dict) -> str:
    """Choose retrieval query from hook payload, with a safe fallback.

    UserPromptSubmit provides a `prompt` field; when present we use it for
    query-aware retrieval. SessionStart and unknown events fall back to a
    generic project-memory query.
    """
    prompt = str(hook_input.get("prompt", "")).strip()
    if prompt:
        return prompt
    return DEFAULT_RETRIEVAL_QUERY


def run_retrieve() -> None:
    """Retrieval hook pipeline: read stdin, query ChromaDB, print context JSON.

    Reads hook input from stdin (same format as capture.py), queries ChromaDB
    for relevant session documents, assembles context within the token budget
    from config, and prints valid hookSpecificOutput JSON to stdout.

    Prints nothing if no context is found -- Claude Code handles empty stdout.
    All exceptions are caught silently to prevent hook failures.
    """
    import json
    from thehook.capture import read_hook_input
    from thehook.config import load_config

    try:
        hook_input = read_hook_input()
        if not hook_input:
            return

        workspace_roots = hook_input.get("workspace_roots", [])
        cwd = hook_input.get("cwd") or (workspace_roots[0] if workspace_roots else ".")
        project_dir = Path(cwd)

        config = load_config(project_dir)
        token_budget = config.get("token_budget", 2000)
        retrieval_n_results = max(1, int(config.get("retrieval_n_results", 5)))
        retrieval_recency_days = max(0, int(config.get("retrieval_recency_days", 0)))
        retrieval_recency_fallback_global = bool(
            config.get("retrieval_recency_fallback_global", True)
        )
        hook_event_name = hook_input.get("hook_event_name", "SessionStart")
        query_text = _query_from_hook_input(hook_input)

        documents = query_sessions(
            project_dir,
            query_text=query_text,
            n_results=retrieval_n_results,
            recency_days=retrieval_recency_days,
            recency_fallback_global=retrieval_recency_fallback_global,
        )
        context = format_context(documents, token_budget=token_budget)

        if context:
            output = {
                "hookSpecificOutput": {
                    "hookEventName": hook_event_name,
                    "additionalContext": context,
                }
            }
            print(json.dumps(output), flush=True)
    except Exception:
        pass  # Hook must never crash -- degrade silently
