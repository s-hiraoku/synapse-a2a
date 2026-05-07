"""Documentation checks for reply usage clarification (#185)."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_reply_docs_distinguish_tracked_messages_from_user_pasted_text() -> None:
    """Docs should explain when to use reply versus send."""
    targets = [
        REPO_ROOT / "README.md",
        REPO_ROOT / "guides" / "references.md",
        REPO_ROOT / "site-docs" / "reference" / "cli.md",
    ]
    required = [
        "Synapse-tracked incoming message",
        "user-pasted A2A text",
        "use `synapse send`",
    ]
    missing: list[str] = []
    for path in targets:
        body = path.read_text(encoding="utf-8")
        for token in required:
            if token not in body:
                missing.append(f"{path.relative_to(REPO_ROOT)}: {token}")

    assert not missing, "Missing reply usage clarification:\n" + "\n".join(missing)
