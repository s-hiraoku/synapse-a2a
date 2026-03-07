"""Allow ``python -m synapse.canvas`` to start the Canvas server."""

from __future__ import annotations

import argparse

import uvicorn

from synapse.canvas.server import create_app
from synapse.config import CANVAS_DEFAULT_PORT

parser = argparse.ArgumentParser(description="Synapse Canvas Server")
parser.add_argument("--port", type=int, default=CANVAS_DEFAULT_PORT)
args = parser.parse_args()

app = create_app()
uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="warning")
