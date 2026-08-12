"""Reusable Smart Diagnosis Qt page.

The page is intentionally decoupled from MainWindow: the host can feed a
normalized facts dictionary collected from existing Nexa modules.
"""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.smart_diagnosis import DiagnosisReport, diagnose
from core.usb_diagnostics import UsbDiagnosticsReport, collect_usb_diagnostics


class SmartDiagnosisPage(QWidget):
    def __init__(
        self,
        facts_provider: Callable[[], dict[str, Any]] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.facts_provider = facts_provider
        self.last_report: DiagnosisReport | None = None
        self.last_usb_report: UsbDiagnosticsReport | None = None
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(14)

        title = QLabel("Smart Diagnosis")
        title.setObjectName("contentTitle")
        desc = QLabel("Rule-based diagnosis dari data device yang sudah dikumpulkan Nexa.")
        desc.setObjectName("muted")
        layout.addWidget(title)
        layout.addWidget(desc)

        summary = QFrame()
        summary.setObjectName("card")
        summary_layout = QHBoxLayout(summary)
        self.score_label = QLabel("-- / 100")
        self.score_label.setObjectName("scoreBig")
        self.status_label = QLabel("Belum dijalankan")
        self.status_label.setObjectName("value")
        summary_layout.addWidget(self.score_label)
        summary_layout.addWidget(self.status_label, 1)
        layout.addWidget(summary)

        self.score_bar = QProgressBar()
        self.score_bar.setRange(0, 100)
        self.score_bar.setValue(0)
        layout.addWidget(self.score_bar)

        actions = QHBoxLayout()
        self.run_button = QPushButton("RUN SMART SCAN")
        self.run_button.setObjectName("actionPrimary")
        self.run_button.clicked.connect(self.run_scan)
        actions.addWidget(self.run_button)

        self.run_usb_button = QPushButton("CHECK USB / ADB")
        self.run_usb_button.setObjectName("action")
        self.run_usb_button.clicked.connect(self.run_usb_scan)
        actions.addWidget(self.run_usb_button)
        actions.addStretch()
        layout.addLayout(actions)

        self.findings_table = QTableWidget(0, 4)
        self.findings_table.setHorizontalHeaderLabels(["Code", "Severity", "Finding", "Summary"])
        self.findings_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.findings_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.findings_table, 2)

        usb_title = QLabel("USB / CONNECTION DIAGNOSTICS")
        usb_title.setObjectName("cardTitle")
        layout.addWidget(usb_title)

        self.usb_status = QLabel("Belum diperiksa")
        self.usb_status.setObjectName("value")
        layout.addWidget(self.usb_status)

        self.usb_details = QPlainTextEdit()
        self.usb_details.setReadOnly(True)
        self.usb_details.setMaximumHeight(150)
        layout.addWidget(self.usb_details)

        rec_title = QLabel("Rekomendasi Aman")
        rec_title.setObjectName("cardTitle")
        layout.addWidget(rec_title)
        self.recommendations = QPlainTextEdit()
        self.recommendations.setReadOnly(True)
        layout.addWidget(self.recommendations, 1)

    def run_scan(self, facts: dict[str, Any] | None = None) -> DiagnosisReport:
        if facts is None:
            facts = self.facts_provider() if self.facts_provider else {}
        report = diagnose(facts)
        self.last_report = report
        self.score_label.setText(f"{report.score} / 100")
        self.status_label.setText(report.severity.upper())
        self.score_bar.setValue(report.score)

        self.findings_table.setRowCount(len(report.findings))
        for row, finding in enumerate(report.findings):
            values = (finding.code, finding.severity.upper(), finding.title, finding.summary)
            for column, value in enumerate(values):
                self.findings_table.setItem(row, column, QTableWidgetItem(str(value)))

        self.recommendations.setPlainText(
            "\n".join(f"• {item}" for item in report.recommendations)
        )
        return report

    def run_usb_scan(self) -> UsbDiagnosticsReport:
        """Run read-only USB/ADB detection and render the result."""
        report = collect_usb_diagnostics()
        self.last_usb_report = report

        usb_count = len(report.usb_devices)
        serial_count = len(report.serial_ports)
        adb_count = len(report.adb_devices)
        samsung = "Detected" if report.samsung_usb_detected else "Not detected"

        self.usb_status.setText(
            f"USB devices: {usb_count} | Serial/COM: {serial_count} | "
            f"ADB devices: {adb_count} | Samsung USB: {samsung}"
        )

        lines = [
            f"Windows PnP: {'available' if report.pnp_available else 'unavailable'}",
            f"ADB executable: {'available' if report.adb_available else 'not found'}",
            f"PyUSB backend: {report.pyusb_backend}",
        ]
        for device in report.usb_devices[:12]:
            ids = ""
            if device.vendor_id or device.product_id:
                ids = f" [{device.vendor_id}:{device.product_id}]"
            lines.append(f"USB: {device.friendly_name}{ids}")
        for port in report.serial_ports[:8]:
            lines.append(f"PORT: {port.name} - {port.description}")
        for device in report.adb_devices[:8]:
            lines.append(f"ADB: {device.get('serial', '?')} - {device.get('state', '?')}")

        if not report.usb_devices:
            lines.append("Diagnosis: Windows is not currently enumerating a USB/modem/port device.")
        elif not report.adb_devices:
            lines.append("Diagnosis: USB is visible, but no ADB device is currently available.")

        self.usb_details.setPlainText("\n".join(lines))
        return report
