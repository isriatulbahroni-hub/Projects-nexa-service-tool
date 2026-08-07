"""Safe diagnostics for devices that cannot be unlocked.

This module deliberately does not bypass PIN/password/pattern/FRP protections.
It only inspects observable device state and returns safe, actionable guidance.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


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


def diagnose_access_issue(state: dict[str, Any]) -> AccessRecoveryReport:
    """Analyze state collected by ADB/fastboot/device probes.

    Expected optional keys include: adb_state, fastboot, recovery, bootloop,
    frp_detected, lockout, data_present, model, manufacturer.
    """
    frp = bool(state.get("frp_detected"))
    bootloop = bool(state.get("bootloop"))
    lockout = bool(state.get("lockout"))
    adb_state = str(state.get("adb_state", "unknown")).lower()
    fastboot = bool(state.get("fastboot"))
    recovery = bool(state.get("recovery"))

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
            "Use the manufacturer's official account-recovery or service procedure.",
            "high",
        ))
        warnings.append("Do not attempt FRP bypass. Owner verification is required.")

    if adb_state == "unauthorized":
        findings.append(RecoveryFinding(
            "ADB_UNAUTHORIZED", "attention", "ADB is unauthorized",
            "The device is visible but has not authorized this computer for ADB.",
            "Unlock the device and accept the USB debugging authorization prompt if available.",
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
            "NO_SAFE_ACTION", "info", "No unlock bypass action available",
            "The tool could not establish a safe automated recovery path.",
            "Collect model/build information and use the manufacturer's official recovery process.",
        ))

    if state.get("data_present"):
        warnings.append("User data may still be present. Avoid factory reset or flashing until data-loss impact is understood.")

    return AccessRecoveryReport(problem=problem, findings=findings, warnings=warnings)
