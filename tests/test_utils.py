"""Tests for synapse/utils.py utility functions."""

import re
from datetime import datetime, timezone
from unittest.mock import MagicMock

from synapse.utils import extract_text_from_parts, format_a2a_message, get_iso_timestamp


class TestExtractTextFromParts:
    """Tests for extract_text_from_parts function."""

    def test_empty_list_returns_empty_string(self):
        """Should return empty string for empty list."""
        result = extract_text_from_parts([])
        assert result == ""

    def test_single_text_part_dict(self):
        """Should extract text from single dict part."""
        parts = [{"type": "text", "text": "Hello world"}]
        result = extract_text_from_parts(parts)
        assert result == "Hello world"

    def test_multiple_text_parts_dict(self):
        """Should join multiple text parts with newlines."""
        parts = [
            {"type": "text", "text": "Line 1"},
            {"type": "text", "text": "Line 2"},
            {"type": "text", "text": "Line 3"},
        ]
        result = extract_text_from_parts(parts)
        assert result == "Line 1\nLine 2\nLine 3"

    def test_ignores_non_text_parts(self):
        """Should ignore parts that are not text type."""
        parts = [
            {"type": "text", "text": "Text part"},
            {"type": "file", "uri": "file://test.txt"},
            {"type": "data", "data": {"key": "value"}},
        ]
        result = extract_text_from_parts(parts)
        assert result == "Text part"

    def test_ignores_dict_without_text_key(self):
        """Should ignore dict parts without 'text' key."""
        parts = [
            {"type": "text", "text": "Valid"},
            {"type": "text", "content": "Missing text key"},
        ]
        result = extract_text_from_parts(parts)
        assert result == "Valid"

    def test_pydantic_model_parts(self):
        """Should extract text from Pydantic model objects."""
        # Create mock Pydantic objects
        text_part = MagicMock()
        text_part.type = "text"
        text_part.text = "Pydantic text"

        file_part = MagicMock()
        file_part.type = "file"
        file_part.text = "Should be ignored"

        parts = [text_part, file_part]
        result = extract_text_from_parts(parts)
        assert result == "Pydantic text"

    def test_mixed_dict_and_model_parts(self):
        """Should handle mixed dict and model parts."""
        text_model = MagicMock()
        text_model.type = "text"
        text_model.text = "From model"

        parts = [
            {"type": "text", "text": "From dict"},
            text_model,
        ]
        result = extract_text_from_parts(parts)
        assert result == "From dict\nFrom model"

    def test_empty_text_parts(self):
        """Should include empty text parts."""
        parts = [
            {"type": "text", "text": ""},
            {"type": "text", "text": "Not empty"},
        ]
        result = extract_text_from_parts(parts)
        assert result == "\nNot empty"

    def test_unicode_text(self):
        """Should handle unicode text correctly."""
        parts = [
            {"type": "text", "text": "日本語テスト"},
            {"type": "text", "text": "Émoji: 🎉"},
        ]
        result = extract_text_from_parts(parts)
        assert result == "日本語テスト\nÉmoji: 🎉"


class TestFormatA2AMessage:
    """Tests for format_a2a_message function."""

    def test_basic_format(self):
        """Should format message with A2A prefix."""
        result = format_a2a_message("Hello")
        assert result == "A2A: Hello"

    def test_empty_content(self):
        """Should handle empty content."""
        result = format_a2a_message("")
        assert result == "A2A: "

    def test_multiline_content(self):
        """Should preserve multiline content."""
        result = format_a2a_message("Line 1\nLine 2")
        assert result == "A2A: Line 1\nLine 2"

    def test_content_with_special_characters(self):
        """Should handle special characters in content."""
        result = format_a2a_message("[INFO] Test: value")
        assert result == "A2A: [INFO] Test: value"

    def test_response_expected_true(self):
        """Should include [REPLY EXPECTED] marker when response_expected=True."""
        result = format_a2a_message("What is the status?", response_expected=True)
        assert result == "A2A: [REPLY EXPECTED] What is the status?"

    def test_response_expected_false(self):
        """Should not include marker when response_expected=False."""
        result = format_a2a_message("FYI: done", response_expected=False)
        assert result == "A2A: FYI: done"

    def test_response_expected_default(self):
        """Should not include marker by default (response_expected=False)."""
        result = format_a2a_message("Hello")
        assert result == "A2A: Hello"
        assert "[REPLY EXPECTED]" not in result


class TestGetIsoTimestamp:
    """Tests for get_iso_timestamp function."""

    def test_returns_string(self):
        """Should return a string."""
        result = get_iso_timestamp()
        assert isinstance(result, str)

    def test_ends_with_z(self):
        """Should end with 'Z' suffix for UTC."""
        result = get_iso_timestamp()
        assert result.endswith("Z")

    def test_iso_format(self):
        """Should be valid ISO 8601 format."""
        result = get_iso_timestamp()
        # Remove Z suffix and parse
        timestamp_str = result[:-1]
        # Should not raise
        parsed = datetime.fromisoformat(timestamp_str)
        assert parsed is not None

    def test_no_timezone_offset(self):
        """Should not contain timezone offset (only Z)."""
        result = get_iso_timestamp()
        # Should not have +00:00 or similar
        assert "+00:00" not in result
        assert "-00:00" not in result
        # Pattern: YYYY-MM-DDTHH:MM:SS.microsZ
        pattern = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z$"
        assert re.match(pattern, result)

    def test_microseconds_included(self):
        """Should include microseconds."""
        result = get_iso_timestamp()
        # Should have decimal point before Z
        assert "." in result

    def test_unique_timestamps(self):
        """Consecutive calls should produce different timestamps (or same within precision)."""
        # Call multiple times rapidly
        timestamps = [get_iso_timestamp() for _ in range(10)]
        # Not all should be identical (though some might be due to timing)
        # At least check format is consistent
        for ts in timestamps:
            assert ts.endswith("Z")
            assert "T" in ts

    def test_timestamp_is_recent(self):
        """Generated timestamp should be close to current time."""
        before = datetime.now(timezone.utc).replace(tzinfo=None)
        result = get_iso_timestamp()
        after = datetime.now(timezone.utc).replace(tzinfo=None)

        # Parse result
        timestamp_str = result[:-1]  # Remove Z
        parsed = datetime.fromisoformat(timestamp_str)

        # Should be between before and after
        assert before <= parsed <= after
