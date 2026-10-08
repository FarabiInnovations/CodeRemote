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
