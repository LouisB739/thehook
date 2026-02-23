from pathlib import Path
from copy import deepcopy
import yaml


DEFAULT_CONFIG = {
    "token_budget": 2000,
    "consolidation_threshold": 5,
    "active_hooks": ["SessionEnd", "SessionStart"],
}


def _deep_merge(base: dict, override: dict) -> dict:
    result = deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def load_config(project_dir: Path) -> dict:
    config_path = project_dir / "thehook.yaml"
    if not config_path.exists():
        return deepcopy(DEFAULT_CONFIG)
    with open(config_path) as f:
        user_config = yaml.safe_load(f) or {}
    return _deep_merge(DEFAULT_CONFIG, user_config)
