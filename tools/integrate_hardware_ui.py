from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise SystemExit(f"Cannot find insertion point: {label}")
    return text.replace(old, new, 1)


def main() -> None:
    text = APP.read_text(encoding="utf-8")

    text = replace_once(
        text,
        "from core.network_info import get_network_info\n",
        "from core.network_info import get_network_info\nfrom core.hardware_test import run_hardware_test\n",
        "hardware import",
    )

    text = replace_once(
        text,
        '            ("firmware", "Firmware & Flash"),\n',
        '            ("firmware", "Firmware & Flash"),\n            ("hardware", "Hardware Test"),\n',
        "hardware nav",
    )

    text = replace_once(
        text,
        "        self.firmware_page = self.create_firmware_page()\n",
        "        self.firmware_page = self.create_firmware_page()\n        self.hardware_page = self.create_hardware_test_page()\n",
        "hardware page construction",
    )

    text = replace_once(
        text,
        "        self.pages.addWidget(self.firmware_page)\n",
        "        self.pages.addWidget(self.firmware_page)\n        self.pages.addWidget(self.hardware_page)\n",
        "hardware widget",
    )

    text = replace_once(
        text,
        '            "firmware": self.firmware_page,\n',
        '            "firmware": self.firmware_page,\n            "hardware": self.hardware_page,\n',
        "hardware mapping",
    )

    text = replace_once(
        text,
        '        elif key == "firmware":\n            self.refresh_firmware_info()\n',
        '        elif key == "firmware":\n            self.refresh_firmware_info()\n        elif key == "hardware":\n            self.refresh_hardware_test_status()\n',
        "hardware switch",
    )

    marker = "    # ------------------------------------------------------------------\n    # Device Page\n"
    page_code = '''    # ------------------------------------------------------------------\n    # Hardware Test Page\n    # ------------------------------------------------------------------\n\n    def create_hardware_test_page(self):\n        page = QWidget()\n        layout = QVBoxLayout(page)\n        layout.setContentsMargins(32, 28, 32, 28)\n        layout.setSpacing(16)\n\n        title = QLabel("Hardware Test")\n        title.setObjectName("contentTitle")\n        desc = QLabel("Safe, read-only checks for the connected Android device.")\n        desc.setObjectName("muted")\n        layout.addWidget(title)\n        layout.addWidget(desc)\n\n        summary = QFrame()\n        summary.setObjectName("card")\n        summary_layout = QHBoxLayout(summary)\n        summary_layout.setContentsMargins(20, 16, 20, 16)\n        self.hardware_score = QLabel("-- / 100")\n        self.hardware_score.setObjectName("scoreBig")\n        self.hardware_summary = QLabel("Run a full hardware test to collect a report.")\n        self.hardware_summary.setObjectName("value")\n        summary_layout.addWidget(self.hardware_score)\n        summary_layout.addWidget(self.hardware_summary, 1)\n        layout.addWidget(summary)\n\n        actions = QHBoxLayout()\n        self.hardware_run_button = QPushButton("RUN FULL HARDWARE TEST")\n        self.hardware_run_button.setObjectName("actionPrimary")\n        self.hardware_run_button.clicked.connect(self.run_full_hardware_test)\n        self.hardware_refresh_button = QPushButton("Refresh")\n        self.hardware_refresh_button.setObjectName("action")\n        self.hardware_refresh_button.clicked.connect(self.refresh_hardware_test_status)\n        actions.addWidget(self.hardware_run_button)\n        actions.addWidget(self.hardware_refresh_button)\n        actions.addStretch()\n        layout.addLayout(actions)\n\n        self.hardware_table = QTableWidget(0, 4)\n        self.hardware_table.setHorizontalHeaderLabels(["Check", "Status", "Value", "Detail"])\n        self.hardware_table.setEditTriggers(QTableWidget.NoEditTriggers)\n        self.hardware_table.setSelectionBehavior(QTableWidget.SelectRows)\n        self.hardware_table.horizontalHeader().setStretchLastSection(True)\n        layout.addWidget(self.hardware_table, 1)\n\n        warning = QLabel("Read-only diagnostics: camera, speaker, microphone, sensors, fingerprint and touchscreen still require physical interaction tests.")\n        warning.setObjectName("muted")\n        warning.setWordWrap(True)\n        layout.addWidget(warning)\n        return page\n\n    def refresh_hardware_test_status(self):\n        if not self.current_serial:\n            self.hardware_score.setText("-- / 100")\n            self.hardware_summary.setText("No authorized ADB device connected.")\n            self.hardware_run_button.setEnabled(False)\n            self.hardware_table.setRowCount(0)\n            return\n        self.hardware_run_button.setEnabled(True)\n        self.hardware_summary.setText(f"Ready: {self.current_serial}")\n\n    def run_full_hardware_test(self):\n        if not self.current_serial:\n            QMessageBox.warning(self, "No Device", "Connect and authorize an Android device first.")\n            return\n        self.hardware_run_button.setEnabled(False)\n        QApplication.processEvents()\n        try:\n            report = run_hardware_test(self.current_serial)\n            self.hardware_score.setText(f"{report.score} / 100")\n            self.hardware_summary.setText(\n                f"PASS {report.passed}  |  WARN {report.warnings}  |  FAIL {report.failed}"\n            )\n            self.hardware_table.setRowCount(len(report.results))\n            for row, item in enumerate(report.results):\n                values = [item.name, item.status, item.value, item.detail]\n                for col, value in enumerate(values):\n                    self.hardware_table.setItem(row, col, QTableWidgetItem(str(value)))\n            self.last_hardware_report = report\n        except Exception as exc:\n            QMessageBox.critical(self, "Hardware Test Error", str(exc))\n        finally:\n            self.hardware_run_button.setEnabled(True)\n\n'''
    text = replace_once(text, marker, page_code + marker, "hardware page methods")

    APP.write_text(text, encoding="utf-8")
    print("Hardware Test UI integrated successfully")


if __name__ == "__main__":
    main()
