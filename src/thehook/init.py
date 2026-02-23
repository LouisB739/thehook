import json
from pathlib import Path


HOOK_CONFIG = {
    "SessionEnd": [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": "thehook capture",
                    "async": True,
                    "timeout": 120,
                }
            ]
        }
    ],
    "SessionStart": [
        {
            "matcher": "startup",
            "hooks": [
                {
                    "type": "command",
                    "command": "thehook retrieve",
                    "timeout": 30,
                }
            ]
        }
    ],
}


def init_project(project_dir: Path) -> None:
    """Initialize TheHook in the given project directory.

    Creates .thehook/ directory structure and registers Claude Code lifecycle
    hooks in .claude/settings.local.json.
    """
    # Create .thehook directory structure
    thehook_dir = project_dir / ".thehook"
    (thehook_dir / "sessions").mkdir(parents=True, exist_ok=True)
    (thehook_dir / "knowledge").mkdir(parents=True, exist_ok=True)
    (thehook_dir / "chromadb").mkdir(parents=True, exist_ok=True)

    # Register Claude Code hooks
    claude_dir = project_dir / ".claude"
    claude_dir.mkdir(exist_ok=True)
    settings_path = claude_dir / "settings.local.json"

    settings = {}
    if settings_path.exists():
        settings = json.loads(settings_path.read_text())

    settings["hooks"] = HOOK_CONFIG

    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=2)
