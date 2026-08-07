"""Controlled factory-reset workflow for authorized service work.

The module never bypasses screen locks or FRP and never silently wipes a device.
It only prepares an authorized ADB device for the manufacturer's recovery flow.
"""

from dataclasses import dataclass

from .adb import ADBError, get_devices_with_state, reboot_device


@dataclass(frozen=True)
class ResetPlan:
    serial: str
    ready: bool
    action: str
    warnings: tuple[str, ...]


def prepare_factory_reset(serial: str, *, owner_confirmed: bool, backup_confirmed: bool) -> ResetPlan:
    """Prepare, but do not execute, a factory reset through official recovery."""
    serial = serial.strip()
    if not serial:
        raise ADBError("Serial perangkat wajib diisi.")

    warnings = (
        "Factory reset menghapus data pengguna secara permanen.",
        "FRP/akun pemilik tetap dapat diminta setelah reset.",
        "Nexa tidak melewati PIN, password, atau FRP.",
    )

    if not owner_confirmed or not backup_confirmed:
        return ResetPlan(serial, False, "confirmation_required", warnings)

    state = get_devices_with_state().get(serial, "not_detected")
    if state != "device":
        return ResetPlan(serial, False, "device_not_ready", warnings + (f"ADB state: {state}.",))

    return ResetPlan(serial, True, "reboot_to_official_recovery", warnings)


def start_official_recovery_reset(serial: str, *, owner_confirmed: bool, backup_confirmed: bool) -> str:
    """Reboot an authorized device to recovery; the wipe remains a manual recovery action."""
    plan = prepare_factory_reset(
        serial, owner_confirmed=owner_confirmed, backup_confirmed=backup_confirmed
    )
    if not plan.ready:
        raise ADBError(f"Factory reset belum siap: {plan.action}")
    return reboot_device(serial.strip(), mode="recovery")
