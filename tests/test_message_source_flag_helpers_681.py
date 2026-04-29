"""Regression tests for narrow message source flag helpers (#681)."""

import argparse

import pytest


def test_add_text_input_flags_adds_message_file_and_stdin():
    from synapse.tools.a2a_helpers import _add_text_input_flags

    parser = argparse.ArgumentParser()
    _add_text_input_flags(parser)

    args = parser.parse_args(["--message-file", "/tmp/a.txt"])
    assert args.message_file == "/tmp/a.txt"

    args = parser.parse_args(["--stdin"])
    assert args.stdin is True

    with pytest.raises(SystemExit):
        parser.parse_args(["--attach", "x"])


def test_add_attachments_flag_adds_attach_only():
    from synapse.tools.a2a_helpers import _add_attachments_flag

    parser = argparse.ArgumentParser()
    _add_attachments_flag(parser)

    args = parser.parse_args(["-a", "f1", "-a", "f2"])
    assert args.attach == ["f1", "f2"]

    with pytest.raises(SystemExit):
        parser.parse_args(["--message-file", "/tmp/a.txt"])


def test_add_task_file_flag_adds_task_file_only():
    from synapse.tools.a2a_helpers import _add_task_file_flag

    parser = argparse.ArgumentParser()
    _add_task_file_flag(parser)

    args = parser.parse_args(["-T", "/tmp/t.md"])
    assert args.task_file == "/tmp/t.md"

    with pytest.raises(SystemExit):
        parser.parse_args(["--message-file", "/tmp/a.txt"])


def test_legacy_add_message_source_flags_still_bundles_all_four():
    from synapse.tools.a2a_helpers import _add_message_source_flags

    parser = argparse.ArgumentParser()
    _add_message_source_flags(parser)

    args = parser.parse_args(
        [
            "--message-file",
            "/tmp/a.txt",
            "--task-file",
            "/tmp/t.md",
            "--stdin",
            "--attach",
            "f1",
            "--attach",
            "f2",
        ]
    )

    assert args.message_file == "/tmp/a.txt"
    assert args.task_file == "/tmp/t.md"
    assert args.stdin is True
    assert args.attach == ["f1", "f2"]


@pytest.mark.parametrize("rejected_flag", ["--attach", "--task-file"])
def test_p_reply_rejects_attach_and_task_file(rejected_flag, monkeypatch):
    from synapse.tools import a2a

    monkeypatch.setattr("sys.argv", ["synapse", "reply", rejected_flag, "x"])

    with pytest.raises(SystemExit):
        a2a.main()
