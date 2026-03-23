from __future__ import annotations

import json
from pathlib import Path


def test_harness_manifest_from_dict_with_all_fields() -> None:
    from synapse.harness import HarnessManifest

    manifest = HarnessManifest.from_dict(
        {
            "name": "team-harness",
            "version": "1.2.3",
            "description": "Team defaults",
            "author": "synapse",
            "license": "MIT",
            "agents": ["claude", "codex"],
            "layer_hint": "overlay",
            "compatible_with": ["react-harness"],
            "conflicts_with": ["legacy-harness"],
            "contents": {
                "instructions": [
                    {"src": "instructions/default.md", "target": ".synapse/default.md"}
                ],
                "skills": [{"src": "skills/review", "target": "skills/review"}],
            },
            "dependencies": ["base-harness"],
        }
    )

    assert manifest.name == "team-harness"
    assert manifest.version == "1.2.3"
    assert manifest.description == "Team defaults"
    assert manifest.author == "synapse"
    assert manifest.license == "MIT"
    assert manifest.agents == ["claude", "codex"]
    assert manifest.layer_hint == "overlay"
    assert manifest.compatible_with == ["react-harness"]
    assert manifest.conflicts_with == ["legacy-harness"]
    assert "skills" in manifest.contents
    assert manifest.dependencies == ["base-harness"]


def test_harness_manifest_from_dict_with_minimal_fields() -> None:
    from synapse.harness import HarnessManifest

    manifest = HarnessManifest.from_dict({"name": "minimal", "version": "0.1.0"})

    assert manifest.name == "minimal"
    assert manifest.version == "0.1.0"
    assert manifest.description == ""
    assert manifest.author == ""
    assert manifest.license == ""
    assert manifest.agents == ["claude", "codex", "gemini", "opencode", "copilot"]
    assert manifest.layer_hint == "overlay"
    assert manifest.compatible_with == []
    assert manifest.conflicts_with == []
    assert manifest.contents == {}
    assert manifest.dependencies == []


def test_harness_lock_add_remove_and_get(tmp_path: Path) -> None:
    from synapse.harness import HarnessLock

    lock = HarnessLock(lock_path=tmp_path / "harness-lock.json")
    lock.add_harness(
        name="base",
        source="local:base",
        version="1.0.0",
        commit="abc123",
        files=[".claude/skills/base/SKILL.md"],
        layer=1,
        enabled=True,
    )

    harness = lock.get_harness("base")
    assert harness is not None
    assert harness["source"] == "local:base"
    assert lock.remove_harness("base") is True
    assert lock.get_harness("base") is None


def test_harness_lock_get_active_layers_sorted_and_toggle(tmp_path: Path) -> None:
    from synapse.harness import HarnessLock

    lock = HarnessLock(lock_path=tmp_path / "harness-lock.json")
    lock.add_harness("phase", "local:phase", "1.0.0", "aaa", [], 3, True)
    lock.add_harness("base", "local:base", "1.0.0", "bbb", [], 1, True)
    lock.add_harness("overlay", "local:overlay", "1.0.0", "ccc", [], 2, False)

    active = lock.get_active_layers()

    assert [item["name"] for item in active] == ["base", "phase"]
    assert lock.set_enabled("overlay", True) is True
    active = lock.get_active_layers()
    assert [item["name"] for item in active] == ["base", "overlay", "phase"]


def test_harness_installer_places_files_and_removes_them(tmp_path: Path) -> None:
    from synapse.harness import HarnessInstaller, HarnessManifest

    source_dir = tmp_path / "source"
    (source_dir / "skills" / "review").mkdir(parents=True)
    (source_dir / "skills" / "review" / "SKILL.md").write_text("skill")
    (source_dir / "rules").mkdir(parents=True)
    (source_dir / "rules" / "coding-style.md").write_text("rule")
    (source_dir / "workflows").mkdir(parents=True)
    (source_dir / "workflows" / "review.yaml").write_text("workflow")
    (source_dir / "instructions").mkdir(parents=True)
    (source_dir / "instructions" / "default.md").write_text("instruction")

    manifest = HarnessManifest.from_dict(
        {
            "name": "team-harness",
            "version": "1.0.0",
            "contents": {
                "skills": [{"src": "skills/review", "target": "skills/review"}],
                "rules": [{"src": "rules/coding-style.md"}],
                "workflows": [
                    {"src": "workflows/review.yaml", "target": ".synapse/workflows/"}
                ],
                "instructions": [
                    {"src": "instructions/default.md", "target": ".synapse/default.md"}
                ],
            },
        }
    )

    installer = HarnessInstaller(project_root=tmp_path / "project")
    installed = installer.install_files(manifest, source_dir)

    assert (
        str(tmp_path / "project" / ".claude" / "skills" / "review" / "SKILL.md")
        in installed
    )
    assert (
        str(tmp_path / "project" / ".agents" / "skills" / "review" / "SKILL.md")
        in installed
    )
    assert (
        str(tmp_path / "project" / ".claude" / "rules" / "coding-style.md") in installed
    )
    assert (
        str(tmp_path / "project" / ".synapse" / "workflows" / "review.yaml")
        in installed
    )
    assert str(tmp_path / "project" / ".synapse" / "default.md") in installed

    removed = installer.remove_files(installed)

    assert removed == len(installed)
    for path in installed:
        assert not Path(path).exists()


def test_harness_manifest_from_yaml(tmp_path: Path) -> None:
    from synapse.harness import HarnessManifest

    manifest_path = tmp_path / "harness.yaml"
    manifest_path.write_text(
        "\n".join(
            [
                "name: yaml-harness",
                "version: 0.2.0",
                "agents: [claude, gemini]",
                "contents:",
                "  rules:",
                "    - src: rules/sample.md",
            ]
        )
    )

    manifest = HarnessManifest.from_yaml(manifest_path)

    assert manifest.name == "yaml-harness"
    assert manifest.version == "0.2.0"
    assert manifest.agents == ["claude", "gemini"]


def test_harness_lock_persists_json(tmp_path: Path) -> None:
    from synapse.harness import HarnessLock

    lock_path = tmp_path / "harness-lock.json"
    lock = HarnessLock(lock_path=lock_path)
    lock.add_harness("base", "local:base", "1.0.0", "abc", ["foo"], 1, True)

    saved = json.loads(lock_path.read_text())

    assert saved["harnesses"]["base"]["version"] == "1.0.0"
