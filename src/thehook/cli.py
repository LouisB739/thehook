import click
from pathlib import Path


@click.group()
@click.version_option()
def main():
    """TheHook - Self-improving long-term memory for AI coding agents."""
    pass


@main.command()
@click.option("--path", default=".", help="Project root directory")
def init(path):
    """Initialize TheHook in the current project."""
    project_dir = Path(path).resolve()
    from thehook.init import init_project
    init_project(project_dir)
    click.echo(f"TheHook initialized in {project_dir / '.thehook'}")
    click.echo("Hooks registered in .claude/settings.local.json")


@main.command()
def capture():
    """Extract knowledge from the completed session transcript (called by SessionEnd hook)."""
    from thehook.capture import run_capture
    run_capture()


@main.command()
@click.option("--path", default=".", help="Project root directory")
def reindex(path):
    """Rebuild the ChromaDB index from all session markdown files."""
    from thehook.storage import reindex as do_reindex
    project_dir = Path(path).resolve()
    count = do_reindex(project_dir)
    click.echo(f"Reindexed {count} session files.")


@main.command()
def retrieve():
    """Inject relevant context into a new Claude Code session (called by SessionStart hook)."""
    from thehook.retrieve import run_retrieve
    run_retrieve()


@main.command()
@click.argument("query")
@click.option("--path", default=".", help="Project root directory")
def recall(query, path):
    """Search stored knowledge for QUERY and print matching results."""
    from thehook.retrieve import query_sessions, format_context
    from thehook.config import load_config
    project_dir = Path(path).resolve()
    config = load_config(project_dir)
    token_budget = config.get("token_budget", 2000)
    documents = query_sessions(project_dir, query_text=query)
    if not documents:
        click.echo("No relevant knowledge found.")
        return
    click.echo(format_context(documents, token_budget=token_budget))


@main.command()
@click.option("--path", default=".", help="Project root directory")
def save(path):
    """Save session knowledge from stdin. Pipe markdown content to this command."""
    import sys
    import uuid
    from thehook.capture import write_session_file
    content = sys.stdin.read().strip()
    if not content:
        click.echo("Nothing to save (empty stdin).", err=True)
        return
    project_dir = Path(path).resolve()
    sessions_dir = project_dir / ".thehook" / "sessions"
    session_id = uuid.uuid4().hex[:12]
    session_path = write_session_file(sessions_dir, session_id, "manual-save", content)
    try:
        from thehook.storage import index_session_file
        index_session_file(project_dir, session_path)
    except Exception:
        pass
    click.echo(f"Saved to {session_path.name}")
