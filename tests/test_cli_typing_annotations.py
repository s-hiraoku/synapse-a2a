"""Typing-related tests for CLI helpers."""

from __future__ import annotations

from collections.abc import Callable
from typing import get_args, get_origin, get_type_hints

from synapse.cli import _maybe_prompt_save_agent_profile


def test_save_prompt_input_func_annotation_is_callable_string_to_string() -> None:
    """input_func should be typed as Callable[[str], str] for type checker compatibility."""
    hints = get_type_hints(_maybe_prompt_save_agent_profile)
    input_func_hint = hints["input_func"]

    assert get_origin(input_func_hint) is Callable
    arg_types, return_type = get_args(input_func_hint)
    assert arg_types == [str]
    assert return_type is str
