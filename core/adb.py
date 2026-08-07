import subprocess
from pathlib import Path

from .config import ADB_PATH
from .tool_router import ToolRouter


class ADBError(RuntimeError):
    pass


_router = ToolRouter()


def _resolve_adb_path() -> str:
    if ADB_PATH.exists():
        return str(ADB_PATH)

    adb_path = _router.get_tool_path("adb")
    if adb_path:
        return str(adb_path)

    return str(ADB_PATH)


def run_adb(*args: str, timeout: int = 15) -> str:
    adb_executable = _resolve_adb_path()
    if not Path(adb_executable).exists():
        raise ADBError(f"ADB tidak ditemukan: {adb_executable}")

    try:
        result = subprocess.run(
            [adb_executable, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ADBError("ADB timeout.") from exc
    except OSError as exc:
        raise ADBError(f"Gagal menjalankan ADB: {exc}") from exc

    if result.returncode != 0:
        error = result.stderr.strip() or result.stdout.strip()
        raise ADBError(error or f"ADB gagal dengan exit code {result.returncode}")

    return result.stdout.strip()


def get_adb_version() -> str:
    return run_adb("version")


def get_devices() -> list[str]:
    output = run_adb("devices")
    devices = []

    for line in output.splitlines()[1:]:
        line = line.strip()

        if not line:
            continue

        parts = line.split()

        if len(parts) >= 2 and parts[1] == "device":
            devices.append(parts[0])

    return devices


def get_devices_with_state() -> dict[str, str]:
    """
    Mengembalikan semua device yang terdeteksi ADB beserta statusnya,
    termasuk yang unauthorized/offline (untuk multi-device support).
    Contoh: {"ABC123": "device", "XYZ456": "unauthorized"}
    """
    output = run_adb("devices")
    devices = {}

    for line in output.splitlines()[1:]:
        line = line.strip()

        if not line:
            continue

        parts = line.split()

        if len(parts) >= 2:
            devices[parts[0]] = parts[1]

    return devices


def reboot_device(serial: str, mode: str = "system") -> str:
    allowed_modes = {
        "system": (),
        "recovery": ("recovery",),
        "bootloader": ("bootloader",),
    }

    if mode not in allowed_modes:
        raise ADBError(f"Mode reboot tidak valid: {mode}")

    return run_adb(
        "-s",
        serial,
        "reboot",
        *allowed_modes[mode],
        timeout=10,
    )
