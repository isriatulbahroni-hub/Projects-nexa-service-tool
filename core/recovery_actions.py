"""Safe, explicit recovery actions for service-center workflows.

This module deliberately does not bypass screen locks, FRP, or device security.
Destructive factory reset is not automated; the tool can prepare the device for
recovery and explain the data-loss consequences instead.
"""

from dataclasses import dataclass

from .adb import ADBError, reboot_device, run_adb


@dataclass(frozen=True)
class RecoveryAction:
    action_id: str
    title: str
    risk: str
    destructive: bool
    description: str


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
