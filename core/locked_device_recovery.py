"""Safe recovery planning for devices that cannot be unlocked.

This module does not bypass PIN/password/pattern/FRP protections.
It identifies connected devices, determines device mode, and recommends
supported OEM recovery steps with technician confirmation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from .adb import ADBError, get_devices_with_state, run_adb
from .device import DeviceInfo, get_device_info
from .firmware import FastbootError, list_fastboot_devices, run_fastboot
from .frp_verification import (
    FRPVerification,
    FRPVerificationError,
    collect_frp_verification,
)
from .tool_router import ToolRouter


class AccessProblem(str, Enum):
    UNKNOWN = "unknown"
    FORGOT_CREDENTIAL = "forgot_credential"
    LOCKOUT = "lockout"
    BOOTLOOP = "bootloop"
    FRP_LOCK = "frp_lock"
    ADB_UNAUTHORIZED = "adb_unauthorized"
    RECOVERY_AVAILABLE = "recovery_available"
    FASTBOOT_AVAILABLE = "fastboot_available"


@dataclass(frozen=True)
class RecoveryFinding:
    code: str
    severity: str
    title: str
    detail: str
    action: str
    data_loss_risk: str = "none"


@dataclass
class AccessRecoveryReport:
    problem: AccessProblem
    findings: list[RecoveryFinding] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def requires_owner_verification(self) -> bool:
        return self.problem == AccessProblem.FRP_LOCK


@dataclass(frozen=True)
class RecoveryPlan:
    state: str
    title: str
    actions: tuple[str, ...]
    destructive: bool = False


@dataclass(frozen=True)
class LockedDeviceRecoveryState:
    serial: str
    adb_state: str
    authorized: bool
    fastboot_connected: bool
    device_identity: dict[str, str]
    device_mode: str
    frp_status: str | None
    owner_verification_required: bool | None
    recovery_options: tuple[str, ...]
    supported_actions: tuple[str, ...]
    confirmation_required: bool
    recommended_tools: tuple[str, ...]
    message: str


def diagnose_access_issue(state: dict[str, Any]) -> AccessRecoveryReport:
    """Analyze observable device state and return safe recovery findings."""
    frp = bool(state.get("frp_detected"))
    bootloop = bool(state.get("bootloop"))
    lockout = bool(state.get("lockout"))
    adb_state = str(state.get("adb_state", "unknown")).lower()
    fastboot = bool(state.get("fastboot"))
    recovery = bool(state.get("recovery"))
    data_present = bool(state.get("data_present"))

    if frp:
        problem = AccessProblem.FRP_LOCK
    elif bootloop:
        problem = AccessProblem.BOOTLOOP
    elif lockout:
        problem = AccessProblem.LOCKOUT
    elif fastboot:
        problem = AccessProblem.FASTBOOT_AVAILABLE
    elif recovery:
        problem = AccessProblem.RECOVERY_AVAILABLE
    elif adb_state == "unauthorized":
        problem = AccessProblem.ADB_UNAUTHORIZED
    else:
        problem = AccessProblem.FORGOT_CREDENTIAL

    findings: list[RecoveryFinding] = []
    warnings: list[str] = []

    if frp:
        findings.append(RecoveryFinding(
            "FRP_REQUIRED", "critical", "FRP / owner verification detected",
            "The device requires the previously authorized owner account.",
            "Use the manufacturer's official account recovery or service procedure.",
            "high",
        ))
        warnings.append("Do not attempt FRP bypass. Owner verification is required.")

    if adb_state == "unauthorized":
        findings.append(RecoveryFinding(
            "ADB_UNAUTHORIZED", "attention", "ADB is unauthorized",
            "The device is visible but has not authorized this computer for ADB.",
            "Unlock the device and accept the USB debugging authorization prompt if possible.",
        ))

    if lockout:
        findings.append(RecoveryFinding(
            "LOCKOUT", "attention", "Temporary lockout detected",
            "Repeated failed unlock attempts may have triggered a device lockout.",
            "Stop repeated attempts and follow the device's displayed timeout/recovery procedure.",
        ))

    if bootloop:
        findings.append(RecoveryFinding(
            "BOOTLOOP", "critical", "Boot loop suspected",
            "The device is not completing normal Android startup.",
            "Collect diagnostics first; use official recovery/repair procedures before any wipe or flash.",
            "medium",
        ))

    if fastboot:
        findings.append(RecoveryFinding(
            "FASTBOOT", "info", "Fastboot mode available",
            "A bootloader/fastboot interface is detectable.",
            "Identify the exact model/build before performing any firmware operation.",
            "medium",
        ))

    if recovery:
        findings.append(RecoveryFinding(
            "RECOVERY", "info", "Recovery environment available",
            "A recovery environment is detectable.",
            "Prefer official recovery options and preserve data where possible.",
            "medium",
        ))

    if not findings:
        findings.append(RecoveryFinding(
            "NO_SAFE_ACTION", "info", "No safe automated unlock action available",
            "The tool could not establish a safe automated recovery path.",
            "Collect model/build information and use the manufacturer's official recovery process.",
        ))

    if data_present:
        warnings.append(
            "User data may still be present. Avoid factory reset or flashing until the data-loss impact is understood."
        )

    return AccessRecoveryReport(problem=problem, findings=findings, warnings=warnings)


def plan_locked_device(*, adb_state: str = "not_detected", recovery_available: bool = False,
                       fastboot_available: bool = False, owner_account_known: bool = False,
                       device_mode: str = "unknown") -> RecoveryPlan:
    state = adb_state.strip().lower()

    if state == "device":
        return RecoveryPlan(
            "accessible", "Device accessible",
            ("Collect read-only diagnostics", "Back up accessible data before any reset"),
        )

    if state == "unauthorized":
        return RecoveryPlan(
            "unauthorized", "ADB is not authorized",
            ("Do not attempt to unlock or circumvent the screen lock",
             "Use the device owner's official unlock/recovery path"),
        )

    if recovery_available or fastboot_available:
        if recovery_available and not fastboot_available:
            actions = ["Use the manufacturer's official recovery procedure"]
        elif fastboot_available and not recovery_available:
            actions = ["Use the manufacturer's official bootloader/fastboot procedure"]
        else:
            actions = ["Use the manufacturer's official recovery or bootloader procedure"]

        if owner_account_known:
            actions.append("Keep the owner's account credentials available for post-reset verification")
        else:
            actions.append("Recover the owner's account before factory reset if possible")

        actions.append("Warn that factory reset erases local data")
        return RecoveryPlan("recovery_available", "Recovery path detected", tuple(actions), True)

    return RecoveryPlan(
        "not_detected", "Device not accessible from the current connection",
        ("Check cable and drivers", "Try the manufacturer's official Recovery/Fastboot/Download mode",
         "Do not repeatedly guess the PIN"),
    )


def _parse_fastboot_getvar(output: str) -> dict[str, str]:
    vars: dict[str, str] = {}
    for line in output.splitlines():
        line = line.strip()
        if not line or ": " not in line:
            continue
        key, value = line.split(": ", 1)
        vars[key.strip()] = value.strip()
    return vars


def _determine_device_mode(adb_state: str, authorized: bool, fastboot_connected: bool,
                           bootmode: str | None) -> str:
    if fastboot_connected:
        return "Fastboot / Bootloader"
    if adb_state == "unauthorized":
        return "ADB Unauthorized"
    if adb_state == "offline":
        return "Offline"
    if not authorized:
        return "No connection"
    if bootmode:
        lower = bootmode.lower()
        if "recovery" in lower:
            return "Recovery Mode"
        if "bootloader" in lower or "fastboot" in lower:
            return "Bootloader"
    return "Normal Android (ADB authorized)"


def _collect_device_identity(serial: str, authorized: bool, fastboot_vars: dict[str, str] | None,
                             device_info_fn: Callable[[str], DeviceInfo]) -> dict[str, str]:
    identity = {
        "manufacturer": "Unknown",
        "model": "Unknown",
        "product": "Unknown",
        "device": "Unknown",
        "build_id": "Unknown",
    }

    if authorized:
        try:
            info = device_info_fn(serial)
            identity.update({
                "manufacturer": info.manufacturer,
                "model": info.model,
                "product": info.product,
                "device": info.device,
                "build_id": info.build_id,
            })
        except ADBError:
            pass

    if not authorized and fastboot_vars:
        identity["manufacturer"] = fastboot_vars.get("manufacturer", fastboot_vars.get("brand", "Unknown"))
        identity["model"] = fastboot_vars.get("model", "Unknown")
        identity["product"] = fastboot_vars.get("product", "Unknown")
        identity["device"] = fastboot_vars.get("product", identity["model"])
        identity["build_id"] = fastboot_vars.get("buildid", "Unknown")

    if authorized and fastboot_vars:
        for key, source in (("manufacturer", "manufacturer"), ("model", "model"),
                             ("product", "product"), ("device", "product")):
            if identity.get(key, "Unknown") == "Unknown":
                identity[key] = fastboot_vars.get(source, identity[key])

    return identity


def _infer_brand_group(identity: dict[str, str]) -> str:
    raw = " ".join(
        identity.get(key, "") for key in (
            "manufacturer", "brand", "model", "product", "device"
        )
    ).lower()

    if "samsung" in raw:
        return "Samsung"
    if any(tag in raw for tag in ("xiaomi", "redmi", "poco")):
        return "Xiaomi / Redmi / POCO"
    if any(tag in raw for tag in ("oppo", "realme")):
        return "OPPO / realme"
    if any(tag in raw for tag in ("vivo", "iqoo")):
        return "vivo / iQOO"
    if any(tag in raw for tag in ("infinix", "tecno")):
        return "Infinix / TECNO"
    if any(tag in raw for tag in ("motorola", "moto")):
        return "Motorola"
    if any(tag in raw for tag in ("nokia", "hmd")):
        return "Nokia / HMD"
    if "oneplus" in raw:
        return "OnePlus"
    return "Unknown"


def _build_recovery_options(device_mode: str, authorized: bool,
                            owner_verification_required: bool | None) -> tuple[str, ...]:
    options: list[str] = []

    if device_mode == "Fastboot / Bootloader":
        options.extend([
            "Use bootloader/fastboot only for official firmware or diagnostics.",
            "Identify the exact model/build before any flash operation.",
        ])
    elif device_mode == "Recovery Mode":
        options.extend([
            "Use recovery menu options provided by the manufacturer.",
            "Avoid data wipe unless the owner consents and understands the loss.",
        ])
    elif device_mode == "Normal Android (ADB authorized)":
        options.extend([
            "Collect diagnostics before any recovery reboot.",
            "Prefer rebooting to recovery or bootloader for official service paths.",
        ])
    elif device_mode == "ADB Unauthorized":
        options.append("Authorize USB debugging on-device or use official hardware recovery keys.")
    elif device_mode == "Offline":
        options.append("Check cable, USB port, and battery. Retry once the device responds.")
    else:
        options.append("No active recovery connection detected. Use the OEM recovery routine.")

    if owner_verification_required:
        options.append("Owner/OEM verification is required before any reset or FRP-sensitive operation.")

    return tuple(options)


def _build_supported_actions(authorized: bool, fastboot_connected: bool,
                             device_mode: str, owner_verification_required: bool | None) -> tuple[str, ...]:
    actions: list[str] = []

    if authorized:
        if not owner_verification_required and device_mode in (
            "Normal Android (ADB authorized)",
            "Recovery Mode",
            "Fastboot / Bootloader",
        ):
            actions.extend(["reboot_recovery", "reboot_bootloader"])
        actions.append("verify_result")

    return tuple(actions)


def _collect_fastboot_vars(serial: str, run_fastboot_fn: Callable[..., str]) -> dict[str, str] | None:
    try:
        output = run_fastboot_fn("-s", serial, "getvar", "all")
        return _parse_fastboot_getvar(output)
    except FastbootError:
        return None


def detect_locked_device_recovery_state(
    serial: str,
    *,
    devices_fn: Callable[[], dict[str, str]] = get_devices_with_state,
    fastboot_fn: Callable[[], list[str]] = list_fastboot_devices,
    run_adb_fn: Callable[..., str] = run_adb,
    run_fastboot_fn: Callable[..., str] = run_fastboot,
    device_info_fn: Callable[[str], DeviceInfo] = get_device_info,
    frp_fn: Callable[..., FRPVerification] = collect_frp_verification,
) -> LockedDeviceRecoveryState:
    serial = serial.strip()
    if not serial:
        raise ValueError("Serial perangkat kosong.")

    devices = devices_fn()
    adb_state = devices.get(serial, "not_detected")
    fastboot_devices = fastboot_fn()
    fastboot_connected = serial in fastboot_devices
    authorized = adb_state == "device"

    bootmode = None
    if authorized:
        try:
            bootmode = run_adb_fn("-s", serial, "shell", "getprop", "ro.bootmode").strip()
        except ADBError:
            bootmode = None

    fastboot_vars = None
    if fastboot_connected:
        fastboot_vars = _collect_fastboot_vars(serial, run_fastboot_fn)

    frp_status = None
    owner_verification_required = None
    if authorized:
        try:
            verification = frp_fn(serial)
            frp_status = verification.frp_status
            owner_verification_required = verification.owner_verification_required
        except FRPVerificationError:
            frp_status = "UNKNOWN"
            owner_verification_required = None

    identity = _collect_device_identity(serial, authorized, fastboot_vars, device_info_fn)
    device_mode = _determine_device_mode(adb_state, authorized, fastboot_connected, bootmode)
    recovery_options = _build_recovery_options(device_mode, authorized, owner_verification_required)
    supported_actions = _build_supported_actions(authorized, fastboot_connected, device_mode, owner_verification_required)
    confirmation_required = any(
        action in supported_actions for action in ("reboot_recovery", "reboot_bootloader")
    )

    router = ToolRouter()
    recommended_tools = tuple(
        router.select_tools_for_device(
            brand_group=_infer_brand_group(identity),
            device_mode=device_mode,
            fastboot_connected=fastboot_connected,
            authorized=authorized,
        )
    )

    message = "Locked device recovery workflow detected."

    if device_mode == "No connection":
        message = "Device is not connected via ADB or Fastboot."
    elif device_mode == "ADB Unauthorized":
        message = "Device requires USB debugging authorization before any recovery operations."
    elif owner_verification_required:
        message = "Owner/OEM verification is required before FRP-sensitive recovery actions."

    return LockedDeviceRecoveryState(
        serial=serial,
        adb_state=adb_state,
        authorized=authorized,
        fastboot_connected=fastboot_connected,
        device_identity=identity,
        device_mode=device_mode,
        frp_status=frp_status,
        owner_verification_required=owner_verification_required,
        recovery_options=recovery_options,
        supported_actions=supported_actions,
        confirmation_required=confirmation_required,
        message=message,
    )
