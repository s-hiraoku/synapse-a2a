"""CLI integration tests for gRPC server startup (issue #22)."""

import argparse
from unittest.mock import MagicMock, mock_open, patch

from synapse.commands.start import StartCommand


def test_start_command_passes_grpc_flags_to_server() -> None:
    subprocess_module = MagicMock()
    process = MagicMock()
    process.poll.return_value = None
    process.pid = 12345
    subprocess_module.Popen.return_value = process

    args = argparse.Namespace(
        profile="dummy",
        port=8100,
        foreground=False,
        ssl_cert=None,
        ssl_key=None,
        grpc=True,
        grpc_port=9100,
        tool_args=[],
    )

    with (
        patch("builtins.open", mock_open()),
        patch("os.makedirs"),
        patch("time.sleep"),
    ):
        StartCommand(subprocess_module=subprocess_module).run(args)

    cmd = subprocess_module.Popen.call_args.args[0]
    assert "--grpc" in cmd
    assert "--grpc-port" in cmd
    assert "9100" in cmd


def test_start_help_documents_grpc_flag() -> None:
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "synapse.cli", "start", "--help"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "--grpc" in result.stdout
    assert "--grpc-port" in result.stdout
