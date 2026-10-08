"""Which operating system the daemon is running on."""

from __future__ import annotations

import platform
from pathlib import Path


def is_wsl(proc_version: str | None = None) -> bool:
    """True when running inside Windows Subsystem for Linux.

    WSL kernels identify themselves with "microsoft" in /proc/version.
    """
    if proc_version is None:
        try:
            proc_version = Path("/proc/version").read_text()
        except OSError:
            return False
    return "microsoft" in proc_version.lower()


def detect() -> dict:
    system = platform.system()  # "Linux", "Darwin", "Windows"
    wsl = system == "Linux" and is_wsl()
    labels = {"Darwin": "macOS", "Linux": "Linux", "Windows": "Windows"}
    label = labels.get(system, system or "Unknown")
    if wsl:
        label = "Linux (WSL)"
    return {
        "system": system,
        "label": label,
        "wsl": wsl,
        "release": platform.release(),
        "machine": platform.machine(),
        "hostname": platform.node(),
        "python": platform.python_version(),
    }
