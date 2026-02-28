"""Documentation regression tests for shared memory references in CLAUDE.md."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLAUDE_MD = ROOT / "CLAUDE.md"


def _read_claude_md() -> str:
    return CLAUDE_MD.read_text(encoding="utf-8")


class TestClaudeSharedMemoryDocs:
    def test_commands_section_includes_shared_memory_commands(self):
        text = _read_claude_md()

        expected_commands = [
            "synapse memory save <key> <content> [--tags tag1,tag2] [--notify]",
            "synapse memory list [--author <id>] [--tags <tags>] [--limit <n>]",
            "synapse memory show <id_or_key>",
            "synapse memory search <query>",
            "synapse memory delete <id_or_key> [--force]",
            "synapse memory stats",
        ]

        for command in expected_commands:
            assert command in text

    def test_commands_section_includes_shared_memory_test_commands(self):
        text = _read_claude_md()

        expected_tests = [
            "pytest tests/test_shared_memory.py -v",
            "pytest tests/test_cli_memory.py -v",
            "pytest tests/test_memory_api.py -v",
        ]

        for test_command in expected_tests:
            assert test_command in text

    def test_architecture_section_includes_shared_memory_module(self):
        text = _read_claude_md()

        assert "shared_memory.py" in text

    def test_storage_section_includes_shared_memory_db(self):
        text = _read_claude_md()

        assert ".synapse/memory.db" in text
