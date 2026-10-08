import sys
import time

from coderemote import runner

PY = sys.executable


def test_captures_output_and_exit_code():
    res = runner.run([PY, "-c", "print('hello')"], timeout=10)
    assert res.ok and res.output.strip() == "hello"


def test_hanging_command_is_killed_at_timeout():
    start = time.monotonic()
    res = runner.run([PY, "-c", "import time; print('partial', flush=True); time.sleep(30)"], timeout=1)
    assert res.timed_out and not res.ok
    assert "partial" in res.output  # output printed before the hang is kept
    assert time.monotonic() - start < 5


def test_until_returns_as_soon_as_marker_appears():
    # Mimics `claude remote-control --help`: prints the help, then never exits.
    start = time.monotonic()
    res = runner.run([PY, "-c", "import time; print('--spawn <mode>', flush=True); time.sleep(30)"],
                     timeout=10, until="--spawn")
    assert not res.timed_out and "--spawn" in res.output
    assert time.monotonic() - start < 5


def test_missing_program_reports_error():
    res = runner.run(["/nonexistent/definitely-not-here"], timeout=5)
    assert res.error and not res.ok
