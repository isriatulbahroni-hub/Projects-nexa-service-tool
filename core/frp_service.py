"""FRP Service workflow - deteksi state device + reboot standar + verifikasi.

Modul ini HANYA melakukan tiga jenis operasi:
1. Membaca state device (ADB/Fastboot connected, authorized, brand, dll)
   - selalu read-only.
2. Reboot device ke recovery/bootloader - ini operasi STANDAR yang dipakai
   teknisi untuk banyak keperluan legit (flashing firmware resmi, wipe
   cache, diagnostik) dan TIDAK dengan sendirinya melewati FRP apapun.
   Dibatasi ke reboot_device() yang cuma menerima mode "recovery"/
   "bootloader"/"system" - tidak ada command arbitrary.
3. Verifikasi ulang status FRP setelah aksi (read-only, reuse
   collect_frp_verification dari core/frp_verification.py).

Modul ini TIDAK PERNAH menjalankan "fastboot oem unlock", "fastboot
flashing unlock", "fastboot erase frp", atau perintah lain yang melewati
proteksi device. Tombol aksi di UI (reboot/verify) hanya aktif ketika
owner_auth_required bernilai False, konsisten dengan
core/locked_device_recovery.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .adb import ADBError, get_devices_with_state, reboot_device
from .device import get_device_info
from .firmware import FastbootError, run_fastboot
from .frp_verification import FRPVerification, collect_frp_verification
from .locked_device_recovery import (
    _collect_device_identity,
    _infer_brand_group,
    _parse_fastboot_getvar,
)


class FRPServiceError(RuntimeError):
    """Gagal membaca state atau menjalankan aksi FRP service."""


@dataclass
class FRPServiceState:
    serial: str
    adb_state: str
    fastboot_connected: bool
    authorized: bool
    owner_auth_required: bool
    brand_group: str
    device_properties: dict[str, str]
    workflow_guidance: list[str]
    supported_operations: list[str]
    message: str
    fastboot_vars: dict[str, str] = field(default_factory=dict)


def collect_fastboot_variables(serial: str) -> dict[str, str]:
    """Baca `fastboot getvar all` (read-only). Kembalikan dict kosong
    kalau device tidak dalam mode fastboot / fastboot tidak tersedia.
    """
    try:
        output = run_fastboot("-s", serial, "getvar", "all")
    except FastbootError:
        return {}
    return _parse_fastboot_getvar(output)


def detect_frp_service_state(serial: str) -> FRPServiceState:
    """Deteksi state device saat ini untuk workflow FRP service. Murni
    membaca - tidak mengubah apapun di device.
    """
    try:
        devices = get_devices_with_state()
    except ADBError as exc:
        raise FRPServiceError(str(exc)) from exc

    adb_state = devices.get(serial, "not_detected")
    authorized = adb_state == "device"

    fastboot_vars = collect_fastboot_variables(serial)
    fastboot_connected = bool(fastboot_vars)

    identity = _collect_device_identity(serial, authorized, fastboot_vars, get_device_info)
    brand_group = _infer_brand_group(identity)

    owner_auth_required = False
    message = "Device belum terdeteksi. Hubungkan via USB dan pastikan authorized."

    if authorized:
        try:
            verification = collect_frp_verification(serial)
            owner_auth_required = verification.owner_verification_required
            message = verification.message
        except Exception as exc:  # tetap tampilkan state lain walau verifikasi gagal
            owner_auth_required = True
            message = f"Gagal membaca status FRP, verifikasi owner diwajibkan sebagai default aman: {exc}"
    elif fastboot_connected:
        # Di mode fastboot, status "secure"/"unlocked" dari device dipakai
        # sebagai sinyal tambahan (read-only) - tidak ada aksi otomatis.
        secure = fastboot_vars.get("secure", "").lower()
        owner_auth_required = secure in ("yes", "true", "1")
        message = "Device dalam mode Fastboot/Bootloader."
    elif adb_state == "unauthorized":
        message = "Device terdeteksi tapi belum diotorisasi (cek layar device untuk approve USB debugging)."
        owner_auth_required = True

    workflow_guidance = [
        "Selalu verifikasi kepemilikan (invoice/KTP) sebelum tindakan apa pun jika owner_auth_required = True.",
        "Reboot recovery/bootloader adalah operasi standar, aman untuk diagnostik dan flashing firmware resmi.",
        "Tool ini tidak pernah melewati FRP/PIN/password/pattern secara otomatis.",
    ]

    supported_operations = []
    if authorized and not owner_auth_required:
        supported_operations = ["reboot_recovery", "reboot_bootloader", "verify_result"]
    elif authorized:
        supported_operations = ["verify_result"]

    return FRPServiceState(
        serial=serial,
        adb_state=adb_state,
        fastboot_connected=fastboot_connected,
        authorized=authorized,
        owner_auth_required=owner_auth_required,
        brand_group=brand_group,
        device_properties=identity,
        workflow_guidance=workflow_guidance,
        supported_operations=supported_operations,
        message=message,
        fastboot_vars=fastboot_vars,
    )


def execute_recovery_reboot(serial: str) -> str:
    """Reboot device ke recovery mode - operasi standar ADB, dibatasi
    lewat reboot_device() yang hanya menerima mode allowlist."""
    try:
        return reboot_device(serial, mode="recovery")
    except ADBError as exc:
        raise FRPServiceError(str(exc)) from exc


def execute_bootloader_reboot(serial: str) -> str:
    """Reboot device ke bootloader/fastboot mode - operasi standar ADB."""
    try:
        return reboot_device(serial, mode="bootloader")
    except ADBError as exc:
        raise FRPServiceError(str(exc)) from exc


def verify_frp_result(serial: str) -> FRPVerification:
    """Baca ulang status FRP saat ini (read-only) - dipakai setelah
    reboot untuk konfirmasi state terbaru sebelum mengizinkan aksi lain."""
    try:
        return collect_frp_verification(serial)
    except Exception as exc:
        raise FRPServiceError(str(exc)) from exc
