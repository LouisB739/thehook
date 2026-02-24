"""Retrieval functions for the SessionStart hook and recall CLI."""

from pathlib import Path


def query_sessions(project_dir: Path, query_text: str, n_results: int = 5) -> list[str]:
    """Query ChromaDB for session documents matching query_text.

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
        actual_n = min(n_results, count)
        results = collection.query(query_texts=[query_text], n_results=actual_n)
        return results["documents"][0]
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


def run_retrieve() -> None:
    """SessionStart hook pipeline: read stdin, query ChromaDB, print context JSON.

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

        cwd = hook_input.get("cwd", ".")
        project_dir = Path(cwd)

        config = load_config(project_dir)
        token_budget = config.get("token_budget", 2000)

        documents = query_sessions(
            project_dir,
            query_text="project conventions decisions gotchas architecture",
        )
        context = format_context(documents, token_budget=token_budget)

        if context:
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": context,
                }
            }
            print(json.dumps(output), flush=True)
    except Exception:
        pass  # Hook must never crash -- degrade silently
