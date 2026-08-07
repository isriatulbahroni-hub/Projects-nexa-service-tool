"""Safe recovery helpers for service-center workflows.

This module deliberately does not bypass screen locks, FRP, or device security.
Destructive factory reset is not automated; the tool can prepare the device for
recovery and explain the data-loss consequences instead.
"""

from dataclasses import dataclass

from .adb import ADBError, get_devices_with_state, reboot_device, run_adb


@dataclass(frozen=True)
class RecoveryAction:
    action_id: str
    title: str
    risk: str
    destructive: bool
    description: str


@dataclass(frozen=True)
class AccessAssessment:
    serial: str
    adb_state: str
    can_use_adb: bool
    recommended_path: str
    warning: str


SAFE_ACTIONS = (
    RecoveryAction(
        "reboot_system",
        "Restart device",
        "SAFE",
        False,
        "Restart Android normally.",
    ),
    RecoveryAction(
        "reboot_recovery",
        "Restart to recovery",
        "CAUTION",
        False,
        "Open the device recovery environment for official maintenance options.",
    ),
    RecoveryAction(
        "reboot_bootloader",
        "Restart to bootloader",
        "CAUTION",
        False,
        "Open bootloader/fastboot mode for supported service operations.",
    ),
)


def list_recovery_actions() -> tuple[RecoveryAction, ...]:
    return SAFE_ACTIONS


def assess_access(serial: str) -> AccessAssessment:
    """Assess ADB access without attempting to defeat the screen lock."""
    serial = serial.strip()
    if not serial:
        raise ADBError("Serial perangkat wajib diisi.")

    states = get_devices_with_state()
    state = states.get(serial, "not_detected")

    if state == "device":
        return AccessAssessment(
            serial, state, True,
            "ADB tersedia; gunakan diagnosis read-only dan recovery resmi.",
            "Jangan menghapus data tanpa persetujuan pemilik.",
        )
    if state == "unauthorized":
        return AccessAssessment(
            serial, state, False,
            "Buka kunci perangkat dan setujui dialog USB debugging jika memungkinkan.",
            "Nexa tidak dapat melewati PIN/password atau otorisasi ADB.",
        )
    if state == "offline":
        return AccessAssessment(
            serial, state, False,
            "Periksa kabel, port USB, driver, lalu reboot ke recovery resmi bila diperlukan.",
            "Perangkat belum menyediakan kanal ADB yang stabil.",
        )

    return AccessAssessment(
        serial, state, False,
        "Gunakan deteksi Fastboot/Recovery dan prosedur resmi untuk model perangkat.",
        "Tidak ada kanal ADB aktif; screen-lock/FRP bypass tidak didukung.",
    )


def reboot(serial: str, mode: str = "system") -> str:
    """Reboot a connected, authorized ADB device into a supported mode."""
    if not serial.strip():
        raise ADBError("Serial perangkat wajib diisi.")
    return reboot_device(serial.strip(), mode=mode)


def clear_app_data(serial: str, package: str) -> str:
    """Clear one app's data after explicit technician confirmation.

    This does not remove device security or screen-lock credentials.
    """
    package = package.strip()
    if not serial.strip() or not package:
        raise ADBError("Serial dan package aplikasi wajib diisi.")
    if any(ch in package for ch in " ;|&`$()<>\"'"):
        raise ADBError("Nama package tidak valid.")
    return run_adb("-s", serial.strip(), "shell", "pm", "clear", package)


def factory_reset_guidance() -> str:
    """Return safe guidance instead of automating a destructive wipe."""
    return (
        "Factory reset menghapus data pengguna dan dapat memicu FRP/owner "
        "verification. Gunakan hanya jalur recovery resmi untuk model tersebut "
        "setelah backup dan persetujuan pemilik. Nexa tidak melakukan bypass FRP "
        "atau screen lock."
    )
