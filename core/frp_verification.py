"""Deteksi status FRP (Factory Reset Protection) - READ ONLY.

Modul ini HANYA membaca status setup/provisioning device via ADB shell
(getprop, settings get) untuk menentukan apakah verifikasi kepemilikan
diperlukan sebelum teknisi melakukan reset/recovery. Modul ini secara
sengaja TIDAK PERNAH mencoba melewati (bypass) FRP, PIN, password, atau
pattern - konsisten dengan core/locked_device_recovery.py yang
mengonsumsi hasil dari sini.
"""

from __future__ import annotations

from dataclasses import dataclass

from .adb import ADBError, run_adb


class FRPVerificationError(RuntimeError):
    """Gagal membaca status FRP/provisioning dari device (mis. ADB error)."""


@dataclass
class FRPVerification:
    serial: str
    manufacturer: str
    model: str
    android_version: str
    build_id: str
    setup_complete: bool
    device_provisioned: bool
    frp_provisioned: str
    bootloader_locked: str
    verified_boot_state: str
    frp_status: str
    owner_verification_required: bool
    message: str


def _getprop(serial: str, prop: str) -> str:
    return run_adb("-s", serial, "shell", "getprop", prop).strip()


def _settings_get(serial: str, namespace: str, key: str) -> str:
    return run_adb("-s", serial, "shell", "settings", "get", namespace, key).strip()


def collect_frp_verification(serial: str) -> FRPVerification:
    """Baca status setup/provisioning device untuk menentukan apakah
    verifikasi kepemilikan (invoice/KTP) diperlukan sebelum tindakan
    reset. Tidak pernah mengembalikan/menjalankan langkah bypass.
    """
    try:
        manufacturer = _getprop(serial, "ro.product.manufacturer") or "Unknown"
        model = _getprop(serial, "ro.product.model") or "Unknown"
        android_version = _getprop(serial, "ro.build.version.release") or "Unknown"
        build_id = _getprop(serial, "ro.build.id") or "Unknown"

        setup_complete_raw = _settings_get(serial, "secure", "user_setup_complete")
        device_provisioned_raw = _settings_get(serial, "global", "device_provisioned")
        setup_complete = setup_complete_raw == "1"
        device_provisioned = device_provisioned_raw == "1"

        frp_provisioned = _getprop(serial, "ro.frp.pst") or "Unknown"
        bootloader_locked = _getprop(serial, "ro.boot.flash.locked") or "Unknown"
        verified_boot_state = _getprop(serial, "ro.boot.verifiedbootstate") or "Unknown"
    except ADBError as exc:
        raise FRPVerificationError(str(exc)) from exc

    owner_verification_required = setup_complete and device_provisioned

    if owner_verification_required:
        frp_status = "SETUP COMPLETE"
        message = (
            "Device sudah melewati setup wizard dan terikat ke akun pemilik. "
            "Wajib verifikasi kepemilikan (invoice pembelian/KTP yang sesuai) "
            "sebelum melakukan factory reset atau tindakan recovery lain."
        )
    else:
        frp_status = "SETUP INCOMPLETE"
        message = "Device belum menyelesaikan setup wizard / belum di-provision."

    return FRPVerification(
        serial=serial,
        manufacturer=manufacturer,
        model=model,
        android_version=android_version,
        build_id=build_id,
        setup_complete=setup_complete,
        device_provisioned=device_provisioned,
        frp_provisioned=frp_provisioned,
        bootloader_locked=bootloader_locked,
        verified_boot_state=verified_boot_state,
        frp_status=frp_status,
        owner_verification_required=owner_verification_required,
        message=message,
    )
