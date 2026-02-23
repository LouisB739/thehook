# Phase 1: Setup - Research

**Researched:** 2026-02-23
**Domain:** Python CLI packaging, Claude Code hooks API, YAML config, pyproject.toml
**Confidence:** HIGH

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| SETUP-01 | User can run `thehook init` to wire SessionEnd and SessionStart hooks into Claude Code settings | Hooks API fully documented; target file is `.claude/settings.local.json`; JSON merge pattern verified |
| SETUP-02 | `thehook init` creates `.thehook/` directory structure (sessions/, knowledge/, chromadb/) | Standard `pathlib.Path.mkdir(exist_ok=True)` pattern; directory names locked in requirements |
| SETUP-03 | User can configure behavior via `thehook.yaml` (token budget, consolidation threshold, active hooks) | PyYAML `safe_load`; deep-merge pattern with `copy.deepcopy`; `thehook.yaml` is at project root per requirements |
| SETUP-04 | Config has sensible defaults — tool works without any YAML file present | `DEFAULT_CONFIG` dict with `deepcopy` fallback; no file = return defaults directly |

</phase_requirements>

---

## Summary

Phase 1 establishes a Python CLI package installable via `pip install -e .`, with a single entry point `thehook` backed by Click. The `thehook init` command creates a `.thehook/` directory tree in the current project, wires two Claude Code lifecycle hooks (`SessionEnd`, `SessionStart`) into `.claude/settings.local.json`, and optionally generates a `thehook.yaml` config skeleton. The config system loads a YAML file from the project root (not inside `.thehook/`) when present and deep-merges it over hard-coded defaults; absent config silently uses defaults.

All four SETUP requirements are well-understood problems with established Python solutions. The Claude Code hooks API is fully documented with precise input/output schemas — no guesswork required. The only genuine decision point is which `settings.json` file `init` should write to: official docs support three project-level targets; the implementation plan chose `.claude/settings.local.json` (project-local, gitignored) which is the right default for a per-developer tool.

One naming discrepancy exists between requirements and the pre-written implementation plan: SETUP-02 says `knowledge/` (singular) while the plan uses `knowledges/`. The requirements are authoritative; the plan should be corrected during planning. Similarly, SETUP-03 names the config file `thehook.yaml` at the project root, while the plan mistakenly uses `.thehook/config.yaml`. Requirements win.

**Primary recommendation:** Python 3.11+ / Click 8.1+ / PyYAML 6.0+ / Hatchling build backend. Write hooks to `.claude/settings.local.json` (project-local, safe to create programmatically). Config file is `thehook.yaml` at project root, defaulting silently when absent.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.11+ | Runtime | f-strings, `match`, `tomllib`, modern `pathlib`; ChromaDB requires 3.8+ but 3.11 is the project decision |
| Click | 8.1+ | CLI framework | De-facto Python CLI standard; `@click.group()` + `@group.command()` pattern; `CliRunner` for testing |
| PyYAML | 6.0+ | YAML parsing | `yaml.safe_load` / `yaml.dump`; standard for config files; pre-decision |
| Hatchling | latest | Build backend | PEP 517 compliant; fast; `[project.scripts]` entry point support; simpler than setuptools |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | 8.0+ | Test framework | `tmp_path` fixture for filesystem isolation; `CliRunner` for CLI tests |
| pathlib | stdlib | Path manipulation | All file operations; `Path.mkdir(exist_ok=True)`, `Path.exists()`, `read_text()`, `write_text()` |
| json | stdlib | settings.json read/write | Merge existing Claude settings with hook config |
| copy | stdlib | Config deep-merge | `deepcopy(DEFAULT_CONFIG)` before merging user overrides |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Hatchling | setuptools | setuptools is verbose; hatchling is cleaner for `src/` layout; hatchling is default for `hatch new` projects |
| PyYAML | strictyaml / pydantic-yaml | Over-engineered for simple config; PyYAML `safe_load` is sufficient and already decided |
| Click | Typer / argparse | Typer adds pydantic complexity; argparse has no testing runner; Click is the pre-planning decision |
| `.claude/settings.local.json` | `~/.claude/settings.json` | Global file affects all projects; local is per-project and gitignored by default |

**Installation:**
```bash
pip install click>=8.1 pyyaml>=6.0
pip install --dev pytest>=8.0
```

Packaged via:
```bash
pip install -e ".[dev]"
```

---

## Architecture Patterns

