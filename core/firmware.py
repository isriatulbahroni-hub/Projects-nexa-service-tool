import subprocess
from dataclasses import dataclass
from pathlib import Path

from .adb import run_adb, ADBError
from .config import FASTBOOT_PATH
from .tool_router import ToolRouter


_router = ToolRouter()


def _resolve_fastboot_path() -> str:
    if FASTBOOT_PATH.exists():
        return str(FASTBOOT_PATH)

    fastboot_path = _router.get_tool_path("fastboot")
    if fastboot_path:
        return str(fastboot_path)

    return str(FASTBOOT_PATH)


def run_fastboot(*args: str, timeout: int = 60) -> str:
    fastboot_executable = _resolve_fastboot_path()
    if not Path(fastboot_executable).exists():
        raise FastbootError(f"Fastboot tidak ditemukan: {fastboot_executable}")

    try:
        result = subprocess.run(
            [fastboot_executable, *args],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise FastbootError("Fastboot timeout.") from exc
    except OSError as exc:
        raise FastbootError(f"Gagal menjalankan fastboot: {exc}") from exc

    output = (result.stdout or "") + (result.stderr or "")

    if result.returncode != 0:
        raise FastbootError(output.strip() or f"Fastboot gagal, exit code {result.returncode}")

    return output.strip()


class FastbootError(RuntimeError):
    pass


@dataclass
class BuildInfo:
    build_id: str
    build_fingerprint: str
    android_version: str
    security_patch: str
    baseband_version: str
    bootloader_version: str
    build_date: str


def get_build_info(serial: str) -> BuildInfo:
    def prop(name: str) -> str:
        try:
            return run_adb("-s", serial, "shell", "getprop", name).strip() or "Unknown"
        except ADBError:
            return "Unknown"

    return BuildInfo(
        build_id=prop("ro.build.id"),
        build_fingerprint=prop("ro.build.fingerprint"),
        android_version=prop("ro.build.version.release"),
        security_patch=prop("ro.build.version.security_patch"),
        baseband_version=prop("gsm.version.baseband"),
        bootloader_version=prop("ro.bootloader"),
        build_date=prop("ro.build.date"),
    )


def list_fastboot_devices() -> list[str]:
    output = run_fastboot("devices")
    devices = []

    for line in output.splitlines():
        line = line.strip()

        if line and "\t" in line:
            devices.append(line.split("\t")[0])
        elif line and " " in line:
            devices.append(line.split()[0])

    return devices


# Partisi umum yang aman untuk diflash teknisi (menghindari partisi kritis
# seperti bootloader/modem tanpa konfirmasi eksplisit tambahan).
COMMON_PARTITIONS = [
    "boot",
    "recovery",
    "system",
    "vendor",
    "vbmeta",
    "dtbo",
]

CRITICAL_PARTITIONS = ["bootloader", "modem", "radio"]


def flash_partition(
    partition: str, image_path: str, serial: str | None = None, allow_critical: bool = False
) -> str:
    # Defense-in-depth: sebelumnya fungsi ini akan flash partition APAPUN
    # tanpa validasi - satu-satunya penghalang partition kritis
    # (bootloader/modem/radio) cuma combo box di UI yang isinya dibatasi
    # ke COMMON_PARTITIONS. Aman selama UI tidak berubah, tapi kalau ada
    # caller lain (mis. automation/macro) yang manggil flash_partition()
    # langsung, tidak ada yang mencegah flash partition kritis tanpa
    # sengaja. Sekarang diblokir kecuali eksplisit di-allow.
    if partition in CRITICAL_PARTITIONS and not allow_critical:
        raise FastbootError(
            f"Partition '{partition}' adalah partition kritis dan diblokir "
            f"secara default. Set allow_critical=True kalau memang sengaja."
        )

    args = []

    if serial:
        args += ["-s", serial]

    args += ["flash", partition, image_path]

    return run_fastboot(*args, timeout=180)


def reboot_from_fastboot(serial: str | None = None) -> str:
    args = []

    if serial:
        args += ["-s", serial]

    args.append("reboot")

    return run_fastboot(*args, timeout=30)
