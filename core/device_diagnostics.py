"""Laporan diagnostics gabungan (Category/Check/Status/Value/Detail) - READ ONLY.

Menjalankan pemeriksaan komprehensif terhadap device: identitas/build,
baterai, storage, boot & setup wizard, keamanan (root/bootloader),
jaringan, dan komunikasi fastboot - semuanya lewat ADB shell dan murni
membaca (read-only), tidak pernah mengubah apapun di device.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .adb import ADBError, get_devices_with_state, run_adb
from .device import get_device_info
from .firmware import FastbootError, list_fastboot_devices
from .network_info import get_network_info
from .security_check import run_security_check


class CheckStatus(Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    NA = "NA"


@dataclass(frozen=True)
class DiagnosticItem:
    category: str
    name: str
    status: CheckStatus
    value: str
    detail: str = ""


@dataclass
class DiagnosticReport:
    serial: str
    summary: str
    device_info: dict[str, str]
    items: list[DiagnosticItem] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)


DiagnosticStatus = CheckStatus
DeviceDiagnosticsReport = DiagnosticReport


def _parse_key_value(text: str, key: str) -> str:
    """Ambil value dari baris berformat key value atau key: value
    di dalam output multi-baris seperti dumpsys battery / /proc/meminfo."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(key):
            return stripped[len(key):].strip()
    return ""


def _run_adb_safe(*args: str, timeout: int = 15) -> str:
    try:
        return run_adb(*args, timeout=timeout)
    except ADBError:
        return ""


def _battery_item(serial: str) -> DiagnosticItem:
    raw = _run_adb_safe("-s", serial, "shell", "dumpsys", "battery")
    level = _parse_key_value(raw, "level:")
    status_code = _parse_key_value(raw, "status:")
    health_code = _parse_key_value(raw, "health:")

    if not level:
        return DiagnosticItem("Hardware", "Battery Level", CheckStatus.NA, "Unknown", "Data baterai tidak terbaca.")

    try:
        level_int = int(level)
    except ValueError:
        level_int = None

    if level_int is not None and level_int < 15:
        status = CheckStatus.WARN
        detail = "Level baterai rendah, sebaiknya charge sebelum diagnostik lanjutan."
    else:
        status = CheckStatus.PASS
        detail = f"Status code: {status_code or 'Unknown'}; Health code: {health_code or 'Unknown'}."

    return DiagnosticItem("Hardware", "Battery Level", status, f"{level}%", detail)


def _storage_item(serial: str) -> DiagnosticItem:
    raw = _run_adb_safe("-s", serial, "shell", "df", "-h", "/data")
    lines = [line for line in raw.splitlines() if line.strip()]
    if len(lines) < 2:
        return DiagnosticItem("Storage", "Internal Storage", CheckStatus.NA, "Unknown", "Output df tidak terbaca.")

    parts = lines[-1].split()
    usage = next((p for p in parts if p.endswith("%")), None)
    if usage is None:
        return DiagnosticItem("Storage", "Internal Storage", CheckStatus.NA, "Unknown", "Persentase penggunaan tidak ditemukan.")

    try:
        percent = int(usage.rstrip("%"))
    except ValueError:
        percent = 0

    status = CheckStatus.WARN if percent >= 90 else CheckStatus.PASS
    detail = "Storage hampir penuh." if percent >= 90 else f"Penggunaan /data: {usage}."
    return DiagnosticItem("Storage", "Internal Storage", status, usage, detail)


def _mounts_item(serial: str) -> DiagnosticItem:
    raw = _run_adb_safe("-s", serial, "shell", "cat", "/proc/mounts")
    data_mounted = any("/data" in line for line in raw.splitlines())
    status = CheckStatus.PASS if data_mounted else CheckStatus.WARN
    detail = "Partisi /data ter-mount normal." if data_mounted else "Partisi /data tidak terdeteksi di /proc/mounts."
    return DiagnosticItem("Storage", "Mount Points", status, "Detected" if data_mounted else "Unknown", detail)


