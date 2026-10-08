"""`coderemote` command: start the daemon."""

from __future__ import annotations

import argparse
import os

import uvicorn

from coderemote.config import config_dir, load_or_create_token
from coderemote.server import create_app

DEFAULT_PORT = 8765  # 3333 is reserved for Playwright


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="coderemote", description=__doc__)
    parser.add_argument("--host", default=os.environ.get("CODEREMOTE_HOST", "127.0.0.1"),
                        help="address to listen on (default: 127.0.0.1, this machine only)")
    parser.add_argument("--port", type=int, default=int(os.environ.get("CODEREMOTE_PORT", DEFAULT_PORT)))
    args = parser.parse_args(argv)

    token = load_or_create_token()
    shown_host = "127.0.0.1" if args.host in ("0.0.0.0", "::") else args.host
    print(f"CodeRemote settings: {config_dir()}", flush=True)
    print(f"Open: http://{shown_host}:{args.port}/#token={token}", flush=True)
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print("Warning: listening beyond this machine. Anyone who reaches this port and has the "
              "token can start agents here; keep it behind a VPN such as Tailscale.", flush=True)

    uvicorn.run(create_app(token), host=args.host, port=args.port, log_level="warning")
