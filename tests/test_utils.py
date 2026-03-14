"""Tests for synapse/utils.py utility functions."""

import re
from datetime import datetime, timezone
from unittest.mock import MagicMock

from synapse.utils import (
    extract_file_parts,
    extract_text_from_parts,
    format_a2a_message,
    get_iso_timestamp,
)


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

    def test_response_mode_wait(self):
        """Should include [REPLY EXPECTED] marker when response_mode='wait'."""
        result = format_a2a_message("What is the status?", response_mode="wait")
        assert result == "A2A: [REPLY EXPECTED] What is the status?"

    def test_response_mode_notify(self):
        """Should not include marker when response_mode='notify'."""
        result = format_a2a_message("Task started", response_mode="notify")
        assert result == "A2A: Task started"
        assert "[REPLY EXPECTED]" not in result

    def test_response_mode_silent(self):
        """Should not include marker when response_mode='silent'."""
        result = format_a2a_message("FYI: done", response_mode="silent")
        assert result == "A2A: FYI: done"

    def test_response_mode_default(self):
        """Should not include marker by default (response_mode='silent')."""
        result = format_a2a_message("Hello")
        assert result == "A2A: Hello"
        assert "[REPLY EXPECTED]" not in result

    # --- Dedup tests (Bug 1: LLM echoes [REPLY EXPECTED] causing duplication) ---

    def test_dedup_reply_expected_when_content_already_has_marker(self):
        """Should not duplicate [REPLY EXPECTED] when content already contains it."""
        result = format_a2a_message(
            "[REPLY EXPECTED] What is the status?", response_mode="wait"
        )
        assert result == "A2A: [REPLY EXPECTED] What is the status?"
        # Must NOT be "A2A: [REPLY EXPECTED] [REPLY EXPECTED] What is the status?"
        assert result.count("[REPLY EXPECTED]") == 1

    def test_dedup_preserves_marker_when_no_response(self):
        """Should preserve [REPLY EXPECTED] in content when response_mode='silent'.

        This is important for the long-message file-reference flow where
        format_file_reference() embeds [REPLY EXPECTED] in the content and
        format_a2a_message is called with response_mode='silent'.
        """
        result = format_a2a_message(
            "[REPLY EXPECTED] Just info", response_mode="silent"
        )
        assert result == "A2A: [REPLY EXPECTED] Just info"

    def test_dedup_reply_expected_with_extra_whitespace(self):
        """Should handle [REPLY EXPECTED] with trailing whitespace in content."""
        result = format_a2a_message("[REPLY EXPECTED]   Hello", response_mode="wait")
        assert result == "A2A: [REPLY EXPECTED] Hello"
        assert result.count("[REPLY EXPECTED]") == 1

    def test_dedup_does_not_strip_mid_content_marker(self):
        """Should only strip leading [REPLY EXPECTED], not mid-content occurrences."""
        result = format_a2a_message(
            "Check [REPLY EXPECTED] marker", response_mode="silent"
        )
        assert result == "A2A: Check [REPLY EXPECTED] marker"


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


class TestExtractFilePartsExceptionHandling:
    """Tests for extract_file_parts exception narrowing."""

    def test_model_dump_type_error_returns_none(self):
        """Should catch TypeError from model_dump() and skip the part."""
        obj = MagicMock()
        obj.model_dump.side_effect = TypeError("bad args")
        del obj.dict  # Ensure dict fallback is not tried
        obj.type = "other"

        result = extract_file_parts([obj])
        assert result == []

    def test_model_dump_value_error_returns_none(self):
        """Should catch ValueError from model_dump() and skip the part."""
        obj = MagicMock()
        obj.model_dump.side_effect = ValueError("invalid")
        del obj.dict
        obj.type = "other"

        result = extract_file_parts([obj])
        assert result == []

    def test_model_dump_attribute_error_returns_none(self):
        """Should catch AttributeError from model_dump() and skip the part."""
        obj = MagicMock()
        obj.model_dump.side_effect = AttributeError("missing")
        del obj.dict
        obj.type = "other"

        result = extract_file_parts([obj])
        assert result == []

    def test_dict_method_type_error_returns_none(self):
        """Should catch TypeError from dict() and skip the part."""
        obj = MagicMock(spec=[])
        obj.dict = MagicMock(side_effect=TypeError("bad"))
        obj.type = "other"

        result = extract_file_parts([obj])
        assert result == []

    def test_dict_method_value_error_returns_none(self):
        """Should catch ValueError from dict() and skip the part."""
        obj = MagicMock(spec=[])
        obj.dict = MagicMock(side_effect=ValueError("invalid"))
        obj.type = "other"

        result = extract_file_parts([obj])
        assert result == []

    def test_uncaught_exceptions_propagate(self):
        """Exceptions outside the narrowed set should propagate."""
        obj = MagicMock()
        obj.model_dump.side_effect = RuntimeError("unexpected")

        with MagicMock():
            import pytest

            with pytest.raises(RuntimeError, match="unexpected"):
                extract_file_parts([obj])