def _build_items(serial: str) -> list[DiagnosticItem]:
    build_id = _run_adb_safe("-s", serial, "shell", "getprop", "ro.build.id") or "Unknown"
    fingerprint = _run_adb_safe("-s", serial, "shell", "getprop", "ro.build.fingerprint") or "Unknown"
    patch = _run_adb_safe("-s", serial, "shell", "getprop", "ro.build.version.security_patch") or "Unknown"
    version = _run_adb_safe("-s", serial, "shell", "getprop", "ro.build.version.release") or "Unknown"

    return [
        DiagnosticItem("System", "Build ID", CheckStatus.PASS if build_id != "Unknown" else CheckStatus.NA, build_id, f"Fingerprint: {fingerprint}"),
        DiagnosticItem("System", "Android Version", CheckStatus.PASS if version != "Unknown" else CheckStatus.NA, version, ""),
        DiagnosticItem("System", "Security Patch", CheckStatus.PASS if patch != "Unknown" else CheckStatus.NA, patch, ""),
    ]


def _boot_items(serial: str) -> list[DiagnosticItem]:
    bootmode = _run_adb_safe("-s", serial, "shell", "getprop", "ro.bootmode")
    boot_completed = _run_adb_safe("-s", serial, "shell", "getprop", "sys.boot_completed")

    boot_status = CheckStatus.PASS if boot_completed == "1" else CheckStatus.WARN
    return [
        DiagnosticItem("System", "Boot Completed", boot_status, boot_completed or "Unknown", f"Boot mode: {bootmode or 'normal'}."),
    ]


def _setup_items(serial: str) -> list[DiagnosticItem]:
    setup_complete = _run_adb_safe("-s", serial, "shell", "settings", "get", "secure", "user_setup_complete")
    adb_enabled = _run_adb_safe("-s", serial, "shell", "settings", "get", "global", "adb_enabled")

    return [
        DiagnosticItem(
            "System", "Setup Wizard",
            CheckStatus.PASS if setup_complete == "1" else CheckStatus.WARN,
            "Complete" if setup_complete == "1" else "Incomplete",
            "",
        ),
        DiagnosticItem(
            "System", "ADB Debugging",
            CheckStatus.PASS if adb_enabled == "1" else CheckStatus.NA,
            "Enabled" if adb_enabled == "1" else "Unknown",
            "",
        ),
    ]


def _packages_item(serial: str) -> DiagnosticItem:
    raw = _run_adb_safe("-s", serial, "shell", "pm", "list", "packages", timeout=20)
    count = len([line for line in raw.splitlines() if line.strip().startswith("package:")])
    status = CheckStatus.PASS if count > 0 else CheckStatus.NA
    return DiagnosticItem("System", "Installed Apps", status, str(count), f"{count} paket terdeteksi via pm list packages.")


def _log_item(serial: str) -> DiagnosticItem:
    raw = _run_adb_safe("-s", serial, "shell", "logcat", "-d", "-t", "2000", "*:E", timeout=15)
    crash_count = raw.count("FATAL EXCEPTION")
    status = CheckStatus.WARN if crash_count > 0 else CheckStatus.PASS
    detail = f"{crash_count} fatal exception ditemukan di log terkini." if crash_count else "Tidak ada fatal exception di log terkini."
    return DiagnosticItem("System", "Crash Log", status, str(crash_count), detail)


def _memory_item(serial: str) -> DiagnosticItem:
    raw = _run_adb_safe("-s", serial, "shell", "cat", "/proc/meminfo")
    total = _parse_key_value(raw, "MemTotal:")
    free = _parse_key_value(raw, "MemFree:")
    if not total:
        return DiagnosticItem("Hardware", "Memory", CheckStatus.NA, "Unknown", "Data memori tidak terbaca.")
    return DiagnosticItem("Hardware", "Memory", CheckStatus.PASS, f"{total} total, {free or '0'} free", "")


def _bootloader_items(serial: str) -> list[DiagnosticItem]:
    locked = _run_adb_safe("-s", serial, "shell", "getprop", "ro.boot.flash.locked")
    verified = _run_adb_safe("-s", serial, "shell", "getprop", "ro.boot.verifiedbootstate")

    locked_status = CheckStatus.PASS if locked == "1" else CheckStatus.WARN
    verified_status = CheckStatus.PASS if verified == "green" else CheckStatus.WARN

    return [
        DiagnosticItem("Security", "Bootloader Lock", locked_status, "Locked" if locked == "1" else "Unlocked", ""),
        DiagnosticItem("Security", "Verified Boot", verified_status, verified or "Unknown", ""),
    ]


