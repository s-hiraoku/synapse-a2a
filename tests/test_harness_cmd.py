from __future__ import annotations

import io
import tarfile
from argparse import Namespace
from pathlib import Path


def test_cmd_harness_create_writes_template(tmp_path: Path, monkeypatch) -> None:
    from synapse.commands.harness_cmd import cmd_harness_create

    monkeypatch.chdir(tmp_path)

    cmd_harness_create(Namespace(name="demo-harness"))

    manifest_path = tmp_path / "demo-harness" / "harness.yaml"
    assert manifest_path.exists()
    text = manifest_path.read_text(encoding="utf-8")
    assert "name: demo-harness" in text
    assert "contents:" in text


def test_cmd_harness_status_reports_empty_lock(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    from synapse.commands.harness_cmd import cmd_harness_status

    monkeypatch.chdir(tmp_path)

    cmd_harness_status(Namespace(json=False, verbose=False))

    output = capsys.readouterr().out
    assert "Harness Status" in output
    assert "Files managed: 0" in output


def test_cmd_harness_list_prints_installed_harnesses(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    from synapse.commands.harness_cmd import cmd_harness_list
    from synapse.harness import HarnessLock

    monkeypatch.chdir(tmp_path)
    lock = HarnessLock()
    lock.add_harness("base", "local:base", "1.0.0", "abc", ["foo"], 1, True)

    cmd_harness_list(Namespace())

    output = capsys.readouterr().out
    assert "base" in output
    assert "1.0.0" in output


def test_cmd_harness_diff_detects_drift(tmp_path: Path, monkeypatch, capsys) -> None:
    from synapse.commands.harness_cmd import cmd_harness_diff
    from synapse.harness import HarnessLock

    monkeypatch.chdir(tmp_path)
    managed = tmp_path / ".claude" / "skills" / "demo" / "SKILL.md"
    managed.parent.mkdir(parents=True, exist_ok=True)
    managed.write_text("content", encoding="utf-8")
    lock = HarnessLock()
    lock.add_harness(
        "demo",
        "local:demo",
        "1.0.0",
        "abc",
        [str(managed), str(tmp_path / ".agents" / "skills" / "demo" / "SKILL.md")],
        1,
        True,
    )

    cmd_harness_diff(Namespace(name="demo"))

    output = capsys.readouterr().out
    assert "missing" in output.lower()


def test_cmd_harness_diff_reports_clean_when_all_files_exist(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    from synapse.commands.harness_cmd import cmd_harness_diff
    from synapse.harness import HarnessLock

    monkeypatch.chdir(tmp_path)
    files = [
        tmp_path / ".claude" / "skills" / "demo" / "SKILL.md",
        tmp_path / ".agents" / "skills" / "demo" / "SKILL.md",
    ]
    for path in files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("content", encoding="utf-8")
    lock = HarnessLock()
    lock.add_harness(
        "demo", "local:demo", "1.0.0", "abc", [str(path) for path in files], 1, True
    )

    cmd_harness_diff(Namespace(name="demo"))

    output = capsys.readouterr().out
    assert "no drift" in output.lower()


def test_fetch_github_tarball_uses_gh_api(monkeypatch, tmp_path: Path) -> None:
    from synapse.commands.harness_cmd import _fetch_github_tarball

    archive_bytes = io.BytesIO()
    with tarfile.open(fileobj=archive_bytes, mode="w:gz") as tar:
        payload = b"name: demo\nversion: 1.0.0\n"
        info = tarfile.TarInfo(name="user-demo-abc123/harness.yaml")
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    archive_data = archive_bytes.getvalue()

    calls: list[list[str]] = []

    def fake_run(cmd: list[str], check: bool, capture_output: bool) -> object:
        calls.append(cmd)
        tarball_path = Path(cmd[-1])
        tarball_path.write_bytes(archive_data)

        class Result:
            stdout = b""

        return Result()

    monkeypatch.setattr("subprocess.run", fake_run)

    repo_name, version, commit_sha = _fetch_github_tarball("user/demo@v1.0.0", tmp_path)

    assert repo_name == "demo"
    assert version == "v1.0.0"
    assert commit_sha == "user-demo-abc123"
    assert calls
    assert "gh" in calls[0][0]
