"""Launch Nexa Service Tool with the Hardware Test page enabled.

This wrapper intentionally leaves the existing app.py untouched so the stable
12-page application remains recoverable while the new page is validated.
"""

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QFrame, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QHBoxLayout, QMessageBox

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from app import MainWindow
from core.hardware_test import run_hardware_test


class HardwareTestWindow(MainWindow):
    def build_ui(self):
        super().build_ui()
        self._install_hardware_page()

    def _install_hardware_page(self):
        if "hardware" in self.nav_buttons:
            return

        button = QPushButton("Hardware Test")
        button.setObjectName("navBtn")
        button.setCheckable(True)
        button.clicked.connect(lambda: self.switch_page("hardware"))
        self.nav_buttons["hardware"] = button

        sidebar = self.findChild(QFrame, "sidebar")
        if sidebar and sidebar.layout():
            layout = sidebar.layout()
            # Insert immediately before the stretch/version area.
            insert_at = max(0, layout.count() - 2)
            layout.insertWidget(insert_at, button)

        self.hardware_page = self.create_hardware_test_page()
        self.pages.addWidget(self.hardware_page)
        self.page_widgets["hardware"] = self.hardware_page

    def create_hardware_test_page(self):
        page = QFrame()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)

        title = QLabel("Hardware Test")
        title.setObjectName("contentTitle")
        desc = QLabel("Safe, read-only checks for the connected Android device.")
        desc.setObjectName("muted")
        layout.addWidget(title)
        layout.addWidget(desc)

        summary = QFrame()
        summary.setObjectName("card")
        summary_layout = QHBoxLayout(summary)
        self.hardware_score = QLabel("-- / 100")
        self.hardware_score.setObjectName("scoreBig")
        self.hardware_summary = QLabel("Run a full hardware test to collect a report.")
        self.hardware_summary.setObjectName("value")
        summary_layout.addWidget(self.hardware_score)
        summary_layout.addWidget(self.hardware_summary, 1)
        layout.addWidget(summary)

        actions = QHBoxLayout()
        run_button = QPushButton("RUN FULL HARDWARE TEST")
        run_button.setObjectName("actionPrimary")
        run_button.clicked.connect(self.run_full_hardware_test)
        refresh_button = QPushButton("Refresh")
        refresh_button.setObjectName("action")
        refresh_button.clicked.connect(self.refresh_hardware_test_status)
        actions.addWidget(run_button)
        actions.addWidget(refresh_button)
        actions.addStretch()
        layout.addLayout(actions)
        self.hardware_run_button = run_button

        self.hardware_table = QTableWidget(0, 4)
        self.hardware_table.setHorizontalHeaderLabels(["Check", "Status", "Value", "Detail"])
        self.hardware_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.hardware_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.hardware_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.hardware_table, 1)

        note = QLabel("Read-only diagnostics. Physical tests are still required for touch, speaker, microphone, camera capture, sensors and fingerprint.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        return page

    def switch_page(self, key: str):
        if key == "hardware":
            for name, btn in self.nav_buttons.items():
                btn.setChecked(name == key)
            self.pages.setCurrentWidget(self.page_widgets[key])
            self.refresh_hardware_test_status()
            return
        super().switch_page(key)

    def refresh_hardware_test_status(self):
        if not hasattr(self, "hardware_run_button"):
            return
        if not self.current_serial:
            self.hardware_score.setText("-- / 100")
            self.hardware_summary.setText("No authorized ADB device connected.")
            self.hardware_run_button.setEnabled(False)
            self.hardware_table.setRowCount(0)
            return
        self.hardware_run_button.setEnabled(True)
        self.hardware_summary.setText(f"Ready: {self.current_serial}")

    def run_full_hardware_test(self):
        if not self.current_serial:
            QMessageBox.warning(self, "No Device", "Connect and authorize an Android device first.")
            return
        self.hardware_run_button.setEnabled(False)
        QApplication.processEvents()
        try:
            report = run_hardware_test(self.current_serial)
            self.hardware_score.setText(f"{report.score} / 100")
            self.hardware_summary.setText(
                f"PASS {report.passed}  |  WARN {report.warnings}  |  FAIL {report.failed}"
            )
            self.hardware_table.setRowCount(len(report.results))
            for row, item in enumerate(report.results):
                for col, value in enumerate((item.name, item.status, item.value, item.detail)):
                    self.hardware_table.setItem(row, col, QTableWidgetItem(str(value)))
        except Exception as exc:
            QMessageBox.critical(self, "Hardware Test Error", str(exc))
        finally:
            self.hardware_run_button.setEnabled(True)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = HardwareTestWindow()
    window.show()
    raise SystemExit(app.exec())
