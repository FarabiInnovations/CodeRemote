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


def os_name(system: str, release: str, *, mac_version: str = "", os_release: dict | None = None,
            wsl: bool = False) -> str:
    """Human-readable OS name: 'macOS 14.4', 'Ubuntu 24.04 LTS', 'Windows 11', ...

    Falls back to the kernel/OS release when nothing better is known.
    """
    if system == "Darwin":
        return f"macOS {mac_version}" if mac_version else f"macOS (Darwin {release})"
    if system == "Linux":
        pretty = (os_release or {}).get("PRETTY_NAME") or (os_release or {}).get("NAME")
        name = pretty or f"Linux {release}"
        return f"{name} (WSL)" if wsl else name
    if system == "Windows":
        return f"Windows {release}"
    return f"{system} {release}".strip() or "Unknown"


def _os_release() -> dict | None:
    try:
        return platform.freedesktop_os_release()
    except OSError:
        return None


def detect() -> dict:
    system = platform.system()  # "Linux", "Darwin", "Windows"
    release = platform.release()
    wsl = system == "Linux" and is_wsl()
    return {
        "system": system,
        "label": os_name(
            system,
            release,
            mac_version=platform.mac_ver()[0] if system == "Darwin" else "",
            os_release=_os_release() if system == "Linux" else None,
            wsl=wsl,
        ),
        "wsl": wsl,
        "release": release,
        "machine": platform.machine(),
        "hostname": platform.node(),
        "python": platform.python_version(),
    }
