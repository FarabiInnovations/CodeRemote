"""Run a CLI command safely: no stdin, a hard timeout, and no orphaned children.

Some commands print what we need and then never exit (`claude remote-control
--help` prints its help and keeps running). `run` can return as soon as a marker
string appears in the output, and always kills the whole process group when it
gives up.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass


@dataclass
class Result:
    output: str
    returncode: int | None  # None when we killed it
    timed_out: bool
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and not self.timed_out and self.returncode == 0


def _kill_tree(proc: subprocess.Popen) -> None:
    try:
        if sys.platform == "win32":
            proc.kill()
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        pass


def run(argv: list[str], timeout: float = 10.0, until: str | None = None) -> Result:
    """Run argv and capture stdout+stderr.

    If `until` is given, stop as soon as that text appears in the output and
    return what was captured (returncode is None in that case).
    """
    kwargs: dict = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    try:
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            **kwargs,
        )
    except OSError as exc:
        return Result(output="", returncode=None, timed_out=False, error=str(exc))

    chunks: list[str] = []

    def reader() -> None:
        assert proc.stdout is not None
        for raw in iter(lambda: proc.stdout.read1(4096), b""):
            chunks.append(raw.decode("utf-8", errors="replace"))

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()

    deadline = time.monotonic() + timeout
    while True:
        if proc.poll() is not None:
            thread.join(timeout=1)
            return Result(output="".join(chunks), returncode=proc.returncode, timed_out=False)
        if until is not None and until in "".join(chunks):
            _kill_tree(proc)
            proc.wait()
            thread.join(timeout=1)
            return Result(output="".join(chunks), returncode=None, timed_out=False)
        if time.monotonic() >= deadline:
            _kill_tree(proc)
            proc.wait()
            thread.join(timeout=1)
            return Result(output="".join(chunks), returncode=None, timed_out=True)
        time.sleep(0.05)
