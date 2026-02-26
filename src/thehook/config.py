from pathlib import Path
from copy import deepcopy
import yaml


DEFAULT_CONFIG = {
    "token_budget": 2000,
    "retrieval_n_results": 5,
    "retrieval_recency_days": 0,
    "retrieval_recency_fallback_global": True,
    "consolidation_threshold": 5,
    "intermediate_capture_enabled": True,
    "intermediate_capture_timeout_seconds": 20,
    "intermediate_capture_min_interval_seconds": 180,
    "intermediate_capture_max_transcript_chars": 12000,
    "auto_consolidation_enabled": True,
    "active_hooks": ["SessionEnd", "SessionStart", "UserPromptSubmit", "Stop", "PreCompact"],
    "consolidation_timeout_seconds": 120,
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
