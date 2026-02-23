import pytest
from pathlib import Path


def test_load_config_no_yaml_returns_defaults(tmp_project):
    """No thehook.yaml exists; load_config returns exact defaults."""
    from thehook.config import load_config
    config = load_config(tmp_project)
    assert config["token_budget"] == 2000
    assert config["consolidation_threshold"] == 5
    assert config["active_hooks"] == ["SessionEnd", "SessionStart"]


def test_load_config_full_yaml_overrides_all(tmp_project):
    """thehook.yaml with all keys set; load_config returns custom values."""
    from thehook.config import load_config
    yaml_content = (
        "token_budget: 4000\n"
        "consolidation_threshold: 10\n"
        "active_hooks:\n"
        "  - SessionEnd\n"
    )
    (tmp_project / "thehook.yaml").write_text(yaml_content)
    config = load_config(tmp_project)
    assert config["token_budget"] == 4000
    assert config["consolidation_threshold"] == 10
    assert config["active_hooks"] == ["SessionEnd"]


def test_load_config_partial_yaml_merges_with_defaults(tmp_project):
    """thehook.yaml with only token_budget; other keys retain defaults."""
    from thehook.config import load_config
    (tmp_project / "thehook.yaml").write_text("token_budget: 3000\n")
    config = load_config(tmp_project)
    assert config["token_budget"] == 3000
    assert config["consolidation_threshold"] == 5
    assert config["active_hooks"] == ["SessionEnd", "SessionStart"]


def test_load_config_empty_yaml_returns_defaults(tmp_project):
    """Empty thehook.yaml (yaml.safe_load returns None); load_config returns defaults."""
    from thehook.config import load_config
    (tmp_project / "thehook.yaml").write_text("")
    config = load_config(tmp_project)
    assert config["token_budget"] == 2000
    assert config["consolidation_threshold"] == 5
    assert config["active_hooks"] == ["SessionEnd", "SessionStart"]


def test_load_config_does_not_mutate_defaults(tmp_project):
    """Calling load_config twice does not leak state between calls."""
    from thehook.config import load_config, DEFAULT_CONFIG
    # First call with custom yaml
    (tmp_project / "thehook.yaml").write_text("token_budget: 9999\n")
    config1 = load_config(tmp_project)
    assert config1["token_budget"] == 9999

    # Second call with no yaml (different tmp dir)
    import tempfile
    with tempfile.TemporaryDirectory() as other_dir:
        config2 = load_config(Path(other_dir))
    assert config2["token_budget"] == 2000

    # DEFAULT_CONFIG itself must not be mutated
    assert DEFAULT_CONFIG["token_budget"] == 2000
    assert DEFAULT_CONFIG["consolidation_threshold"] == 5
    assert DEFAULT_CONFIG["active_hooks"] == ["SessionEnd", "SessionStart"]
