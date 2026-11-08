"""Deteksi status FRP (Factory Reset Protection) - READ ONLY.

Modul ini HANYA membaca status setup/provisioning device via ADB shell
(getprop dan settings get) untuk menentukan apakah verifikasi kepemilikan
diperlukan sebelum teknisi melakukan reset/recovery. Modul ini secara sengaja
TIDAK PERNAH mencoba melewati (bypass) FRP, PIN, password, atau pattern -
konsisten dengan core/locked_device_recovery.py yang mengonsumsi hasil
dari sini.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

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


def _default_runner(serial: str, command: str) -> str:
    return run_adb("-s", serial, "shell", command)


def _parse_getprop(output: str) -> dict[str, str]:
    """Parse output mentah getprop (format [key]: [value] per baris)
    menjadi dict {key: value}."""
    props: dict[str, str] = {}
    for line in output.splitlines():
        line = line.strip()
        if not line.startswith("["):
            continue
        try:
            key_part, value_part = line.split("]:", 1)
        except ValueError:
            continue
        key = key_part.strip().lstrip("[").strip()
        value = value_part.strip().strip("[]").strip()
        props[key] = value
    return props


def _getprop(serial: str, prop: str) -> str:
    return run_adb("-s", serial, "shell", "getprop", prop).strip()


def _settings_get(serial: str, namespace: str, key: str) -> str:
    return run_adb("-s", serial, "shell", "settings", "get", namespace, key).strip()


def collect_frp_verification(
    serial: str,
    runner: Callable[[str, str], str] = _default_runner,
) -> FRPVerification:
    """Baca status setup/provisioning device untuk menentukan apakah
    verifikasi kepemilikan (invoice/KTP) diperlukan sebelum tindakan
    reset. Tidak pernah mengembalikan/menjalankan langkah bypass.

    manufacturer/model/build/frp/bootloader dibaca lewat satu panggilan
    `getprop` (properti ro.* sungguhan). Status setup wizard/provisioning
    TIDAK tersedia lewat getprop di device Android manapun - itu murni
    nilai Settings Provider, jadi dibaca terpisah lewat `settings get`.
    """
    try:
        prop_output = runner(serial, "getprop")
    except ADBError as exc:
        raise FRPVerificationError(str(exc)) from exc

    props = _parse_getprop(prop_output)

    manufacturer = props.get("ro.product.manufacturer") or "Unknown"
    model = props.get("ro.product.model") or "Unknown"
    android_version = props.get("ro.build.version.release") or "Unknown"
    build_id = props.get("ro.build.id") or "Unknown"
    frp_provisioned = props.get("ro.frp.pst") or "Unknown"
    bootloader_locked = props.get("ro.boot.flash.locked") or "Unknown"
    verified_boot_state = props.get("ro.boot.verifiedbootstate") or "Unknown"

    try:
        setup_raw = runner(serial, "settings get secure user_setup_complete").strip()
    except ADBError:
        setup_raw = ""
    try:
        provisioned_raw = runner(serial, "settings get global device_provisioned").strip()
    except ADBError:
        provisioned_raw = ""

    # `settings get` pada key yang tidak ada mengembalikan literal "null"
    # (bukan string kosong) di Android sungguhan.
    setup_missing = setup_raw in ("", "null")
    provisioned_missing = provisioned_raw in ("", "null")

    if setup_missing and provisioned_missing:
        setup_complete = False
        device_provisioned = False
        frp_status = "UNKNOWN"
        owner_verification_required = True
        message = (
            "Status setup wizard/provisioning tidak terbaca. Wajib verifikasi "
            "kepemilikan (invoice pembelian/KTP yang sesuai) sebelum tindakan lanjut."
        )
    elif setup_raw == "1" and provisioned_raw == "1":
        setup_complete = True
        device_provisioned = True
        frp_status = "SETUP COMPLETE"
        owner_verification_required = False
        message = (
            "Device sudah menyelesaikan setup wizard. Aman untuk melanjutkan "
            "diagnostik/service standar."
        )
    else:
        setup_complete = setup_raw == "1"
        device_provisioned = provisioned_raw == "1"
        frp_status = "OWNER VERIFICATION REQUIRED"
        owner_verification_required = True
        message = (
            "Device belum menyelesaikan setup wizard / belum di-provision penuh. "
            "Wajib verifikasi kepemilikan (invoice pembelian/KTP yang sesuai) "
            "sebelum melakukan factory reset atau tindakan recovery lain."
        )

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
