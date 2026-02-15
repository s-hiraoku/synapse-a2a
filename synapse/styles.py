"""Shared questionary style for all Synapse TUI menus."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

# ──────────────────────────────────────────────────────────
# simple_term_menu shared constants
# ──────────────────────────────────────────────────────────

TERM_MENU_STYLES: dict[str, Any] = {
    "menu_cursor": "> ",
    "menu_cursor_style": ("fg_yellow", "bold"),
    "menu_highlight_style": ("fg_yellow", "bold"),
    "shortcut_key_highlight_style": ("fg_green", "bold"),
    "shortcut_brackets_highlight_style": ("fg_green",),
    "cycle_cursor": True,
    "clear_screen": True,
}

MENU_SEPARATOR = "───────────────────────────────"


def build_numbered_items(
    labels: list[str],
    footer_items: list[tuple[str, str]] | None = None,
    separator: bool = True,
) -> list[str]:
    """Build ``[N]`` prefixed menu items for *simple_term_menu*.

    Args:
        labels: Item labels to number (1-indexed).
        footer_items: Optional ``(shortcut, label)`` tuples appended after a
            separator line (e.g. ``[("q", "Exit")]``).
        separator: Whether to insert a separator line before *footer_items*.

    Returns:
        List of formatted menu strings.
    """
    width = len(str(len(labels)))
    items = [f"[{i + 1:>{width}}] {label}" for i, label in enumerate(labels)]
    if separator and footer_items:
        items.append(MENU_SEPARATOR)
    if footer_items:
        for shortcut, label in footer_items:
            items.append(f"[{shortcut}] {label}")
    return items


SYNAPSE_STYLE: list[tuple[str, str]] = [
    ("qmark", "fg:ansicyan bold"),
    ("question", "bold"),
    ("pointer", "fg:ansiyellow bold"),
    ("highlighted", "fg:ansiyellow bold"),
    ("answer", "fg:ansicyan bold"),
    ("instruction", "fg:ansicyan"),
    ("separator", "fg:ansicyan"),
]

# Shortcut keys for numbered_choices(). j/k excluded to avoid
# conflict with use_jk_keys=True navigation bindings.
_SHORTCUT_KEYS: list[str] = (
    [str(i) for i in range(1, 10)]
    + ["0"]
    + [chr(c) for c in range(ord("a"), ord("z") + 1) if chr(c) not in ("j", "k")]
)


# Style applied to the number prefix token — keep distinct from highlighted.
SHORTCUT_PREFIX_STYLE = "fg:ansigreen bold"


def numbered_choices(choices: list[Any]) -> list[Any]:
    """Prefix selectable Choice titles with green ``[N]`` and suppress native shortcuts.

    - ``Separator`` instances pass through unchanged.
    - Each ``Choice`` gets ``[1]``, ``[2]``, ... ``[9]``, ``[0]``, ``[a]`` ... ``[z]``
      (j/k skipped) as a green-bold prefix via prompt_toolkit token list.
    - ``get_shortcut_title()`` is overridden to ``""`` so questionary does not
      also render its own ``N) `` prefix.
    - Must be used with ``use_shortcuts=True`` to keep keyboard bindings active.
    - Pair with ``patch_highlight_token_list()`` to apply highlighted style on
      the pointed-at row (questionary skips highlighting for token-list titles).
    """
    from questionary import Choice as QChoice
    from questionary import Separator as QSeparator

    result: list[Any] = []
    idx = 0
    for item in choices:
        if isinstance(item, QSeparator) or not isinstance(item, QChoice):
            result.append(item)
            continue
        if idx < len(_SHORTCUT_KEYS):
            key = _SHORTCUT_KEYS[idx]
            original_title = (
                item.title if isinstance(item.title, str) else str(item.title)
            )
            title_tokens: list[tuple[str, str]] = [
                (SHORTCUT_PREFIX_STYLE, f"[{key}] "),
                ("", original_title),
            ]
            new_choice = QChoice(
                title=title_tokens,
                value=item.value,
                shortcut_key=key,
            )
            # Suppress questionary's native "N) " prefix
            new_choice.get_shortcut_title = lambda: ""  # type: ignore[method-assign,unused-ignore]
            result.append(new_choice)
            idx += 1
        else:
            result.append(item)
    return result


@contextmanager
def patch_highlight_token_list() -> Iterator[None]:
    """Patch questionary so token-list titles get ``class:highlighted`` on the pointed row.

    By default, ``InquirerControl._get_choice_tokens`` calls
    ``tokens.extend(choice.title)`` for token-list titles, ignoring
    ``pointed_at`` entirely.  This patch wraps that method so that
    non-prefix tokens on the pointed row receive ``class:highlighted``.

    The pointer row is identified by scanning for the ``class:pointer``
    token, then restyling tokens from there until the next newline.
    The green ``[N]`` prefix is preserved; only the body text is highlighted.

    Falls back to a no-op if questionary internals are unavailable
    (e.g. when the module is mocked in tests).
    """
    try:
        from questionary.prompts.common import InquirerControl
    except (ImportError, AttributeError):
        yield
        return

    original = InquirerControl._get_choice_tokens

    def _patched(self: Any) -> Any:  # noqa: ANN401
        tokens = original(self)
        if not isinstance(tokens, list):
            return tokens

        # Find the pointer row span: (start_of_pointer_token .. next_newline)
        pointer_start: int | None = None
        pointer_end: int | None = None
        for i, (style, text) in enumerate(tokens):
            if style == "class:pointer":
                pointer_start = i
            elif pointer_start is not None and text == "\n":
                pointer_end = i
                break

        # Fallback: pointer on final line with no trailing newline
        if pointer_start is not None and pointer_end is None:
            pointer_end = len(tokens)

        if pointer_start is None or pointer_end is None:
            return tokens

        # Restyle tokens in the pointer row, keeping prefix style intact
        result = list(tokens)
        for i in range(pointer_start, pointer_end):
            style, text = result[i]
            if (
                style == ""  # unstyled body text
                or style == "class:text"
            ):
                result[i] = ("class:highlighted", text)
        return result

    with patch.object(InquirerControl, "_get_choice_tokens", _patched):
        yield