### Recommended Project Structure
```
thehook/
├── pyproject.toml          # build system + entry point declaration
├── thehook.yaml            # user config (optional, at project root)
├── src/
│   └── thehook/
│       ├── __init__.py     # version string
│       ├── cli.py          # Click group + command registration
│       ├── init.py         # thehook init logic
│       └── config.py       # load_config + DEFAULT_CONFIG
├── tests/
│   ├── __init__.py
│   ├── conftest.py         # shared fixtures (tmp_project)
│   ├── test_init.py        # tests for thehook init behavior
│   └── test_config.py      # tests for config loading and merging
└── .thehook/               # created by thehook init at runtime
    ├── sessions/           # markdown session files
    ├── knowledge/          # consolidated knowledge (SETUP-02: singular)
    └── chromadb/           # vector DB storage
```

### Pattern 1: Click Entry Point via pyproject.toml

**What:** Declares `thehook` as an installable console script pointing to `thehook.cli:main`
**When to use:** Any Python CLI that needs `pip install -e .` to produce a runnable command

```toml
# Source: https://click.palletsprojects.com/en/stable/entry-points/
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "thehook"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "click>=8.1",
    "pyyaml>=6.0",
]

[project.scripts]
thehook = "thehook.cli:main"

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[tool.hatch.build.targets.wheel]
packages = ["src/thehook"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

### Pattern 2: Click Command Group

**What:** `@click.group()` creates a multi-command CLI; subcommands are registered with `@main.command()`
**When to use:** CLI with multiple verbs (`init`, `capture`, `retrieve`, `recall`, `reindex`)

```python
# Source: https://context7.com/pallets/click/llms.txt
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
```

### Pattern 3: Config Deep-Merge

**What:** Load optional `thehook.yaml` from project root; deep-merge over `DEFAULT_CONFIG`; return defaults when file is absent
**When to use:** Any tool where partial config override is valid

```python
# Source: Python stdlib docs + project decision
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
    config_path = project_dir / "thehook.yaml"   # PROJECT ROOT, not .thehook/
    if not config_path.exists():
        return deepcopy(DEFAULT_CONFIG)
    with open(config_path) as f:
        user_config = yaml.safe_load(f) or {}
    return _deep_merge(DEFAULT_CONFIG, user_config)
```

### Pattern 4: Claude Code Hook Registration

**What:** Read existing `.claude/settings.local.json` (or start empty dict); set/replace `hooks` key; write back
**When to use:** `thehook init` writes hooks; must not destroy existing non-hook settings

```python
# Source: https://code.claude.com/docs/en/hooks (verified 2026-02-23)
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

def _setup_claude_hooks(project_dir: Path) -> None:
    claude_dir = project_dir / ".claude"
    claude_dir.mkdir(exist_ok=True)
    settings_path = claude_dir / "settings.local.json"

    settings = {}
    if settings_path.exists():
        settings = json.loads(settings_path.read_text())

    settings["hooks"] = HOOK_CONFIG

    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=2)
```

### Pattern 5: Testing CLI with CliRunner

**What:** `click.testing.CliRunner` invokes Click commands in-process with controlled filesystem
**When to use:** All CLI command tests; combine with `tmp_path` for filesystem isolation

```python
# Source: https://context7.com/pallets/click/llms.txt
from click.testing import CliRunner
from pathlib import Path
from thehook.cli import main

def test_init_command(tmp_path):
    runner = CliRunner()
    result = runner.invoke(main, ["init", "--path", str(tmp_path)])
    assert result.exit_code == 0
    assert (tmp_path / ".thehook").is_dir()
