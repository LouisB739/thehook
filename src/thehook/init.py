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
    "Stop": [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": "thehook capture-lite",
                    "async": True,
                    "timeout": 25,
                }
            ]
        }
    ],
    "PreCompact": [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": "thehook capture-lite",
                    "async": True,
                    "timeout": 25,
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
        "stop": [
            {
                "command": "thehook capture-lite",
                "type": "command",
                "timeout": 25,
            }
        ],
        "preCompact": [
            {
                "command": "thehook capture-lite",
                "type": "command",
                "timeout": 25,
            }
        ],
    },
}


def _load_active_hooks(project_dir: Path) -> list[str]:
    """Load active hook names from config with safe defaults."""
    try:
        from thehook.config import load_config
        config = load_config(project_dir)
    except Exception:
        return list(HOOK_CONFIG.keys())
    active_hooks = config.get("active_hooks")
    if not isinstance(active_hooks, list) or not active_hooks:
        return list(HOOK_CONFIG.keys())
    return [str(name) for name in active_hooks]


def _build_claude_hooks(active_hooks: list[str]) -> dict:
    return {name: HOOK_CONFIG[name] for name in active_hooks if name in HOOK_CONFIG}


def _build_cursor_hooks(active_hooks: list[str]) -> dict:
    mapping = {
        "SessionEnd": "sessionEnd",
        "SessionStart": "sessionStart",
        "UserPromptSubmit": "beforeSubmitPrompt",
        "Stop": "stop",
        "PreCompact": "preCompact",
    }
    hooks = {}
    for name in active_hooks:
        cursor_name = mapping.get(name)
        if cursor_name and cursor_name in CURSOR_HOOK_CONFIG["hooks"]:
            hooks[cursor_name] = CURSOR_HOOK_CONFIG["hooks"][cursor_name]
    return hooks


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
        gitignore_path.write_text("chromadb/\nintermediate_capture_state.json\n")
    else:
        existing = gitignore_path.read_text().splitlines()
        required_entries = {"chromadb/", "intermediate_capture_state.json"}
        merged = list(existing)
        for entry in required_entries:
            if entry not in existing:
                merged.append(entry)
        gitignore_path.write_text("\n".join(merged).rstrip() + "\n")

    active_hooks = _load_active_hooks(project_dir)

    # Register Claude Code hooks
    claude_dir = project_dir / ".claude"
    claude_dir.mkdir(exist_ok=True)
    settings_path = claude_dir / "settings.local.json"

    settings = {}
    if settings_path.exists():
        settings = json.loads(settings_path.read_text())

    settings["hooks"] = _build_claude_hooks(active_hooks)

    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=2)

    # Register Cursor hooks
    cursor_dir = project_dir / ".cursor"
    cursor_dir.mkdir(exist_ok=True)
    cursor_hooks_path = cursor_dir / "hooks.json"

    cursor_hook_config = {
        "version": CURSOR_HOOK_CONFIG["version"],
        "hooks": _build_cursor_hooks(active_hooks),
    }

    with open(cursor_hooks_path, "w") as f:
        json.dump(cursor_hook_config, f, indent=2)
