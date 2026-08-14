"""Reusable Qt UI for the safe Factory Reset Assistant.

The widget never performs a destructive wipe. It only validates the safety
checklist and gives the technician the official-recovery handoff.
"""
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.factory_reset_assistant import FactoryResetPlan


class FactoryResetAssistantPanel(QWidget):
    """Safety-first factory-reset preparation panel."""

    def __init__(self, model: str = "Unknown device", parent=None):
        super().__init__(parent)
        self.plan = FactoryResetPlan(model=model).build()
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)

        title = QLabel("Factory Reset Assistant")
        title.setObjectName("contentTitle")
        layout.addWidget(title)

        desc = QLabel(
            "Checklist keamanan sebelum factory reset - tool ini TIDAK pernah "
            "melakukan wipe otomatis."
        )
        desc.setObjectName("muted")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        warning = QLabel(
            "⚠ PERINGATAN: Factory reset menghapus data pengguna dan tidak "
            "menghapus FRP/ownership. Nexa tidak melakukan wipe otomatis."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("color:#ff6b6b;")
        layout.addWidget(warning)

        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(22, 18, 22, 18)
        card_layout.setSpacing(10)

        checklist_title = QLabel("Checklist Keamanan")
        checklist_title.setObjectName("cardTitle")
        card_layout.addWidget(checklist_title)

        self.backup = QCheckBox("Backup data sudah dilakukan / tidak diperlukan")
        self.authorization = QCheckBox("Customer/pemilik sudah mengizinkan reset")
        self.data_loss = QCheckBox("Kehilangan seluruh data sudah dipahami")
        self.frp = QCheckBox("Peringatan FRP/ownership sudah dipahami")

        for check in (self.backup, self.authorization, self.data_loss, self.frp):
            card_layout.addWidget(check)

        self.prepare_button = QPushButton("✅ PREPARE OFFICIAL RECOVERY")
        self.prepare_button.setObjectName("actionPrimary")
        self.prepare_button.clicked.connect(self.prepare_recovery)
        card_layout.addWidget(self.prepare_button)
        layout.addWidget(card)

        instructions_card = QFrame()
        instructions_card.setObjectName("card")
        instructions_layout = QVBoxLayout(instructions_card)
        instructions_layout.setContentsMargins(22, 18, 22, 18)
        instructions_layout.setSpacing(10)

        instructions_title = QLabel("Instruksi & Peringatan")
        instructions_title.setObjectName("cardTitle")
        instructions_layout.addWidget(instructions_title)

        self.instructions = QTextEdit()
        self.instructions.setObjectName("value")
        self.instructions.setReadOnly(True)
        self.instructions.setPlainText("\n".join(f"• {item}" for item in self.plan.warnings))
        instructions_layout.addWidget(self.instructions)

        self.post_reset_button = QPushButton("📋 SHOW POST-RESET CHECKLIST")
        self.post_reset_button.setObjectName("action")
        self.post_reset_button.clicked.connect(self.show_post_reset)
        instructions_layout.addWidget(self.post_reset_button)

        layout.addWidget(instructions_card)

    def prepare_recovery(self):
        self.plan.checklist.backup_confirmed = self.backup.isChecked()
        self.plan.checklist.customer_authorized = self.authorization.isChecked()
        self.plan.checklist.data_loss_acknowledged = self.data_loss.isChecked()
        self.plan.checklist.frp_warning_acknowledged = self.frp.isChecked()

        try:
            self.plan.authorize_recovery_guidance()
        except ValueError as exc:
            QMessageBox.warning(self, "Safety Check Belum Lengkap", str(exc))
            return

        QMessageBox.information(
            self,
            "Recovery Resmi",
            "Checklist lengkap. Lanjutkan factory reset hanya melalui "
            "prosedur Recovery resmi manufacturer. Nexa tidak melakukan wipe otomatis.",
        )

    def show_post_reset(self):
        items = self.plan.post_reset_checklist()
        self.instructions.setPlainText("\n".join(f"• {item}" for item in items))
