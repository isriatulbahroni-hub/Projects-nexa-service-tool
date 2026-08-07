"""Safe recovery planning for devices that cannot be unlocked.

This module never bypasses screen locks, account verification, or FRP.
It only assesses what can be done safely and prepares an official recovery plan.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class RecoveryPlan:
    state: str
    title: str
    actions: tuple[str, ...]
    destructive: bool = False


def plan_locked_device(*, adb_state: str = "not_detected", recovery_available: bool = False,
                       fastboot_available: bool = False, owner_account_known: bool = False) -> RecoveryPlan:
    state = adb_state.strip().lower()
    if state == "device":
        return RecoveryPlan(
            "accessible", "Device accessible",
            ("Collect read-only diagnostics", "Back up accessible data before any reset"),
        )
    if state == "unauthorized":
        return RecoveryPlan(
            "unauthorized", "ADB is not authorized",
            ("Do not attempt a lock bypass", "Use the device owner's official unlock/recovery path"),
        )
    if recovery_available or fastboot_available:
        actions = ["Use the manufacturer's official recovery procedure"]
        if owner_account_known:
            actions.append("Keep the owner's account credentials available for post-reset verification")
        else:
            actions.append("Recover the owner's account before factory reset if possible")
        actions.append("Warn that factory reset erases local data")
        return RecoveryPlan("recovery_available", "Recovery path detected", tuple(actions), True)
    return RecoveryPlan(
        "not_detected", "Device not accessible from the current connection",
        ("Check cable and drivers", "Try the manufacturer's official Recovery/Fastboot/Download mode", "Do not repeatedly guess the PIN"),
    )
