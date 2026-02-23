import json
import pytest
from pathlib import Path

from thehook.init import init_project


def test_init_creates_thehook_directory_structure(tmp_project):
    """init_project creates .thehook/sessions/, .thehook/knowledge/, .thehook/chromadb/"""
    init_project(tmp_project)
    assert (tmp_project / ".thehook" / "sessions").is_dir()
    assert (tmp_project / ".thehook" / "knowledge").is_dir()
    assert (tmp_project / ".thehook" / "chromadb").is_dir()


def test_init_registers_session_end_hook(tmp_project):
    """init_project writes SessionEnd hook with thehook capture, async, timeout 120"""
    init_project(tmp_project)
    settings_path = tmp_project / ".claude" / "settings.local.json"
    settings = json.loads(settings_path.read_text())

    hooks = settings["hooks"]
    assert "SessionEnd" in hooks
    session_end = hooks["SessionEnd"]
    assert isinstance(session_end, list) and len(session_end) > 0
    inner_hooks = session_end[0]["hooks"]
    assert isinstance(inner_hooks, list) and len(inner_hooks) > 0
    cmd = inner_hooks[0]
    assert cmd["type"] == "command"
    assert "thehook capture" in cmd["command"]
    assert cmd["async"] is True
    assert cmd["timeout"] == 120


def test_init_registers_session_start_hook(tmp_project):
    """init_project writes SessionStart hook with thehook retrieve, timeout 30, matcher startup"""
    init_project(tmp_project)
    settings_path = tmp_project / ".claude" / "settings.local.json"
    settings = json.loads(settings_path.read_text())

    hooks = settings["hooks"]
    assert "SessionStart" in hooks
    session_start = hooks["SessionStart"]
    assert isinstance(session_start, list) and len(session_start) > 0
    entry = session_start[0]
    assert entry["matcher"] == "startup"
    inner_hooks = entry["hooks"]
    assert isinstance(inner_hooks, list) and len(inner_hooks) > 0
    cmd = inner_hooks[0]
    assert cmd["type"] == "command"
    assert "thehook retrieve" in cmd["command"]
    assert cmd["timeout"] == 30


def test_init_preserves_existing_settings(tmp_project):
    """init_project preserves existing non-hook keys in settings.local.json"""
    claude_dir = tmp_project / ".claude"
    claude_dir.mkdir()
    settings_path = claude_dir / "settings.local.json"
    settings_path.write_text(json.dumps({"some_existing": "setting"}))

    init_project(tmp_project)

    settings = json.loads(settings_path.read_text())
    assert settings["some_existing"] == "setting"
    assert "hooks" in settings


def test_init_is_idempotent(tmp_project):
    """Calling init_project twice does not error; directories and hooks remain correct"""
    init_project(tmp_project)
    init_project(tmp_project)  # second call — must not raise

    assert (tmp_project / ".thehook" / "sessions").is_dir()
    assert (tmp_project / ".thehook" / "knowledge").is_dir()
    assert (tmp_project / ".thehook" / "chromadb").is_dir()

    settings_path = tmp_project / ".claude" / "settings.local.json"
    settings = json.loads(settings_path.read_text())
    assert "hooks" in settings
    assert "SessionEnd" in settings["hooks"]
    assert "SessionStart" in settings["hooks"]


def test_init_creates_claude_dir_if_missing(tmp_project):
    """init_project creates .claude/ and settings.local.json when .claude/ does not exist"""
    assert not (tmp_project / ".claude").exists()

    init_project(tmp_project)

    assert (tmp_project / ".claude").is_dir()
    settings_path = tmp_project / ".claude" / "settings.local.json"
    assert settings_path.exists()
    settings = json.loads(settings_path.read_text())
    assert "hooks" in settings
