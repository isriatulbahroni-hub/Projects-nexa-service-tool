"""Reusable Smart Diagnosis 2.0 Qt panel.

The panel is intentionally read-only: it consumes normalized facts and renders
explainable findings. It never bypasses PIN/pattern/password/FRP or changes
device identity/security state.
"""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.smart_diagnosis import DiagnosisReport, diagnose


PROBLEM_PROFILES: dict[str, dict[str, str]] = {
    "General / Full Scan": {"connection_state": ""},
    "Tidak bisa masuk / lupa PIN": {"access_issue": "locked"},
    "Bootloop / restart terus": {"boot_issue": "bootloop"},
    "Tidak ada sinyal": {"network_state": "no_service"},
    "Wi-Fi / Bluetooth bermasalah": {"network_issue": "wireless"},
    "Baterai boros / panas": {"battery_issue": "thermal"},
}


class SmartDiagnosisPanel(QWidget):
    """UI panel for selecting a complaint and rendering a diagnosis report.

    ``collect_facts`` receives the selected problem key and must return a dict
    containing only facts already available to the service application.
    """

    def __init__(
        self,
        collect_facts: Callable[[str], dict[str, Any]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.collect_facts = collect_facts
        self.last_report: DiagnosisReport | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel("Smart Diagnosis 2.0")
        title.setObjectName("contentTitle")
        desc = QLabel(
            "Pilih keluhan. Nexa menggabungkan fakta perangkat dan memberi "
            "diagnosis yang dapat dijelaskan."
        )
        desc.setObjectName("muted")
        layout.addWidget(title)
        layout.addWidget(desc)

        selector_row = QHBoxLayout()
        self.problem_selector = QComboBox()
        self.problem_selector.addItems(PROBLEM_PROFILES.keys())
        self.scan_button = QPushButton("RUN SMART SCAN")
        self.scan_button.setObjectName("actionPrimary")
        self.scan_button.clicked.connect(self.run_scan)
        selector_row.addWidget(self.problem_selector, 1)
        selector_row.addWidget(self.scan_button)
        layout.addLayout(selector_row)

        summary = QFrame()
        summary.setObjectName("card")
        summary_layout = QHBoxLayout(summary)
        self.score_label = QLabel("-- / 100")
        self.score_label.setObjectName("scoreBig")
        self.severity_label = QLabel("Belum dipindai")
        self.severity_label.setObjectName("status")
        summary_layout.addWidget(self.score_label)
        summary_layout.addWidget(self.severity_label, 1)
        layout.addWidget(summary)

        self.findings_table = QTableWidget(0, 4)
        self.findings_table.setHorizontalHeaderLabels(
            ["Severity", "Finding", "Bukti", "Tindakan aman"]
        )
        self.findings_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.findings_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.findings_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.findings_table, 1)

        self.recommendations = QLabel("Belum ada rekomendasi.")
        self.recommendations.setWordWrap(True)
        self.recommendations.setObjectName("value")
        layout.addWidget(self.recommendations)

    def run_scan(self) -> DiagnosisReport | None:
        problem = self.problem_selector.currentText()
        try:
            facts = dict(self.collect_facts(problem))
        except Exception as exc:
            QMessageBox.warning(self, "Smart Diagnosis", f"Gagal mengambil data perangkat: {exc}")
            return None

        # Keep the complaint context separate from raw device facts.
        facts["complaint"] = problem
        report = diagnose(facts)
        self.last_report = report
        self._render(report)
        return report

    def _render(self, report: DiagnosisReport) -> None:
        self.score_label.setText(f"{report.score} / 100")
        self.severity_label.setText(report.severity.upper())
        self.findings_table.setRowCount(len(report.findings))

        for row, finding in enumerate(report.findings):
            self.findings_table.setItem(row, 0, QTableWidgetItem(finding.severity.upper()))
            self.findings_table.setItem(row, 1, QTableWidgetItem(finding.title))
            self.findings_table.setItem(row, 2, QTableWidgetItem(finding.summary))
            self.findings_table.setItem(
                row, 3, QTableWidgetItem("\n".join(finding.recommendations))
            )

        if report.recommendations:
            self.recommendations.setText(
                "Rekomendasi:\n• " + "\n• ".join(report.recommendations)
            )

    def report_dict(self) -> dict[str, Any] | None:
        return self.last_report.to_dict() if self.last_report else None
