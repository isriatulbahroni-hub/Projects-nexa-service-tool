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

Semua fungsi publik menerima parameter dependency (mis. devices_fn,
fastboot_fn, frp_fn, detect_fn, reboot_fn) yang defaultnya adalah
implementasi ADB/Fastboot sungguhan - ini memudahkan unit test tanpa
device fisik, dan tetap 100% backward compatible untuk pemanggilan
lama yang cuma mengoper serial.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .adb import ADBError, get_devices_with_state, reboot_device, run_adb
from .firmware import FastbootError, list_fastboot_devices, run_fastboot
from .frp_verification import FRPVerification, collect_frp_verification
from .locked_device_recovery import _infer_brand_group, _parse_fastboot_getvar


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
    frp_status: str | None = None
    frp_verification: FRPVerification | None = None
    fastboot_vars: dict[str, str] | None = field(default_factory=dict)


def _adb_prop(serial: str, prop: str) -> str:
    try:
        return run_adb("-s", serial, "shell", "getprop", prop).strip() or "Unknown"
    except ADBError:
        return "Unknown"


def _collect_device_properties(serial: str) -> dict[str, str]:
    """Baca identitas device langsung via getprop (read-only)."""
    return {
        "manufacturer": _adb_prop(serial, "ro.product.manufacturer"),
        "brand": _adb_prop(serial, "ro.product.brand"),
        "model": _adb_prop(serial, "ro.product.model"),
        "name": _adb_prop(serial, "ro.product.name"),
        "device": _adb_prop(serial, "ro.product.device"),
        "fingerprint": _adb_prop(serial, "ro.build.fingerprint"),
    }


def _build_recovery_guidance(
    *,
    brand_group: str,
    authorized: bool,
    owner_auth_required: bool,
    fastboot_connected: bool,
) -> list[str]:
    """Susun daftar panduan workflow berdasarkan state device saat ini."""
    guidance: list[str] = [
        "Selalu verifikasi kepemilikan (invoice/KTP) sebelum tindakan apa pun "
        "jika owner authorization diwajibkan.",
        "Tool ini tidak pernah melewati FRP/PIN/password/pattern secara otomatis.",
    ]

    if owner_auth_required:
        guidance.append(
            f"Device ({brand_group}) memerlukan owner/OEM authorization sebelum "
            "aksi recovery dapat dilanjutkan."
        )
        guidance.append(
            "Reboot recovery/bootloader adalah operasi standar dan aman untuk "
            "diagnostik setelah owner authorization terkonfirmasi."
        )
    elif authorized:
        guidance.append("Owner authorization cleared - opsi reboot recovery standar tersedia.")
        if fastboot_connected:
            guidance.append(
                "Fastboot mode is available untuk operasi firmware resmi dan diagnostik."
            )
        else:
            guidance.append("Recovery reboot tersedia untuk prosedur diagnostik/servis resmi.")

    return guidance


def collect_fastboot_variables(
    serial: str,
    *,
    fastboot_fn: Callable[[], list[str]] = list_fastboot_devices,
    run_fastboot_fn: Callable[..., str] = run_fastboot,
) -> dict[str, str]:
    """Baca fastboot getvar all (read-only). Kembalikan dict kosong
    kalau device tidak dalam mode fastboot / fastboot tidak tersedia.
    """
    try:
        devices = fastboot_fn()
    except FastbootError:
        return {}

    if serial not in devices:
        return {}

    try:
        output = run_fastboot_fn("-s", serial, "getvar", "all")
    except FastbootError:
        return {}

    return _parse_fastboot_getvar(output)


