"""Laporan diagnostics gabungan (Category/Check/Status/Value/Detail) - READ ONLY.

Melengkapi core/diagnostics.py (ringkasan cepat baterai/storage/layar) dengan
menjalankan pemeriksaan yang lebih luas: hardware (via core/hardware_test.py),
keamanan (via core/security_check.py), dan jaringan (via core/network_info.py),
lalu dikemas jadi satu daftar item seragam untuk ditampilkan di tabel UI.

Modul ini murni membaca status device via ADB shell - tidak pernah mengubah
apapun di device.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .adb import ADBError
from .hardware_test import run_hardware_test
from .network_info import get_network_info
from .security_check import run_security_check


class DiagnosticStatus(Enum):
    OK = "OK"
    WARNING = "WARNING"
    ERROR = "ERROR"
    INFO = "INFO"


@dataclass(frozen=True)
class DiagnosticItem:
    category: str
    name: str
    status: DiagnosticStatus
    value: str
    detail: str = ""


@dataclass(frozen=True)
class DeviceDiagnosticsReport:
    serial: str
    summary: str
    items: list[DiagnosticItem]


_HARDWARE_STATUS_MAP = {
    "PASS": DiagnosticStatus.OK,
    "WARN": DiagnosticStatus.WARNING,
    "FAIL": DiagnosticStatus.ERROR,
    "INFO": DiagnosticStatus.INFO,
}


def _hardware_items(serial: str) -> list[DiagnosticItem]:
    try:
        report = run_hardware_test(serial)
    except Exception as exc:  # tetap resilient walau satu layer gagal total
        return [DiagnosticItem("Hardware", "Hardware Test", DiagnosticStatus.ERROR, "Unavailable", str(exc))]

    return [
        DiagnosticItem(
            category="Hardware",
            name=result.name,
            status=_HARDWARE_STATUS_MAP.get(result.status, DiagnosticStatus.INFO),
            value=result.value,
            detail=result.detail,
        )
        for result in report.results
    ]


def _security_items(serial: str) -> list[DiagnosticItem]:
    try:
        result = run_security_check(serial)
    except ADBError as exc:
        return [DiagnosticItem("Security", "Root/Bootloader", DiagnosticStatus.ERROR, "Unavailable", str(exc))]

    status = DiagnosticStatus.WARNING if result.is_rooted else DiagnosticStatus.OK
    value = "Rooted" if result.is_rooted else "Not Rooted"
    detail = f"Bootloader: {result.bootloader_state}; Verified Boot: {result.verified_boot_state}"
    return [DiagnosticItem("Security", "Root/Bootloader", status, value, detail)]


def _network_items(serial: str) -> list[DiagnosticItem]:
    try:
        info = get_network_info(serial)
    except ADBError as exc:
        return [DiagnosticItem("Network", "Connectivity", DiagnosticStatus.ERROR, "Unavailable", str(exc))]

    connected = info.wifi_state == "Enabled" or info.mobile_data_state == "Enabled"
    status = DiagnosticStatus.OK if connected else DiagnosticStatus.WARNING
    value = info.ip_address or "No IP"
    detail = (
        f"WiFi: {info.wifi_state}; Mobile Data: {info.mobile_data_state}; "
        f"Operator: {info.network_operator}"
    )
    return [DiagnosticItem("Network", "Connectivity", status, value, detail)]


def run_device_diagnostics(serial: str) -> DeviceDiagnosticsReport:
    """Jalankan pemeriksaan hardware + security + network sekaligus untuk
    satu device, dikemas jadi laporan tabular seragam.
    """
    items: list[DiagnosticItem] = []
    items.extend(_hardware_items(serial))
    items.extend(_security_items(serial))
    items.extend(_network_items(serial))

    error_count = sum(1 for item in items if item.status == DiagnosticStatus.ERROR)
    warning_count = sum(1 for item in items if item.status == DiagnosticStatus.WARNING)

    if error_count:
        summary = f"{error_count} pemeriksaan gagal, {warning_count} peringatan - perlu perhatian teknisi."
    elif warning_count:
        summary = f"{warning_count} peringatan ditemukan, sisanya normal."
    else:
        summary = "Semua pemeriksaan normal."

    return DeviceDiagnosticsReport(serial=serial, summary=summary, items=items)
