"""Documentation checks for save-on-exit agent definition prompt."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

DOC_TARGETS = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "guides" / "usage.md",
    REPO_ROOT / "guides" / "references.md",
    REPO_ROOT / "docs" / "README.md",
    REPO_ROOT / "site-docs" / "reference" / "cli.md",
    REPO_ROOT / "site-docs" / "guide" / "agent-management.md",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_save_on_exit_prompt_is_documented_in_key_docs() -> None:
    """Key docs should explain when save-on-exit prompt appears."""
    missing: list[str] = []

    required_tokens = [
        "Save this agent definition for reuse? [y/N]:",
        "headless",
        "synapse stop",
        "synapse kill",
    ]

    for doc in DOC_TARGETS:
        body = _read(doc)
        for token in required_tokens:
            if token not in body:
                missing.append(f"{doc.relative_to(REPO_ROOT)}: {token}")

    assert not missing, "Missing save prompt docs:\n" + "\n".join(missing)
