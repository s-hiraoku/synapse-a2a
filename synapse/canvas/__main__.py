"""Allow ``python -m synapse.canvas`` to start the Canvas server."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

import uvicorn

from synapse.canvas.server import create_app
from synapse.config import CANVAS_DEFAULT_PORT

parser = argparse.ArgumentParser(description="Synapse Canvas Server")
parser.add_argument("--port", type=int, default=CANVAS_DEFAULT_PORT)
args = parser.parse_args()

# Log startup to stderr (captured to log file by auto-start)
now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
print(
    f"[{now}] Canvas server starting on port {args.port} (pid={__import__('os').getpid()})",
    file=sys.stderr,
)

app = create_app()
uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="info")