```

### Anti-Patterns to Avoid

- **Writing hooks to `~/.claude/settings.json`:** Affects all the user's projects — too broad for a per-project tool. Use `.claude/settings.local.json` instead.
- **Storing user config inside `.thehook/config.yaml`:** SETUP-03 names the file `thehook.yaml` at the project root. The pre-written plan disagrees — requirements win.
- **Using `knowledges/` directory name:** SETUP-02 requires `knowledge/` (singular). The pre-written plan uses `knowledges/` — requirements win.
- **`yaml.load()` without Loader:** Always `yaml.safe_load()` — avoids arbitrary code execution from config files.
- **Mutating `DEFAULT_CONFIG` dict:** Always `deepcopy(DEFAULT_CONFIG)` before returning; shared mutable state between tests will cause non-deterministic failures.
- **Using `settings.json` instead of `settings.local.json`:** The `.json` variant is team-shareable and gets committed; `settings.local.json` is gitignored and personal — correct for a per-machine tool.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| CLI argument parsing | Custom `sys.argv` parser | `Click` | Groups, options, help text, CliRunner testing |
| YAML deep-merge | Custom recursive merge | `copy.deepcopy` + simple recursive function | Edge cases: None values, list clobber vs extend, type mismatch |
| CLI entry point wiring | Shell scripts / symlinks | `pyproject.toml [project.scripts]` | pip handles PATH, shebang, venv activation automatically |
| Path operations | `os.path` string concat | `pathlib.Path` | `mkdir(parents=True, exist_ok=True)`, `/` operator, `.exists()`, platform-safe |
| Test filesystem | Manually create/cleanup dirs | `pytest tmp_path` | Auto-cleanup, unique per test, pathlib.Path object |

**Key insight:** For Phase 1, all problems are "wiring" problems — connecting existing tools (Click, YAML, JSON, pathlib) correctly, not building new infrastructure. Complexity risk is in correctness of config file paths and JSON merge, not in the tools themselves.

---

## Common Pitfalls

### Pitfall 1: Wrong Config File Location

**What goes wrong:** Config is written to `.thehook/config.yaml` (as in the pre-written plan) instead of `thehook.yaml` at project root (as specified in SETUP-03).
**Why it happens:** The implementation plan was written before requirements were finalized, and made a local-storage assumption.
**How to avoid:** Config path is `project_dir / "thehook.yaml"`. Phase 1 success criterion 4 says "A `thehook.yaml` file with custom values..." — at project root.
**Warning signs:** Tests that create config at `.thehook/config.yaml` rather than `thehook.yaml` will pass but not match requirements.

### Pitfall 2: Wrong Directory Name for Knowledge Storage

**What goes wrong:** Directory created as `knowledges/` (pre-written plan) instead of `knowledge/` (SETUP-02 requirement).
**Why it happens:** Copy-paste from plan without checking requirements.
**How to avoid:** SETUP-02 text: "`.thehook/` directory structure (sessions/, knowledge/, chromadb/)". Use singular `knowledge/`.
**Warning signs:** Integration tests against SETUP-02 success criterion 1 will fail with `knowledge/` not found.

### Pitfall 3: Overwriting Non-Hook Settings

**What goes wrong:** `init` writes only `{"hooks": ...}` to `settings.local.json`, destroying existing settings.
**Why it happens:** Forgetting to read-then-merge before write.
**How to avoid:** Always read existing JSON first (`settings = json.loads(path.read_text())`), update only `settings["hooks"]`, write back.
**Warning signs:** A test that writes `{"some_existing": "setting"}` to settings first, then runs init, then checks `some_existing` is preserved.

### Pitfall 4: SessionStart matcher "resume" Double-Injection

**What goes wrong:** SessionStart hook fires on `source: "resume"` in addition to `source: "startup"`, causing context to be injected twice when resuming.
**Why it happens:** Omitting the `matcher: "startup"` field (or setting it to `"*"`) catches all session starts.
**How to avoid:** Set `"matcher": "startup"` on the SessionStart hook entry so it only fires for new sessions. This is already noted in STATE.md as a concern for Phase 2, but the hook configuration must be set correctly in Phase 1.
**Warning signs:** Manual test: start session, `/resume`, check that context injection is not duplicated.

### Pitfall 5: `thehook.yaml` with partial config loses defaults

**What goes wrong:** User writes only `token_budget: 3000` in `thehook.yaml`; other defaults vanish because shallow-merge replaces the entire dict.
**Why it happens:** `result.update(user_config)` instead of deep-merge.
**How to avoid:** Use the `_deep_merge(base, override)` recursive pattern with `deepcopy`. Verified that this is the intended pattern from SETUP-04 requirement ("sensible defaults are applied silently").
**Warning signs:** Test: partial YAML only sets one field, assert other fields equal defaults.

### Pitfall 6: Mutating DEFAULT_CONFIG

**What goes wrong:** Tests modify returned config dict; next test gets a mutated DEFAULT_CONFIG.
**Why it happens:** Returning `DEFAULT_CONFIG` directly instead of a copy.
**How to avoid:** `load_config` always returns `deepcopy(DEFAULT_CONFIG)` when no file, or `_deep_merge(DEFAULT_CONFIG, user_config)` which creates a new dict via deepcopy.
**Warning signs:** Tests pass individually but fail when run together.

---

## Code Examples

Verified patterns from official sources:

### Directory structure creation
```python
# Source: Python stdlib pathlib
from pathlib import Path

