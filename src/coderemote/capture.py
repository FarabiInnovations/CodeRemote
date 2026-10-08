"""Run a command and keep only the start of its output in a log file.

    python -m coderemote.capture <log> <max_bytes> -- <command> [args...]

`claude remote-control` redraws its status screen every couple of seconds and Codex logs
heavily, so writing their output straight to a file would grow it without end. This
wrapper copies the first `max_bytes` (enough for the "Connected" line, the session link,
or the error) into the log, then reads and discards the rest so the command never blocks
on a full pipe. It exits with the command's exit code.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys


def copy_capped(src, dst, limit: int) -> None:
    written = 0
    while True:
        chunk = src.read1(65536) if hasattr(src, "read1") else src.read(65536)
        if not chunk:
            return
        if written < limit:
            part = chunk[: limit - written]
            dst.write(part)
            dst.flush()
            written += len(part)


def main(argv: list[str]) -> int:
    if len(argv) < 4 or argv[2] != "--":
        print(__doc__, file=sys.stderr)
        return 2
    log_path, limit, command = argv[0], int(argv[1]), argv[3:]

    fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as log:
        try:
            child = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        except OSError as exc:
            log.write(f"Error: could not start {command[0]}: {exc}\n".encode())
            return 127

        # Pass a stop request on to the command so it can shut down cleanly.
        def forward(signum, _frame):
            try:
                child.send_signal(signum)
            except OSError:
                pass

        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, forward)

        assert child.stdout is not None
        copy_capped(child.stdout, log, limit)
        code = child.wait()
        return 128 - code if code < 0 else code  # killed by a signal -> shell-style 128+N


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
