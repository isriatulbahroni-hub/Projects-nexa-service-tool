"""Safe factory-reset assistant.

This module prepares a technician for a factory reset and verifies the device
after the reset. It never performs a destructive wipe or bypasses FRP.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import List


class ResetStage(str, Enum):
    PRECHECK = "precheck"
    CONFIRMATION = "confirmation"
    RECOVERY = "recovery"
    POST_RESET = "post_reset"


@dataclass
class ResetChecklist:
    backup_confirmed: bool = False
    customer_authorized: bool = False
    data_loss_acknowledged: bool = False
    frp_warning_acknowledged: bool = False

    @property
    def ready_for_recovery(self) -> bool:
        return all((
            self.backup_confirmed,
            self.customer_authorized,
            self.data_loss_acknowledged,
            self.frp_warning_acknowledged,
        ))


@dataclass
class FactoryResetPlan:
    model: str = "Unknown device"
    stage: ResetStage = ResetStage.PRECHECK
    checklist: ResetChecklist = field(default_factory=ResetChecklist)
    warnings: List[str] = field(default_factory=list)

    def build(self) -> "FactoryResetPlan":
        self.warnings = [
            "Factory reset permanently deletes user data.",
            "A reset does not remove ownership or FRP protection.",
            "Use the manufacturer's official recovery procedure.",
        ]
        return self

    def authorize_recovery_guidance(self) -> bool:
        if not self.checklist.ready_for_recovery:
            raise ValueError("All reset safety confirmations are required.")
        self.stage = ResetStage.RECOVERY
        return True

    def post_reset_checklist(self) -> List[str]:
        self.stage = ResetStage.POST_RESET
        return [
            "Verify the device boots normally.",
            "Verify setup/owner authentication is completed by the owner.",
            "Run hardware diagnostics.",
            "Verify cellular, Wi-Fi, Bluetooth, camera, audio and charging.",
            "Record the post-reset result in the service case.",
        ]
