from coderemote import platform_info


def test_wsl_detected_from_proc_version():
    text = "Linux version 5.15.153.1-microsoft-standard-WSL2 (root@1234) (gcc 11.2.0)"
    assert platform_info.is_wsl(text) is True


def test_plain_linux_is_not_wsl():
    text = "Linux version 7.0.0-28-generic (buildd@lcy02-amd64-047) #28-Ubuntu SMP"
    assert platform_info.is_wsl(text) is False


def test_detect_returns_basic_fields():
    info = platform_info.detect()
    assert {"system", "label", "wsl", "release", "machine", "hostname"} <= info.keys()


def test_os_name_linux_uses_distro():
    rel = {"NAME": "Ubuntu", "PRETTY_NAME": "Ubuntu 24.04.1 LTS"}
    assert platform_info.os_name("Linux", "6.8.0-generic", os_release=rel) == "Ubuntu 24.04.1 LTS"


def test_os_name_linux_wsl_keeps_marker():
    rel = {"PRETTY_NAME": "Ubuntu 22.04.4 LTS"}
    assert platform_info.os_name("Linux", "5.15", os_release=rel, wsl=True) == "Ubuntu 22.04.4 LTS (WSL)"


def test_os_name_linux_without_os_release_falls_back_to_kernel():
    assert platform_info.os_name("Linux", "6.8.0-generic", os_release=None) == "Linux 6.8.0-generic"


def test_os_name_macos_uses_product_version():
    assert platform_info.os_name("Darwin", "23.4.0", mac_version="14.4") == "macOS 14.4"
    assert platform_info.os_name("Darwin", "23.4.0", mac_version="") == "macOS (Darwin 23.4.0)"


def test_os_name_windows():
    assert platform_info.os_name("Windows", "11") == "Windows 11"