def create_thehook_dirs(project_dir: Path) -> None:
    thehook_dir = project_dir / ".thehook"
    (thehook_dir / "sessions").mkdir(parents=True, exist_ok=True)
    (thehook_dir / "knowledge").mkdir(parents=True, exist_ok=True)   # singular per SETUP-02
    (thehook_dir / "chromadb").mkdir(parents=True, exist_ok=True)
```

### SessionStart full input schema (from official docs)
```json
{
  "session_id": "abc123",
  "transcript_path": "/Users/.../.claude/projects/.../00893aaf.jsonl",
  "cwd": "/Users/...",
  "permission_mode": "default",
  "hook_event_name": "SessionStart",
  "source": "startup",
  "model": "claude-sonnet-4-6"
}
```

### SessionStart decision output (additionalContext)
```json
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "# Project Memory\n..."
  }
}
```

### SessionEnd full input schema (from official docs)
```json
{
  "session_id": "abc123",
  "transcript_path": "/Users/.../.claude/projects/.../00893aaf.jsonl",
  "cwd": "/Users/...",
  "permission_mode": "default",
  "hook_event_name": "SessionEnd",
  "reason": "other"
}
```

### CliRunner test with isolated filesystem
```python
# Source: https://context7.com/pallets/click/llms.txt
from click.testing import CliRunner
from thehook.cli import main

def test_init_creates_structure(tmp_path):
    runner = CliRunner()
    result = runner.invoke(main, ["init", "--path", str(tmp_path)])
    assert result.exit_code == 0
    assert (tmp_path / ".thehook" / "sessions").is_dir()
    assert (tmp_path / ".thehook" / "knowledge").is_dir()    # singular
    assert (tmp_path / ".thehook" / "chromadb").is_dir()
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `setup.py` + `setup.cfg` | `pyproject.toml` only | PEP 517/518, ~2020; mainstream by 2023 | All new Python packages use pyproject.toml |
| `os.path` for file ops | `pathlib.Path` | Python 3.4+; standard by 3.6 | More readable, platform-safe, composable |
| `tmpdir` fixture (pytest) | `tmp_path` (pathlib.Path) | pytest 3.9+ | Auto-cleanup; strongly preferred over tmpdir |
| Writing all hooks globally | Per-scope (user/project/local) | Claude Code hooks reference (current) | Choose `.claude/settings.local.json` for per-project, non-shared |
| `PreToolUse` top-level `decision` field | `hookSpecificOutput.permissionDecision` | Current docs (deprecated old pattern) | Not relevant to Phase 1, but noted for Phase 2 hooks |

**Deprecated/outdated:**
- `setup.py`: Do not use for new projects; pyproject.toml is the standard.
- `tmpdir` pytest fixture: Use `tmp_path` instead; provides `pathlib.Path` directly.
- `yaml.load()` without explicit Loader: Always `yaml.safe_load()`.

---

## Open Questions

1. **`thehook.yaml` location: project root vs `.thehook/config.yaml`**
   - What we know: SETUP-03 names it `thehook.yaml` and the success criterion says "A `thehook.yaml` file with custom values...". The pre-written plan uses `.thehook/config.yaml`.
   - What's unclear: Root-level `thehook.yaml` is more visible/discoverable; `.thehook/config.yaml` is more encapsulated. Both are valid UX choices.
   - Recommendation: **Trust requirements — use `thehook.yaml` at project root.** The pre-written plan should be updated during planning.