def _authorization_item(serial: str) -> DiagnosticItem:
    try:
        devices = get_devices_with_state()
    except ADBError as exc:
        return DiagnosticItem("System", "ADB Authorization", CheckStatus.FAIL, "Unavailable", str(exc))

    state = devices.get(serial, "not_detected")
    status = CheckStatus.PASS if state == "device" else CheckStatus.WARN
    return DiagnosticItem("System", "ADB Authorization", status, state, "")


def _security_item(serial: str) -> DiagnosticItem:
    try:
        result = run_security_check(serial)
    except ADBError as exc:
        return DiagnosticItem("Security", "Root/Bootloader", CheckStatus.FAIL, "Unavailable", str(exc))

    is_rooted = getattr(result, "is_rooted", False)
    status = CheckStatus.WARN if is_rooted else CheckStatus.PASS
    value = "Rooted" if is_rooted else "Not Rooted"
    detail = f"Bootloader: {result.bootloader_state}; Verified Boot: {result.verified_boot_state}"
    return DiagnosticItem("Security", "Root/Bootloader", status, value, detail)


def _network_item(serial: str) -> DiagnosticItem:
    try:
        info = get_network_info(serial)
    except ADBError as exc:
        return DiagnosticItem("Network", "Connectivity", CheckStatus.FAIL, "Unavailable", str(exc))

    connected = info.wifi_state == "Enabled" or info.mobile_data_state == "Enabled"
    status = CheckStatus.PASS if connected else CheckStatus.WARN
    value = info.ip_address or "No IP"
    detail = (
        f"WiFi: {info.wifi_state}; Mobile Data: {info.mobile_data_state}; "
        f"Operator: {info.network_operator}"
    )
    return DiagnosticItem("Network", "Connectivity", status, value, detail)


def _fastboot_item() -> DiagnosticItem:
    try:
        devices = list_fastboot_devices()
    except FastbootError as exc:
        return DiagnosticItem("System", "Fastboot Communication", CheckStatus.FAIL, "Unavailable", str(exc))

    if devices:
        return DiagnosticItem(
            "System", "Fastboot Communication", CheckStatus.PASS,
            f"{len(devices)} device(s)", "Fastboot tool merespons dan mendeteksi device.",
        )
    return DiagnosticItem(
        "System", "Fastboot Communication", CheckStatus.PASS,
        "0 device(s)", "Fastboot tool merespons normal (tidak ada device dalam mode fastboot saat ini).",
    )


def _device_info_dict(serial: str) -> dict[str, str]:
    try:
        info = get_device_info(serial)
    except ADBError:
        return {
            "Manufacturer": "Unknown", "Model": "Unknown", "Product": "Unknown",
            "Device": "Unknown", "Android Version": "Unknown", "Build ID": "Unknown",
        }
    return {
        "Manufacturer": info.manufacturer,
        "Model": info.model,
        "Product": info.product,
        "Device": info.device,
        "Android Version": info.android_version,
        "Build ID": info.build_id,
    }


def run_device_diagnostics(serial: str) -> DiagnosticReport:
    """Jalankan pemeriksaan komprehensif untuk satu device (identitas,
    baterai, storage, boot/setup, keamanan, jaringan, fastboot) - murni
    read-only, tidak pernah mengubah apapun di device.
    """
    items: list[DiagnosticItem] = []
    items.append(_authorization_item(serial))
    items.append(_battery_item(serial))
    items.append(_storage_item(serial))
    items.append(_mounts_item(serial))
    items.extend(_build_items(serial))
    items.extend(_boot_items(serial))
    items.extend(_setup_items(serial))
    items.append(_packages_item(serial))
    items.append(_log_item(serial))
    items.append(_memory_item(serial))
    items.extend(_bootloader_items(serial))
    items.append(_security_item(serial))
    items.append(_network_item(serial))
    items.append(_fastboot_item())

    counts = {status.value: 0 for status in CheckStatus}
    for item in items:
        counts[item.status.value] += 1

    fail_count = counts[CheckStatus.FAIL.value]
    warn_count = counts[CheckStatus.WARN.value]

    if fail_count:
        summary = f"FAIL - {fail_count} pemeriksaan gagal, {warn_count} peringatan. Perlu perhatian teknisi."
    elif warn_count:
        summary = f"PASS dengan {warn_count} peringatan - sebagian besar pemeriksaan normal."
    else:
        summary = "PASS - semua pemeriksaan normal."

    return DiagnosticReport(
        serial=serial,
        summary=summary,
        device_info=_device_info_dict(serial),
        items=items,
        counts=counts,
    )
