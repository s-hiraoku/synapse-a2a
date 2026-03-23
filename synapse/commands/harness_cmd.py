"""CLI helpers for harness management."""

from __future__ import annotations

import json
import subprocess
import tarfile
import tempfile
from pathlib import Path
from typing import Any

from synapse.harness import HarnessInstaller, HarnessLock, HarnessManifest


def _parse_source(source: str) -> tuple[str, str, str]:
    owner_repo, _, version = source.partition("@")
    owner, repo = owner_repo.split("/", 1)
    return owner, repo, version or "HEAD"


def _fetch_github_tarball(source: str, dest_dir: str | Path) -> tuple[str, str, str]:
    """Fetch a GitHub tarball via gh api and extract it."""
    owner, repo, version = _parse_source(source)
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    tarball_path = dest / "repo.tar.gz"
    subprocess.run(
        [
            "gh",
            "api",
            f"repos/{owner}/{repo}/tarball/{version}",
            "--output",
            str(tarball_path),
        ],
        check=True,
        capture_output=True,
    )

    with tarfile.open(tarball_path, mode="r:gz") as archive:
        archive.extractall(dest)
        first_member = next(
            (
                member
                for member in archive.getmembers()
                if member.name and "/" in member.name
            ),
            None,
        )
    commit_sha = first_member.name.split("/", 1)[0] if first_member else repo
    return repo, version, commit_sha


def cmd_harness_install(args: Any) -> None:
    """Install a harness from a GitHub source."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo_name, version, commit_sha = _fetch_github_tarball(args.source, tmp_dir)
        extracted_root = next(Path(tmp_dir).iterdir())
        manifest = HarnessManifest.from_yaml(extracted_root / "harness.yaml")
        installer = HarnessInstaller()
        installed = installer.install_files(manifest, extracted_root)
        HarnessLock().add_harness(
            name=manifest.name,
            source=args.source,
            version=version,
            commit=commit_sha,
            files=installed,
            layer=len(HarnessLock().load().get("harnesses", {})) + 1,
            enabled=True,
        )
        print(f"Installed {repo_name} ({version})")


def cmd_harness_list(args: Any) -> None:
    """List installed harnesses."""
    del args
    harnesses = HarnessLock().load().get("harnesses", {})
    if not harnesses:
        print("No harnesses installed.")
        return
    for harness in harnesses.values():
        print(
            f"{harness['name']}  {harness['version']}  "
            f"L{harness['layer']}  {'enabled' if harness['enabled'] else 'disabled'}"
        )


def cmd_harness_use(args: Any) -> None:
    """Switch active harness layers."""
    raise NotImplementedError("harness use is not implemented in Phase 2 tests")


def cmd_harness_disable(args: Any) -> None:
    """Disable a harness while retaining its lock entry."""
    raise NotImplementedError("harness disable is not implemented in Phase 2 tests")


def cmd_harness_enable(args: Any) -> None:
    """Re-enable a disabled harness."""
    raise NotImplementedError("harness enable is not implemented in Phase 2 tests")


def cmd_harness_status(args: Any) -> None:
    """Show current harness status."""
    lock = HarnessLock()
    active = lock.get_active_layers()
    if getattr(args, "json", False):
        print(json.dumps({"active_layers": active}, ensure_ascii=False, indent=2))
        return

    managed_files = sum(len(item.get("files", [])) for item in active)
    print("Harness Status")
    print("══════════════════════════════════════════")
    print("  Active layers:")
    for item in reversed(active):
        print(
            f"    L{item['layer']}  {item['name']}  {item['version']}  "
            f"{'✔ active' if item['enabled'] else '(disabled)'}"
        )
    print(f"  Files managed: {managed_files}")


def cmd_harness_remove(args: Any) -> None:
    """Remove a harness from the lockfile and filesystem."""
    raise NotImplementedError("harness remove is not implemented in Phase 2 tests")


def cmd_harness_diff(args: Any) -> None:
    """Check for missing managed files."""
    harness = HarnessLock().get_harness(args.name)
    if not harness:
        print(f"Harness not found: {args.name}")
        return
    missing = [path for path in harness.get("files", []) if not Path(path).exists()]
    if not missing:
        print(f"{args.name}: no drift detected")
        return
    print(f"{args.name}: drift detected")
    for path in missing:
        print(f"  missing: {path}")


def cmd_harness_create(args: Any) -> None:
    """Create a new harness template directory."""
    root = Path.cwd() / str(args.name)
    root.mkdir(parents=True, exist_ok=True)
    (root / "skills").mkdir(exist_ok=True)
    (root / "rules").mkdir(exist_ok=True)
    (root / "workflows").mkdir(exist_ok=True)
    harness_yaml = "\n".join(
        [
            f"name: {args.name}",
            "version: 0.1.0",
            "description: ''",
            "author: ''",
            "license: MIT",
            "contents:",
            "  instructions: []",
            "  skills: []",
            "  rules: []",
            "  workflows: []",
            "dependencies: []",
            "",
        ]
    )
    (root / "harness.yaml").write_text(harness_yaml, encoding="utf-8")
    print(f"Created harness template at {root}")
