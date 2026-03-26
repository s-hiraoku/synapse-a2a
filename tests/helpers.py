"""Shared test helpers for Synapse A2A tests."""

import re
from pathlib import Path


def read_stored_instruction(pty_message: str) -> str:
    """Extract stored file path from PTY reference message and read content.

    Identity instructions are stored in files via LongMessageStore.
    The PTY message contains a reference like:
        [LONG MESSAGE - FILE ATTACHED] Path: /path/to/file.txt — Please read ...

    Returns the stored file content, or the original message if no file ref.
    """
    match = re.search(r"Path: (.+\.txt)", pty_message)
    if match:
        return Path(match.group(1)).read_text()
    return pty_message
