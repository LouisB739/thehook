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
