from __future__ import annotations

import json
from pathlib import Path


def test_detect_project_context_prefers_pyproject(tmp_path: Path, monkeypatch) -> None:
    from synapse.commands.init_enhanced import detect_project_context

    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\ndependencies = ["fastapi"]\n'
    )
    (tmp_path / "package.json").write_text('{"dependencies":{"react":"^18.0.0"}}')

    result = detect_project_context()

    assert result == {
        "language": "python",
        "framework": "fastapi",
        "detected_from": "pyproject.toml",
    }


def test_detect_project_context_detects_javascript(tmp_path: Path, monkeypatch) -> None:
    from synapse.commands.init_enhanced import detect_project_context

    monkeypatch.chdir(tmp_path)
    (tmp_path / "package.json").write_text('{"dependencies":{"react":"^18.0.0"}}')

    result = detect_project_context()

    assert result == {
        "language": "javascript",
        "framework": "react",
        "detected_from": "package.json",
    }


def test_detect_project_context_returns_empty_when_no_markers(
    tmp_path: Path, monkeypatch
) -> None:
    from synapse.commands.init_enhanced import detect_project_context

    monkeypatch.chdir(tmp_path)

    assert detect_project_context() == {}


def test_save_project_context_persists_under_settings(tmp_path: Path) -> None:
    from synapse.commands.init_enhanced import save_project_context

    synapse_dir = tmp_path / ".synapse"
    synapse_dir.mkdir()
    settings_path = synapse_dir / "settings.json"
    settings_path.write_text(json.dumps({"env": {"FOO": "bar"}}))

    context = {"language": "python", "framework": "fastapi"}
    save_project_context(synapse_dir, context)

    saved = json.loads(settings_path.read_text())
    assert saved["env"] == {"FOO": "bar"}
    assert saved["project_context"] == context
