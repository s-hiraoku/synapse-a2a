"""
Tests for --attach file attachment support in synapse send.

Phase 3: File attachment via --attach / -a
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Phase 3: _process_attachments (tools/a2a.py)
# ---------------------------------------------------------------------------
class TestProcessAttachments:
    """Tests for _process_attachments() in synapse/tools/a2a.py."""

    def test_single_file_copy(self, tmp_path):
        """Single attachment is copied to staging directory."""
        from synapse.tools.a2a import _process_attachments

        src = tmp_path / "hello.py"
        src.write_text("print('hello')", encoding="utf-8")
        parts = _process_attachments([str(src)])
        assert len(parts) == 1
        # Check the staged file exists at the URI
        uri = parts[0]["file"]["uri"]
        assert uri.startswith("file://")
        staged_path = Path(uri.replace("file://", ""))
        assert staged_path.exists()
        assert staged_path.read_text(encoding="utf-8") == "print('hello')"

    def test_file_part_structure(self, tmp_path):
        """FilePart dict has correct A2A structure."""
        from synapse.tools.a2a import _process_attachments

        src = tmp_path / "data.json"
        src.write_text('{"key": "value"}', encoding="utf-8")
        parts = _process_attachments([str(src)])
        part = parts[0]
        assert part["type"] == "file"
        assert "file" in part
        assert part["file"]["name"] == "data.json"
        assert part["file"]["uri"].startswith("file://")

    def test_multiple_files(self, tmp_path):
        """Multiple attachments are all processed."""
        from synapse.tools.a2a import _process_attachments

        files = []
        for i in range(3):
            f = tmp_path / f"file{i}.txt"
            f.write_text(f"content {i}", encoding="utf-8")
            files.append(str(f))
        parts = _process_attachments(files)
        assert len(parts) == 3

    def test_nonexistent_file_error(self):
        """Nonexistent file raises SystemExit."""
        from synapse.tools.a2a import _process_attachments

        with pytest.raises(SystemExit):
            _process_attachments(["/nonexistent/file.txt"])


# ---------------------------------------------------------------------------
# Phase 3: extract_file_parts (utils.py)
# ---------------------------------------------------------------------------
class TestExtractFileParts:
    """Tests for extract_file_parts() in synapse/utils.py."""

    def test_extract_from_dicts(self):
        """Extracts FilePart dicts from mixed parts list."""
        from synapse.utils import extract_file_parts

        parts = [
            {"type": "text", "text": "hello"},
            {"type": "file", "file": {"name": "a.py", "uri": "file:///tmp/a.py"}},
            {"type": "text", "text": "world"},
        ]
        file_parts = extract_file_parts(parts)
        assert len(file_parts) == 1
        assert file_parts[0]["file"]["name"] == "a.py"

    def test_extract_from_pydantic(self):
        """Extracts FilePart from Pydantic-like objects."""
        from synapse.utils import extract_file_parts

        class FakeFilePart:
            type = "file"
            file = MagicMock(name="b.py", uri="file:///tmp/b.py")

        class FakeTextPart:
            type = "text"
            text = "hello"

        parts = [FakeTextPart(), FakeFilePart()]
        file_parts = extract_file_parts(parts)
        assert len(file_parts) == 1

    def test_no_file_parts(self):
        """Returns empty list when no file parts."""
        from synapse.utils import extract_file_parts

        parts = [
            {"type": "text", "text": "hello"},
        ]
        file_parts = extract_file_parts(parts)
        assert file_parts == []


# ---------------------------------------------------------------------------
# Phase 3: format_file_parts_for_pty (utils.py)
# ---------------------------------------------------------------------------
class TestFormatFilePartsForPty:
    """Tests for format_file_parts_for_pty() in synapse/utils.py."""

    def test_format_single_file(self):
        """Single file part is formatted correctly."""
        from synapse.utils import format_file_parts_for_pty

        file_parts = [
            {"type": "file", "file": {"name": "main.py", "uri": "file:///tmp/main.py"}},
        ]
        result = format_file_parts_for_pty(file_parts)
        assert "[ATTACHMENTS]" in result
        assert "main.py" in result
        assert "file:///tmp/main.py" in result

    def test_format_multiple_files(self):
        """Multiple file parts are all listed."""
        from synapse.utils import format_file_parts_for_pty

        file_parts = [
            {"type": "file", "file": {"name": "a.py", "uri": "file:///tmp/a.py"}},
            {"type": "file", "file": {"name": "b.py", "uri": "file:///tmp/b.py"}},
        ]
        result = format_file_parts_for_pty(file_parts)
        assert "a.py" in result
        assert "b.py" in result

    def test_format_empty(self):
        """Empty list returns empty string."""
        from synapse.utils import format_file_parts_for_pty

        assert format_file_parts_for_pty([]) == ""
