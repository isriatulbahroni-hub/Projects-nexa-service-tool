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
        layout.setSpacing(10)

        title = QLabel("Factory Reset Assistant")
        title.setObjectName("contentTitle")
        layout.addWidget(title)

        warning = QLabel(
            "PERINGATAN: Factory reset menghapus data pengguna dan tidak "
            "menghapus FRP/ownership. Nexa tidak melakukan wipe otomatis."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("color:#ff6b6b;")
        layout.addWidget(warning)

        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)

        self.backup = QCheckBox("Backup data sudah dilakukan / tidak diperlukan")
        self.authorization = QCheckBox("Customer/pemilik sudah mengizinkan reset")
        self.data_loss = QCheckBox("Kehilangan seluruh data sudah dipahami")
        self.frp = QCheckBox("Peringatan FRP/ownership sudah dipahami")

        for check in (self.backup, self.authorization, self.data_loss, self.frp):
            card_layout.addWidget(check)

        self.prepare_button = QPushButton("PREPARE OFFICIAL RECOVERY")
        self.prepare_button.setObjectName("actionPrimary")
        self.prepare_button.clicked.connect(self.prepare_recovery)
        card_layout.addWidget(self.prepare_button)
        layout.addWidget(card)

        self.instructions = QTextEdit()
        self.instructions.setReadOnly(True)
        self.instructions.setPlainText("\n".join(f"• {item}" for item in self.plan.warnings))
        layout.addWidget(self.instructions)

        self.post_reset_button = QPushButton("SHOW POST-RESET CHECKLIST")
        self.post_reset_button.setObjectName("action")
        self.post_reset_button.clicked.connect(self.show_post_reset)
        layout.addWidget(self.post_reset_button)

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
