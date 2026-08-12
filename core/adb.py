import subprocess
from pathlib import Path

from .config import ADB_PATH
from .tool_router import ToolRouter


class ADBError(RuntimeError):
    pass


_router = ToolRouter()


def run_adb_binary(*args: str, timeout: int = 15) -> bytes:
    """Sama seperti run_adb(), tapi untuk perintah yang outputnya BINARY
    (mis. 'exec-out screencap -p'). Jangan pernah pakai run_adb() untuk ini -
    run_adb() men-decode stdout sebagai teks UTF-8, yang akan merusak data
    biner seperti PNG.
    """
    adb_executable = _resolve_adb_path()
    if not Path(adb_executable).exists():
        raise ADBError(f"ADB tidak ditemukan: {adb_executable}")

    try:
        result = subprocess.run(
            [adb_executable, *args],
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ADBError("ADB timeout.") from exc
    except OSError as exc:
        raise ADBError(f"Gagal menjalankan ADB: {exc}") from exc

    if result.returncode != 0:
        error = (result.stderr or b"").decode("utf-8", errors="replace").strip()
        raise ADBError(error or f"ADB gagal dengan exit code {result.returncode}")

    return result.stdout


def _resolve_adb_path() -> str:
    # Path manual dari Settings punya prioritas tertinggi - berguna kalau
    # auto-detect (ADB_PATH default / ToolRouter di PATH) gagal menemukan
    # instalasi ADB di komputer teknisi.
    override = _get_path_override("adb_path_override")
    if override and Path(override).exists():
        return override

    if ADB_PATH.exists():
        return str(ADB_PATH)

    adb_path = _router.get_tool_path("adb")
    if adb_path:
        return str(adb_path)

    return str(ADB_PATH)


def _get_path_override(key: str) -> str:
    try:
        from .settings import get_settings_store
        return get_settings_store().get(key, "") or ""
    except Exception:
        return ""


def run_adb(*args: str, timeout: int = 15) -> str:
    adb_executable = _resolve_adb_path()
    if not Path(adb_executable).exists():
        raise ADBError(f"ADB tidak ditemukan: {adb_executable}")

    try:
        result = subprocess.run(
            [adb_executable, *args],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
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


def is_device_connected(serial: str) -> bool:
    """Cek cepat apakah `serial` masih terdaftar dan authorized di ADB.
    Dipakai operasi panjang (backup/restore) untuk deteksi device kecabut
    di tengah proses, supaya bisa berhenti dengan pesan yang jelas
    daripada terus mencoba semua target tersisa dan timeout satu-satu."""
    try:
        return get_devices_with_state().get(serial) == "device"
    except ADBError:
        return False


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