2. **Hook registration target: `settings.local.json` vs `settings.json`**
   - What we know: `.claude/settings.local.json` is gitignored, per-machine, correct for personal hooks. `.claude/settings.json` is committed and team-shared.
   - What's unclear: User expectation — do they want hooks personal or shared?
   - Recommendation: **Use `.claude/settings.local.json`** (pre-written plan's choice). TheHook is a personal productivity tool; hooks should not be committed to team repos.

3. **`~/.claude/settings.json` global option**
   - What we know: Registering in the global file means hooks fire in ALL projects, not just this one.
   - What's unclear: SETUP-01 says "wire hooks into Claude Code settings" without specifying scope.
   - Recommendation: **Project-local (`.claude/settings.local.json`) is safer.** Global would affect unrelated projects. Phase 1 success criterion says "Running `thehook init` in a project root" — implies project scope.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.0+ |
| Config file | `pyproject.toml` — `[tool.pytest.ini_options]` (Wave 0 gap, does not exist yet) |
| Quick run command | `pytest tests/ -x -q` |
| Full suite command | `pytest tests/ -v` |
| Estimated runtime | ~2–5 seconds (pure filesystem + in-process CLI, no network, no ChromaDB in Phase 1) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SETUP-01 | `thehook init` writes SessionEnd + SessionStart hooks to `.claude/settings.local.json` | unit | `pytest tests/test_init.py -x -k "hooks"` | Wave 0 gap |
| SETUP-01 | Existing settings keys are preserved after init | unit | `pytest tests/test_init.py -x -k "merge"` | Wave 0 gap |
| SETUP-02 | `.thehook/sessions/`, `.thehook/knowledge/`, `.thehook/chromadb/` created | unit | `pytest tests/test_init.py -x -k "directory"` | Wave 0 gap |
| SETUP-03 | `thehook.yaml` at project root is loaded and applied over defaults | unit | `pytest tests/test_config.py -x -k "yaml"` | Wave 0 gap |
| SETUP-03 | Partial YAML merges with defaults (unset keys keep defaults) | unit | `pytest tests/test_config.py -x -k "partial"` | Wave 0 gap |
| SETUP-04 | No `thehook.yaml` file → defaults returned silently | unit | `pytest tests/test_config.py -x -k "defaults"` | Wave 0 gap |
| SETUP-04 | `thehook init` runs without `thehook.yaml` present | unit | `pytest tests/test_init.py -x -k "no_config"` | Wave 0 gap |

### Nyquist Sampling Rate
- **Minimum sample interval:** After every committed task → run: `pytest tests/ -x -q`
- **Full suite trigger:** Before merging final task of Phase 1
- **Phase-complete gate:** Full suite green before `/gsd:verify-work` runs
- **Estimated feedback latency per task:** ~3 seconds

### Wave 0 Gaps (must be created before implementation)

- [ ] `pyproject.toml` — declares package, entry point `thehook = "thehook.cli:main"`, pytest config, dependencies
- [ ] `src/thehook/__init__.py` — version string
- [ ] `src/thehook/cli.py` — Click group skeleton
- [ ] `tests/__init__.py` — empty
- [ ] `tests/conftest.py` — shared `tmp_project` fixture
- [ ] `tests/test_init.py` — covers SETUP-01, SETUP-02
- [ ] `tests/test_config.py` — covers SETUP-03, SETUP-04
- [ ] `.venv/` — `python -m venv .venv && pip install -e ".[dev]"`

---

## Sources

### Primary (HIGH confidence)
- `https://code.claude.com/docs/en/hooks` — Full hooks reference; SessionStart/SessionEnd input/output schemas; matcher values; `hookSpecificOutput.additionalContext` format; `async` flag; `timeout` field; hook file location table. Fetched 2026-02-23.
- `https://code.claude.com/docs/en/settings` — Settings file locations and scopes; `settings.local.json` vs `settings.json` distinction; hook scope. Fetched 2026-02-23.
- Context7 `/pallets/click` — Click groups, commands, CliRunner test pattern, isolated_filesystem. HIGH reputation, 654 snippets.
- Python official docs — `pathlib.Path`, `copy.deepcopy`, `json` module, `yaml.safe_load`.

### Secondary (MEDIUM confidence)
- `https://click.palletsprojects.com/en/stable/entry-points/` — pyproject.toml `[project.scripts]` entry point format. Verified against Context7 Click docs.
- `https://packaging.python.org/en/latest/guides/writing-pyproject-toml/` — pyproject.toml structure with hatchling. Verified by multiple corroborating sources.
- `https://docs.pytest.org/en/stable/how-to/tmp_path.html` — `tmp_path` fixture usage. Current pytest docs.

### Tertiary (LOW confidence)
- None in this research — all critical claims were verified against official sources.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries are pre-decided; versions confirmed from official sources
- Architecture: HIGH — Claude Code hooks API fully documented; Click patterns from Context7; pyproject.toml from official Python packaging docs
- Pitfalls: HIGH — naming discrepancies (knowledge/ vs knowledges/, thehook.yaml vs .thehook/config.yaml) confirmed by reading both REQUIREMENTS.md and implementation plan directly; hook behavior from official docs

**Research date:** 2026-02-23
**Valid until:** 2026-03-25 (stable ecosystem; Claude Code docs may update faster — re-check hooks reference if more than 2 weeks pass)
