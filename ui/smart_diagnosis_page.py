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
from core.async_worker import AsyncWorker


class SmartDiagnosisPage(QWidget):
    def __init__(
        self,
        facts_provider: Callable[[], dict[str, Any]] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.facts_provider = facts_provider
        self.last_report: DiagnosisReport | None = None
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
        # PENTING: jangan connect langsung ke self.run_scan di sini.
        # QPushButton.clicked selalu mengirim parameter `checked` (bool)
        # ke slot yang terhubung. Karena run_scan(self, facts=None)
        # menerima 1 parameter opsional, PySide otomatis meneruskan bool
        # itu sebagai `facts` - lalu diagnose(False) di dalamnya crash
        # (AttributeError: 'bool' object has no attribute 'get') SETIAP
        # kali tombol diklik. Ini penyebab sebenarnya "Smart Scan tidak
        # bisa diklik" - bukan freeze, tapi exception tak tertangani tiap
        # klik. Lambda di bawah memastikan run_scan() selalu dipanggil
        # tanpa argumen dari tombol.
        self.run_button.clicked.connect(lambda checked=False: self.run_scan())
        actions.addWidget(self.run_button)
        actions.addStretch()
        layout.addLayout(actions)

        self.findings_table = QTableWidget(0, 4)
        self.findings_table.setHorizontalHeaderLabels(["Code", "Severity", "Finding", "Summary"])
        self.findings_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.findings_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.findings_table, 2)

        rec_title = QLabel("Rekomendasi Aman")
        rec_title.setObjectName("cardTitle")
        layout.addWidget(rec_title)
        self.recommendations = QPlainTextEdit()
        self.recommendations.setReadOnly(True)
        layout.addWidget(self.recommendations, 1)

    def run_scan(self, facts: dict[str, Any] | None = None) -> DiagnosisReport | None:
        if facts is not None:
            # Facts eksplisit diberikan (mis. dari kode lain/test) - jalankan
            # sinkron seperti sebelumnya, tidak ada ADB call yang perlu
            # dikhawatirkan bikin freeze.
            report = diagnose(facts)
            self._apply_report(report)
            return report

        # PENTING: tanpa facts eksplisit, jalur ini dipanggil dari tombol
        # "RUN SMART SCAN" di UI. facts_provider() (di app.py) melakukan
        # BEBERAPA call ADB blocking secara berurutan (diagnostics, network
        # info, security check) - sebelumnya semua ini dijalankan LANGSUNG
        # di main GUI thread saat tombol diklik, membuat seluruh aplikasi
        # freeze total tanpa indikator apapun selama beberapa detik (lebih
        # lama lagi kalau salah satu call timeout). Dari sisi user ini
        # kerasa seperti "tombolnya tidak bisa diklik" padahal sebenarnya
        # UI-nya cuma macet. Sekarang dijalankan di background thread,
        # sama seperti pola AsyncWorker yang dipakai di seluruh app.
        if getattr(self, "_scan_worker", None) and self._scan_worker.isRunning():
            return None

        self.run_button.setEnabled(False)
        self.run_button.setText("SCANNING...")
        self.status_label.setText("⏳ Mengumpulkan data device...")

        def _task():
            collected = self.facts_provider() if self.facts_provider else {}
            return diagnose(collected)

        worker = AsyncWorker(_task, self)

        def _on_success(report: DiagnosisReport):
            self._apply_report(report)
            self.run_button.setEnabled(True)
            self.run_button.setText("RUN SMART SCAN")

        def _on_failure(message: str):
            self.status_label.setText(f"❌ Gagal menjalankan scan: {message}")
            self.run_button.setEnabled(True)
            self.run_button.setText("RUN SMART SCAN")

        worker.succeeded.connect(_on_success)
        worker.failed.connect(_on_failure)
        self._scan_worker = worker
        worker.start()
        return None

    def _apply_report(self, report: DiagnosisReport) -> None:
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
