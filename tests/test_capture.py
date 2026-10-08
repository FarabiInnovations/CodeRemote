import os
import signal
import subprocess
import sys
import time

import pytest

from coderemote import capture


def run_capture(tmp_path, limit, script):
    log = tmp_path / "out.log"
    proc = subprocess.run([sys.executable, "-I", capture.__file__, str(log), str(limit), "--",
                           sys.executable, "-c", script], timeout=30)
    return proc.returncode, log


def test_keeps_only_the_first_bytes_and_drains_the_rest(tmp_path):
    # 2 MB of output: more than a pipe buffer, so a wrapper that stopped reading would hang.
    code, log = run_capture(tmp_path, 1000, "import sys; sys.stdout.write('x' * 2_000_000); sys.exit(3)")
    assert code == 3
    assert log.stat().st_size == 1000


def test_log_is_private(tmp_path):
    _, log = run_capture(tmp_path, 100, "print('hi')")
    if os.name == "posix":
        assert (log.stat().st_mode & 0o777) == 0o600
    assert log.read_text() == "hi\n"


def test_missing_command_is_logged(tmp_path):
    log = tmp_path / "out.log"
    code = subprocess.run([sys.executable, "-I", capture.__file__, str(log), "100", "--",
                           "/nonexistent/tool"]).returncode
    assert code == 127
    assert "could not start" in log.read_text()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
def test_stop_signal_reaches_the_command(tmp_path):
    log = tmp_path / "out.log"
    script = ("import signal, sys, time\n"
              "signal.signal(signal.SIGTERM, lambda *a: (print('got TERM', flush=True), sys.exit(0)))\n"
              "print('ready', flush=True)\n"
              "time.sleep(30)\n")
    proc = subprocess.Popen([sys.executable, "-I", capture.__file__, str(log), "1000", "--",
                             sys.executable, "-c", script])
    for _ in range(100):
        if log.exists() and "ready" in log.read_text():
            break
        time.sleep(0.05)
    proc.send_signal(signal.SIGTERM)
    assert proc.wait(timeout=10) == 0
    assert "got TERM" in log.read_text()
