"""Documentation regression tests for shared memory references in project docs.

CLAUDE.md was intentionally slimmed down; detailed content moved to
docs/synapse-reference.md.  These tests verify that the reference doc
(or CLAUDE.md, if it still contains the content) documents shared memory.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REFERENCE_DOC = ROOT / "docs" / "synapse-reference.md"
CLAUDE_MD = ROOT / "CLAUDE.md"


def _read_docs() -> str:
    """Return the combined text of CLAUDE.md and the reference doc."""
    parts: list[str] = []
    for p in (CLAUDE_MD, REFERENCE_DOC):
        if p.exists():
            parts.append(p.read_text(encoding="utf-8"))
    return "\n".join(parts)


class TestClaudeSharedMemoryDocs:
    def test_commands_section_includes_shared_memory_commands(self):
        text = _read_docs()

        expected_commands = [
            "synapse memory save",
            "synapse memory list",
            "synapse memory search",
        ]

        for command in expected_commands:
            assert command in text

    def test_architecture_section_includes_shared_memory_module(self):
        text = _read_docs()

        assert "shared_memory.py" in text

    def test_storage_section_includes_shared_memory_db(self):
        text = _read_docs()

        assert "memory.db" in text