def detect_frp_service_state(
    serial: str,
    *,
    devices_fn: Callable[[], dict[str, str]] = get_devices_with_state,
    fastboot_fn: Callable[[], list[str]] = list_fastboot_devices,
    frp_fn: Callable[[str], FRPVerification] = collect_frp_verification,
) -> FRPServiceState:
    """Deteksi state device saat ini untuk workflow FRP service. Murni
    membaca - tidak mengubah apapun di device.
    """
    try:
        devices = devices_fn()
    except ADBError as exc:
        raise FRPServiceError(str(exc)) from exc

    adb_state = devices.get(serial, "not_detected")
    authorized = adb_state == "device"

    fastboot_devices = fastboot_fn()
    fastboot_connected = serial in fastboot_devices

    fastboot_vars: dict[str, str] = {}
    if fastboot_connected:
        try:
            output = run_fastboot("-s", serial, "getvar", "all")
            fastboot_vars = _parse_fastboot_getvar(output)
        except FastbootError:
            fastboot_vars = {}

    device_properties: dict[str, str] = {}
    if authorized:
        device_properties = _collect_device_properties(serial)

    brand_group = _infer_brand_group(device_properties or fastboot_vars)

    owner_auth_required = False
    frp_status: str | None = None
    frp_verification: FRPVerification | None = None
    message = "Device belum terdeteksi. Hubungkan via USB dan pastikan authorized."

    if authorized:
        try:
            verification = frp_fn(serial)
            owner_auth_required = verification.owner_verification_required
            message = verification.message
            frp_status = verification.frp_status
            frp_verification = verification
        except Exception as exc:
            owner_auth_required = True
            frp_status = "UNKNOWN"
            message = f"Gagal membaca status FRP, verifikasi owner diwajibkan sebagai default aman: {exc}"
    elif fastboot_connected:
        secure = fastboot_vars.get("secure", "").lower()
        owner_auth_required = secure in ("yes", "true", "1")
        message = "Device dalam mode Fastboot/Bootloader."
    elif adb_state == "unauthorized":
        message = "Perangkat memerlukan otorisasi ADB (cek layar device dan izinkan USB debugging)."
        owner_auth_required = True

    workflow_guidance = _build_recovery_guidance(
        brand_group=brand_group,
        authorized=authorized,
        owner_auth_required=owner_auth_required,
        fastboot_connected=fastboot_connected,
    )

    supported_operations: list[str] = []
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
        device_properties=device_properties,
        workflow_guidance=workflow_guidance,
        supported_operations=supported_operations,
        message=message,
        frp_status=frp_status,
        frp_verification=frp_verification,
        fastboot_vars=fastboot_vars,
    )


def execute_recovery_reboot(
    serial: str,
    *,
    detect_fn: Callable[[str], FRPServiceState] = detect_frp_service_state,
    reboot_fn: Callable[..., str] = reboot_device,
) -> str:
    """Reboot device ke recovery mode - operasi standar ADB, dibatasi
    lewat reboot_device() yang hanya menerima mode allowlist."""
    state = detect_fn(serial)
    if state.owner_auth_required:
        raise FRPServiceError(
            "REQUIRES OWNER/OEM AUTHORIZATION sebelum melakukan reboot recovery."
        )
    try:
        return reboot_fn(serial, mode="recovery")
    except ADBError as exc:
        raise FRPServiceError(str(exc)) from exc


def execute_bootloader_reboot(
    serial: str,
    *,
    detect_fn: Callable[[str], FRPServiceState] = detect_frp_service_state,
    reboot_fn: Callable[..., str] = reboot_device,
) -> str:
    """Reboot device ke bootloader/fastboot mode - operasi standar ADB."""
    state = detect_fn(serial)
    if state.owner_auth_required:
        raise FRPServiceError(
            "REQUIRES OWNER/OEM AUTHORIZATION sebelum melakukan reboot bootloader."
        )
    try:
        return reboot_fn(serial, mode="bootloader")
    except ADBError as exc:
        raise FRPServiceError(str(exc)) from exc


def verify_frp_result(
    serial: str,
    *,
    frp_fn: Callable[[str], FRPVerification] = collect_frp_verification,
) -> FRPVerification:
    """Baca ulang status FRP saat ini (read-only) - dipakai setelah
    reboot untuk konfirmasi state terbaru sebelum mengizinkan aksi lain."""
    try:
        return frp_fn(serial)
    except Exception as exc:
        raise FRPServiceError(str(exc)) from exc
