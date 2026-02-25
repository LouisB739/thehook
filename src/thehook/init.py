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
    "UserPromptSubmit": [
        {
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

CURSOR_HOOK_CONFIG = {
    "version": 1,
    "hooks": {
        "sessionEnd": [
            {
                "command": "thehook capture",
                "type": "command",
                "timeout": 120,
            }
        ],
        "sessionStart": [
            {
                "command": "thehook retrieve",
                "type": "command",
                "timeout": 30,
            }
        ],
        "beforeSubmitPrompt": [
            {
                "command": "thehook retrieve",
                "type": "command",
                "timeout": 30,
            }
        ],
    },
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

    # Create .gitignore to exclude chromadb (rebuilt with thehook reindex)
    gitignore_path = thehook_dir / ".gitignore"
    if not gitignore_path.exists():
        gitignore_path.write_text("chromadb/\n")

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

    # Register Cursor hooks
    cursor_dir = project_dir / ".cursor"
    cursor_dir.mkdir(exist_ok=True)
    cursor_hooks_path = cursor_dir / "hooks.json"

    with open(cursor_hooks_path, "w") as f:
        json.dump(CURSOR_HOOK_CONFIG, f, indent=2)
