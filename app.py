import sys
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.adb import ADBError, get_devices_with_state, reboot_device, run_adb
from core.config import ADB_PATH
from core.device import get_device_info
from core.diagnostics import (
    compute_health_score,
    get_diagnostics,
    health_score_label,
)
from core.database import get_history, save_service_record
from core.logcat import LogcatStreamer
from core.report import generate_service_report
from core.packages import (
    list_packages,
    install_apk,
    uninstall_package,
    force_stop,
    clear_app_data,
)
from core.file_explorer import (
    list_dir,
    normalize_path,
    go_up,
    pull_file,
    push_file,
    delete_remote,
)
from core.mirror import ScreenMirror, send_tap, send_swipe, send_key
from core.backup import backup_device, restore_device
from core.security_check import run_security_check
from core.firmware import (
    get_build_info,
    list_fastboot_devices,
    flash_partition,
    reboot_from_fastboot,
    COMMON_PARTITIONS,
    CRITICAL_PARTITIONS,
    FastbootError,
)
from core.network_info import get_network_info
from core.hardware_test import run_hardware_test


STYLESHEET = """
QMainWindow {
    background: #0d0f13;
}

QWidget {
    font-family: 'Segoe UI', sans-serif;
}

QLabel {
    color: #e8eaed;
}

#sidebar {
    background: #14161c;
    border-right: 1px solid #22262f;
}

#brand {
    font-size: 20px;
    font-weight: 700;
    color: #ffffff;
}

#subtitle, #muted {
    color: #7d8590;
    font-size: 12px;
}

#navBtn {
    background: transparent;
    color: #b7bdc7;
    border: none;
    text-align: left;
    padding: 11px 14px;
    border-radius: 8px;
    font-size: 14px;
}

#navBtn:hover {
    background: #1d212a;
    color: white;
}

#navBtn:checked {
    background: #ff5a1f;
    color: white;
    font-weight: 600;
}

#deviceSelector {
    background: #1a1d24;
    color: white;
    border: 1px solid #2b2f3a;
    border-radius: 8px;
    padding: 8px 10px;
    font-size: 13px;
}

#contentTitle {
    font-size: 26px;
    font-weight: 700;
    color: white;
}

#card {
    background: #14161c;
    border: 1px solid #22262f;
    border-radius: 14px;
}

#cardTitle {
    font-size: 15px;
    font-weight: 600;
    color: white;
}

#status {
    font-size: 15px;
    font-weight: 600;
}

#value {
    color: #d3d7de;
    font-size: 13px;
}

#action {
    background: #1a1d24;
    color: white;
    border: 1px solid #2b2f3a;
    text-align: center;
    padding: 10px 16px;
    border-radius: 8px;
    font-size: 13px;
}

#action:hover {
    background: #23272f;
}

#actionPrimary {
    background: #ff5a1f;
    color: white;
    border: none;
    text-align: center;
    padding: 10px 16px;
    border-radius: 8px;
    font-weight: 600;
    font-size: 13px;
}

#actionPrimary:hover {
    background: #ff6f3c;
}

#actionDanger {
    background: transparent;
    color: #ff6b6b;
    border: 1px solid #4a2323;
    text-align: center;
    padding: 10px 16px;
    border-radius: 8px;
    font-size: 13px;
}

#actionDanger:hover {
    background: #241414;
}

#scoreBig {
    font-size: 42px;
    font-weight: 800;
}

#logConsole {
    background: #0a0b0e;
    color: #b7ffb0;
    border: 1px solid #22262f;
    border-radius: 10px;
    font-family: Consolas, monospace;
    font-size: 12px;
}

QTableWidget {
    background: #14161c;
    color: #d3d7de;
    border: 1px solid #22262f;
    border-radius: 10px;
    gridline-color: #22262f;
}

QHeaderView::section {
    background: #1a1d24;
    color: #b7bdc7;
    padding: 6px;
    border: none;
    font-size: 12px;
}

QProgressBar {
    background: #1a1d24;
    border: none;
    border-radius: 6px;
    height: 10px;
    text-align: center;
    color: transparent;
}

QProgressBar::chunk {
    border-radius: 6px;
}
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Nexa Service Tool")
        self.resize(1200, 760)

        self.devices: dict[str, str] = {}
        self.current_serial: str | None = None
        self.current_device = None
        self.last_diag = None
        self.last_score = None
        self.last_recommendations: list[str] = []

        self.logcat_streamer: LogcatStreamer | None = None
        self.screen_mirror: ScreenMirror | None = None
        self.file_explorer_path = "/sdcard"

        self.setStyleSheet(STYLESHEET)

        self.build_ui()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_device_list)
        self.timer.start(1500)

        self.refresh_device_list()

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def build_ui(self):
        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(230)

        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(18, 24, 18, 18)
        side_layout.setSpacing(6)

        brand = QLabel("Nexa Service Tool")
        brand.setObjectName("brand")

        subtitle = QLabel("Professional Service Center")
        subtitle.setObjectName("subtitle")

        side_layout.addWidget(brand)
        side_layout.addWidget(subtitle)
        side_layout.addSpacing(18)

        device_label = QLabel("ACTIVE DEVICE")
        device_label.setObjectName("subtitle")
        side_layout.addWidget(device_label)

        self.device_selector = QComboBox()
        self.device_selector.setObjectName("deviceSelector")
        self.device_selector.currentIndexChanged.connect(self.on_device_selected)
        side_layout.addWidget(self.device_selector)

        side_layout.addSpacing(20)

        self.nav_buttons: dict[str, QPushButton] = {}

        nav_items = [
            ("dashboard", "Dashboard"),
            ("device", "Device"),
            ("diagnostics", "Diagnostics"),
            ("security", "Security Check"),
            ("apps", "App Manager"),
            ("files", "File Explorer"),
            ("mirror", "Screen Mirror"),
            ("backup", "Backup & Restore"),
            ("network", "Network & IMEI"),
            ("logs", "Live Logs"),
            ("history", "Service History"),
            ("firmware", "Firmware & Flash"),
            ("hardware", "Hardware Test"),
        ]

        for key, label in nav_items:
            btn = QPushButton(label)
            btn.setObjectName("navBtn")
            btn.setCheckable(True)
            btn.clicked.connect(lambda _, k=key: self.switch_page(k))
            side_layout.addWidget(btn)
            self.nav_buttons[key] = btn

        side_layout.addStretch()

        version = QLabel("Nexa Service Tool v0.2 - Smart Edition")
        version.setObjectName("subtitle")
        version.setWordWrap(True)
        side_layout.addWidget(version)

        self.pages = QStackedWidget()

        self.dashboard_page = self.create_dashboard_page()
        self.device_page = self.create_device_page()
        self.diagnostics_page = self.create_diagnostics_page()
        self.security_page = self.create_security_page()
        self.apps_page = self.create_apps_page()
        self.files_page = self.create_files_page()
        self.mirror_page = self.create_mirror_page()
        self.backup_page = self.create_backup_page()
        self.network_page = self.create_network_page()
        self.logs_page = self.create_logs_page()
        self.history_page = self.create_history_page()
        self.firmware_page = self.create_firmware_page()
        self.hardware_page = self.create_hardware_test_page()

        self.pages.addWidget(self.dashboard_page)
        self.pages.addWidget(self.device_page)
        self.pages.addWidget(self.diagnostics_page)
        self.pages.addWidget(self.security_page)
        self.pages.addWidget(self.apps_page)
        self.pages.addWidget(self.files_page)
        self.pages.addWidget(self.mirror_page)
        self.pages.addWidget(self.backup_page)
        self.pages.addWidget(self.network_page)
        self.pages.addWidget(self.logs_page)
        self.pages.addWidget(self.history_page)
        self.pages.addWidget(self.firmware_page)
        self.pages.addWidget(self.hardware_page)

        self.page_widgets = {
            "dashboard": self.dashboard_page,
            "device": self.device_page,
            "diagnostics": self.diagnostics_page,
            "security": self.security_page,
            "apps": self.apps_page,
            "files": self.files_page,
            "mirror": self.mirror_page,
            "backup": self.backup_page,
            "network": self.network_page,
            "logs": self.logs_page,
            "history": self.history_page,
            "firmware": self.firmware_page,
            "hardware": self.hardware_page,
        }

        root_layout.addWidget(sidebar)
        root_layout.addWidget(self.pages)

        self.setCentralWidget(root)

        self.switch_page("dashboard")

    def switch_page(self, key: str):
        for k, btn in self.nav_buttons.items():
            btn.setChecked(k == key)

        if key != "mirror" and self.screen_mirror and self.screen_mirror.is_running():
            self.stop_mirror()

        self.pages.setCurrentWidget(self.page_widgets[key])

        if key == "history":
            self.refresh_history_table()
        elif key == "apps":
            self.refresh_apps_list()
        elif key == "files":
            self.refresh_file_list()
        elif key == "security":
            self.refresh_security_check()
        elif key == "network":
            self.refresh_network_info()
        elif key == "firmware":
            self.refresh_firmware_info()
        elif key == "hardware":
            self.refresh_hardware_test_status()

    # ------------------------------------------------------------------
    # Dashboard Page
    # ------------------------------------------------------------------

    def create_dashboard_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(18)

        title = QLabel("Dashboard")
        title.setObjectName("contentTitle")

        desc = QLabel("Overview perangkat dan koneksi service tool.")
        desc.setObjectName("muted")

        layout.addWidget(title)
        layout.addWidget(desc)

        row = QHBoxLayout()
        row.setSpacing(16)

        card1 = QFrame()
        card1.setObjectName("card")
        c1_layout = QVBoxLayout(card1)
        c1_layout.setContentsMargins(22, 20, 22, 20)

        c1_title = QLabel("Connected Devices")
        c1_title.setObjectName("cardTitle")

        self.dashboard_device_count = QLabel("0")
        self.dashboard_device_count.setObjectName("scoreBig")
        self.dashboard_device_count.setStyleSheet("color:#ff5a1f;")

        c1_layout.addWidget(c1_title)
        c1_layout.addWidget(self.dashboard_device_count)

        card2 = QFrame()
        card2.setObjectName("card")
        c2_layout = QVBoxLayout(card2)
        c2_layout.setContentsMargins(22, 20, 22, 20)

        c2_title = QLabel("Active Device")
        c2_title.setObjectName("cardTitle")

        self.dashboard_status = QLabel("Checking...")
        self.dashboard_status.setObjectName("status")

        self.dashboard_info = QLabel("")
        self.dashboard_info.setObjectName("value")

        c2_layout.addWidget(c2_title)
        c2_layout.addWidget(self.dashboard_status)
        c2_layout.addWidget(self.dashboard_info)

        row.addWidget(card1, 1)
        row.addWidget(card2, 2)

        layout.addLayout(row)

        score_card = QFrame()
        score_card.setObjectName("card")
        score_layout = QVBoxLayout(score_card)
        score_layout.setContentsMargins(22, 20, 22, 20)
        score_layout.setSpacing(8)

        score_title = QLabel("Quick Health Check")
        score_title.setObjectName("cardTitle")

        self.dashboard_score_label = QLabel("Belum ada data diagnostics")
        self.dashboard_score_label.setObjectName("value")

        self.dashboard_score_bar = QProgressBar()
        self.dashboard_score_bar.setRange(0, 100)
        self.dashboard_score_bar.setValue(0)

        score_layout.addWidget(score_title)
        score_layout.addWidget(self.dashboard_score_label)
        score_layout.addWidget(self.dashboard_score_bar)

        layout.addWidget(score_card)
        layout.addStretch()

        return page

    # ------------------------------------------------------------------
    # Hardware Test Page
    # ------------------------------------------------------------------

    def create_hardware_test_page(self):
        page = QWidget()
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
        summary_layout.setContentsMargins(20, 16, 20, 16)
        self.hardware_score = QLabel("-- / 100")
        self.hardware_score.setObjectName("scoreBig")
        self.hardware_summary = QLabel("Run a full hardware test to collect a report.")
        self.hardware_summary.setObjectName("value")
        summary_layout.addWidget(self.hardware_score)
        summary_layout.addWidget(self.hardware_summary, 1)
        layout.addWidget(summary)

        actions = QHBoxLayout()
        self.hardware_run_button = QPushButton("RUN FULL HARDWARE TEST")
        self.hardware_run_button.setObjectName("actionPrimary")
        self.hardware_run_button.clicked.connect(self.run_full_hardware_test)
        self.hardware_refresh_button = QPushButton("Refresh")
        self.hardware_refresh_button.setObjectName("action")
        self.hardware_refresh_button.clicked.connect(self.refresh_hardware_test_status)
        actions.addWidget(self.hardware_run_button)
        actions.addWidget(self.hardware_refresh_button)
        actions.addStretch()
        layout.addLayout(actions)

        self.hardware_table = QTableWidget(0, 4)
        self.hardware_table.setHorizontalHeaderLabels(["Check", "Status", "Value", "Detail"])
        self.hardware_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.hardware_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.hardware_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.hardware_table, 1)

        warning = QLabel("Read-only diagnostics: camera, speaker, microphone, sensors, fingerprint and touchscreen still require physical interaction tests.")
        warning.setObjectName("muted")
        warning.setWordWrap(True)
        layout.addWidget(warning)
        return page

    def refresh_hardware_test_status(self):
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
                values = [item.name, item.status, item.value, item.detail]
                for col, value in enumerate(values):
                    self.hardware_table.setItem(row, col, QTableWidgetItem(str(value)))
            self.last_hardware_report = report
        except Exception as exc:
            QMessageBox.critical(self, "Hardware Test Error", str(exc))
        finally:
            self.hardware_run_button.setEnabled(True)

    # ------------------------------------------------------------------
    # Device Page
    # ------------------------------------------------------------------

    def create_device_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(18)

        title = QLabel("Device")
        title.setObjectName("contentTitle")

        desc = QLabel("Informasi perangkat Android yang sedang terhubung.")
        desc.setObjectName("muted")

        layout.addWidget(title)
        layout.addWidget(desc)

        card = QFrame()
        card.setObjectName("card")

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(22, 20, 22, 20)
        card_layout.setSpacing(9)

        self.device_status = QLabel("Checking...")
        self.device_status.setObjectName("status")

        self.device_info = QLabel("")
        self.device_info.setObjectName("value")

        card_layout.addWidget(self.device_status)
        card_layout.addWidget(self.device_info)

        layout.addWidget(card)

        actions = QFrame()
        actions.setObjectName("card")

        actions_layout = QVBoxLayout(actions)
        actions_layout.setContentsMargins(22, 20, 22, 20)
        actions_layout.setSpacing(10)

        actions_title = QLabel("Device Actions")
        actions_title.setObjectName("cardTitle")

        self.refresh_button = QPushButton("Refresh Device")
        self.refresh_button.setObjectName("action")

        self.reboot_button = QPushButton("Reboot System")
        self.reboot_button.setObjectName("action")
        self.reboot_button.setEnabled(False)

        self.recovery_button = QPushButton("Reboot Recovery")
        self.recovery_button.setObjectName("action")
        self.recovery_button.setEnabled(False)

        self.bootloader_button = QPushButton("Reboot Bootloader")
        self.bootloader_button.setObjectName("actionDanger")
        self.bootloader_button.setEnabled(False)

        actions_layout.addWidget(actions_title)
        actions_layout.addWidget(self.refresh_button)
        actions_layout.addWidget(self.reboot_button)
        actions_layout.addWidget(self.recovery_button)
        actions_layout.addWidget(self.bootloader_button)

        layout.addWidget(actions)
        layout.addStretch()

        self.refresh_button.clicked.connect(self.refresh_device_list)
        self.reboot_button.clicked.connect(lambda: self.confirm_reboot("system"))
        self.recovery_button.clicked.connect(lambda: self.confirm_reboot("recovery"))
        self.bootloader_button.clicked.connect(lambda: self.confirm_reboot("bootloader"))

        return page

    def confirm_reboot(self, mode: str):
        if not self.current_device:
            return

        mode_labels = {
            "system": "Reboot System (restart normal)",
            "recovery": "Reboot ke Recovery",
            "bootloader": "Reboot ke Bootloader",
        }

        reply = QMessageBox.question(
            self,
            "Konfirmasi Reboot",
            f"Yakin mau {mode_labels[mode]} untuk device ini?\n\n"
            f"Serial: {self.current_device.serial}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply != QMessageBox.Yes:
            return

        try:
            reboot_device(self.current_device.serial, mode=mode)
            QMessageBox.information(
                self, "Reboot Terkirim",
                "Perintah reboot berhasil dikirim ke device."
            )
        except ADBError as exc:
            QMessageBox.critical(self, "Reboot Gagal", str(exc))

    # ------------------------------------------------------------------
    # Diagnostics Page (Smart)
    # ------------------------------------------------------------------

    def create_diagnostics_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(18)

        title = QLabel("Smart Diagnostics")
        title.setObjectName("contentTitle")

        desc = QLabel(
            "Status baterai, storage, layar, plus skor kesehatan otomatis."
        )
        desc.setObjectName("muted")

        layout.addWidget(title)
        layout.addWidget(desc)

        row = QHBoxLayout()
        row.setSpacing(16)

        info_card = QFrame()
        info_card.setObjectName("card")
        info_layout = QVBoxLayout(info_card)
        info_layout.setContentsMargins(22, 20, 22, 20)
        info_layout.setSpacing(9)

        self.diag_status = QLabel("Checking...")
        self.diag_status.setObjectName("status")

        self.diag_info = QLabel("")
        self.diag_info.setObjectName("value")

        info_layout.addWidget(self.diag_status)
        info_layout.addWidget(self.diag_info)

        score_card = QFrame()
        score_card.setObjectName("card")
        score_layout = QVBoxLayout(score_card)
        score_layout.setContentsMargins(22, 20, 22, 20)
        score_layout.setSpacing(8)

        score_title = QLabel("Health Score")
        score_title.setObjectName("cardTitle")

        self.diag_score_value = QLabel("--")
        self.diag_score_value.setObjectName("scoreBig")

        self.diag_score_bar = QProgressBar()
        self.diag_score_bar.setRange(0, 100)
        self.diag_score_bar.setValue(0)

        self.diag_recommendations = QTextEdit()
        self.diag_recommendations.setObjectName("value")
        self.diag_recommendations.setReadOnly(True)
        self.diag_recommendations.setFixedHeight(140)

        score_layout.addWidget(score_title)
        score_layout.addWidget(self.diag_score_value)
        score_layout.addWidget(self.diag_score_bar)
        score_layout.addWidget(QLabel("Rekomendasi:"))
        score_layout.addWidget(self.diag_recommendations)

        row.addWidget(info_card, 1)
        row.addWidget(score_card, 1)

        layout.addLayout(row)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.diag_refresh_button = QPushButton("Refresh Diagnostics")
        self.diag_refresh_button.setObjectName("action")
        self.diag_refresh_button.clicked.connect(self.refresh_diagnostics)

        self.diag_save_button = QPushButton("Simpan ke Riwayat")
        self.diag_save_button.setObjectName("action")
        self.diag_save_button.clicked.connect(self.save_diagnostics_to_history)

        self.diag_export_button = QPushButton("Export PDF")
        self.diag_export_button.setObjectName("actionPrimary")
        self.diag_export_button.clicked.connect(self.export_pdf_report)

        btn_row.addWidget(self.diag_refresh_button)
        btn_row.addWidget(self.diag_save_button)
        btn_row.addWidget(self.diag_export_button)

        layout.addLayout(btn_row)
        layout.addStretch()

        return page

    def refresh_diagnostics(self):
        if not self.current_device:
            self.diag_status.setText("? No device connected")
            self.diag_info.setText("Hubungkan device via USB terlebih dahulu.")
            self.diag_score_value.setText("--")
            self.diag_score_bar.setValue(0)
            self.diag_recommendations.setPlainText("")
            return

        try:
            diag = get_diagnostics(self.current_device.serial)
            score, recommendations = compute_health_score(diag)

            self.last_diag = diag
            self.last_score = score
            self.last_recommendations = recommendations

            self.diag_status.setText("? Diagnostics OK")
            self.diag_info.setText(
                f"Battery Level    : {diag.battery_level}\n"
                f"Battery Status   : {diag.battery_status}\n"
                f"Battery Health   : {diag.battery_health}\n"
                f"Storage          : {diag.storage}\n"
                f"Screen State     : {diag.screen_state}\n"
                f"USB Debugging    : {diag.usb_debugging}"
            )

            self.diag_score_value.setText(
                f"{score}  ({health_score_label(score)})"
            )
            self.diag_score_bar.setValue(score)
            self.diag_score_bar.setStyleSheet(
                self._score_bar_style(score)
            )

            self.diag_recommendations.setPlainText(
                "\n".join(f"- {r}" for r in recommendations)
            )

            self.dashboard_score_label.setText(
                f"{score}/100 - {health_score_label(score)}"
            )
            self.dashboard_score_bar.setValue(score)
            self.dashboard_score_bar.setStyleSheet(self._score_bar_style(score))

        except ADBError as exc:
            self.diag_status.setText("? Diagnostics error")
            self.diag_info.setText(str(exc))
            self.diag_score_value.setText("--")
            self.diag_score_bar.setValue(0)
            self.diag_recommendations.setPlainText("")

    @staticmethod
    def _score_bar_style(score: int) -> str:
        if score >= 85:
            color = "#2e7d32"
        elif score >= 70:
            color = "#7cb342"
        elif score >= 50:
            color = "#f9a825"
        elif score >= 30:
            color = "#ef6c00"
        else:
            color = "#c62828"

        return f"QProgressBar::chunk {{ background: {color}; border-radius: 6px; }}"

    def save_diagnostics_to_history(self):
        if not self.current_device or not self.last_diag:
            QMessageBox.warning(
                self, "Belum ada data",
                "Jalankan Refresh Diagnostics dulu sebelum menyimpan."
            )
            return

        try:
            save_service_record(
                serial=self.current_device.serial,
                manufacturer=self.current_device.manufacturer,
                model=self.current_device.model,
                android_version=self.current_device.android_version,
                diag=self.last_diag,
                health_score=self.last_score or 0,
                recommendations=self.last_recommendations,
            )
            QMessageBox.information(
                self, "Tersimpan", "Hasil diagnostics berhasil disimpan ke riwayat."
            )
        except Exception as exc:
            QMessageBox.critical(self, "Gagal Menyimpan", str(exc))

    def export_pdf_report(self):
        if not self.current_device or not self.last_diag:
            QMessageBox.warning(
                self, "Belum ada data",
                "Jalankan Refresh Diagnostics dulu sebelum export PDF."
            )
            return

        default_name = f"service_report_{self.current_device.serial}.pdf"

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Simpan Laporan PDF", default_name, "PDF Files (*.pdf)"
        )

        if not file_path:
            return

        try:
            generate_service_report(
                output_path=Path(file_path),
                device=self.current_device,
                diag=self.last_diag,
                health_score=self.last_score or 0,
                recommendations=self.last_recommendations,
            )
            QMessageBox.information(
                self, "Export Berhasil", f"Laporan tersimpan di:\n{file_path}"
            )
        except Exception as exc:
            QMessageBox.critical(self, "Export Gagal", str(exc))

    # ------------------------------------------------------------------
    # Live Logs Page
    # ------------------------------------------------------------------

    def create_logs_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(14)

        title = QLabel("Live Logs")
        title.setObjectName("contentTitle")

        desc = QLabel("Streaming logcat real-time dari device yang aktif.")
        desc.setObjectName("muted")

        layout.addWidget(title)
        layout.addWidget(desc)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.log_start_button = QPushButton("Start Logcat")
        self.log_start_button.setObjectName("actionPrimary")
        self.log_start_button.clicked.connect(self.start_logcat)

        self.log_stop_button = QPushButton("Stop")
        self.log_stop_button.setObjectName("actionDanger")
        self.log_stop_button.clicked.connect(self.stop_logcat)
        self.log_stop_button.setEnabled(False)

        self.log_clear_button = QPushButton("Clear")
        self.log_clear_button.setObjectName("action")
        self.log_clear_button.clicked.connect(lambda: self.log_console.clear())

        btn_row.addWidget(self.log_start_button)
        btn_row.addWidget(self.log_stop_button)
        btn_row.addWidget(self.log_clear_button)
        btn_row.addStretch()

        layout.addLayout(btn_row)

        self.log_console = QPlainTextEdit()
        self.log_console.setObjectName("logConsole")
        self.log_console.setReadOnly(True)
        self.log_console.setMaximumBlockCount(2000)

        layout.addWidget(self.log_console)

        return page

    def start_logcat(self):
        if not self.current_device:
            QMessageBox.warning(
                self, "Tidak ada device", "Hubungkan device terlebih dahulu."
            )
            return

        if self.logcat_streamer and self.logcat_streamer.is_running():
            return

        self.log_console.appendPlainText(
            f"--- Starting logcat for {self.current_device.serial} ---"
        )

        self.logcat_streamer = LogcatStreamer(self.current_device.serial, self)
        self.logcat_streamer.line_received.connect(self.log_console.appendPlainText)
        self.logcat_streamer.error_occurred.connect(
            lambda msg: self.log_console.appendPlainText(f"[stderr] {msg}")
        )
        self.logcat_streamer.stopped.connect(self._on_logcat_stopped)
        self.logcat_streamer.start()

        self.log_start_button.setEnabled(False)
        self.log_stop_button.setEnabled(True)

    def stop_logcat(self):
        if self.logcat_streamer:
            self.logcat_streamer.stop()

    def _on_logcat_stopped(self):
        self.log_console.appendPlainText("--- Logcat stopped ---")
        self.log_start_button.setEnabled(True)
        self.log_stop_button.setEnabled(False)

    # ------------------------------------------------------------------
    # Service History Page
    # ------------------------------------------------------------------

    def create_history_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(14)

        title = QLabel("Service History")
        title.setObjectName("contentTitle")

        desc = QLabel("Riwayat diagnostics yang pernah disimpan per device.")
        desc.setObjectName("muted")

        layout.addWidget(title)
        layout.addWidget(desc)

        btn_row = QHBoxLayout()

        self.history_refresh_button = QPushButton("Refresh Riwayat")
        self.history_refresh_button.setObjectName("action")
        self.history_refresh_button.clicked.connect(self.refresh_history_table)

        btn_row.addWidget(self.history_refresh_button)
        btn_row.addStretch()

        layout.addLayout(btn_row)

        self.history_table = QTableWidget(0, 7)
        self.history_table.setHorizontalHeaderLabels(
            [
                "Tanggal",
                "Serial",
                "Model",
                "Battery",
                "Health",
                "Score",
                "Rekomendasi",
            ]
        )
        self.history_table.horizontalHeader().setStretchLastSection(True)
        self.history_table.setEditTriggers(QTableWidget.NoEditTriggers)

        layout.addWidget(self.history_table)

        return page

    def refresh_history_table(self):
        records = get_history(limit=200)

        self.history_table.setRowCount(len(records))

        for row_idx, rec in enumerate(records):
            values = [
                rec.created_at,
                rec.serial,
                rec.model or "-",
                f"{rec.battery_level} ({rec.battery_status})",
                rec.battery_health,
                f"{rec.health_score}",
                rec.recommendations,
            ]

            for col_idx, val in enumerate(values):
                item = QTableWidgetItem(val)
                self.history_table.setItem(row_idx, col_idx, item)

    # ------------------------------------------------------------------
    # Security Check Page
    # ------------------------------------------------------------------

    def create_security_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(14)

        title = QLabel("Security Check")
        title.setObjectName("contentTitle")

        desc = QLabel("Auto-detect root, status bootloader, dan patch keamanan.")
        desc.setObjectName("muted")

        layout.addWidget(title)
        layout.addWidget(desc)

        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(22, 20, 22, 20)
        card_layout.setSpacing(9)

        self.security_status = QLabel("Checking...")
        self.security_status.setObjectName("status")

        self.security_info = QLabel("")
        self.security_info.setObjectName("value")

        card_layout.addWidget(self.security_status)
        card_layout.addWidget(self.security_info)

        layout.addWidget(card)

        warn_card = QFrame()
        warn_card.setObjectName("card")
        warn_layout = QVBoxLayout(warn_card)
        warn_layout.setContentsMargins(22, 20, 22, 20)
        warn_layout.setSpacing(8)

        warn_title = QLabel("Peringatan & Rekomendasi")
        warn_title.setObjectName("cardTitle")

        self.security_warnings = QTextEdit()
        self.security_warnings.setObjectName("value")
        self.security_warnings.setReadOnly(True)
        self.security_warnings.setFixedHeight(150)

        warn_layout.addWidget(warn_title)
        warn_layout.addWidget(self.security_warnings)

        layout.addWidget(warn_card)

        self.security_refresh_button = QPushButton("Jalankan Security Check")
        self.security_refresh_button.setObjectName("actionPrimary")
        self.security_refresh_button.clicked.connect(self.refresh_security_check)

        layout.addWidget(self.security_refresh_button)
        layout.addStretch()

        return page

    def refresh_security_check(self):
        if not self.current_device:
            self.security_status.setText("? No device connected")
            self.security_info.setText("Hubungkan device terlebih dahulu.")
            self.security_warnings.setPlainText("")
            return

        try:
            result = run_security_check(self.current_device.serial)

            root_icon = "??" if result.is_rooted else "?"

            self.security_status.setText(
                f"{root_icon} {'Rooted' if result.is_rooted else 'Not Rooted'}"
            )
            self.security_info.setText(
                f"Root Indicator     : {result.root_indicator}\n"
                f"Bootloader         : {result.bootloader_state}\n"
                f"Verified Boot      : {result.verified_boot_state}\n"
                f"Security Patch     : {result.security_patch}\n"
                f"SELinux            : {result.selinux_status}"
            )

            self.security_warnings.setPlainText(
                "\n".join(f"- {w}" for w in result.warnings)
            )
        except ADBError as exc:
            self.security_status.setText("? Security check gagal")
            self.security_info.setText(str(exc))
            self.security_warnings.setPlainText("")

    # ------------------------------------------------------------------
    # App Manager Page
    # ------------------------------------------------------------------

    def create_apps_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(14)

        title = QLabel("App Manager")
        title.setObjectName("contentTitle")

        desc = QLabel("Kelola aplikasi terinstall di device: install, uninstall, force-stop.")
        desc.setObjectName("muted")

        layout.addWidget(title)
        layout.addWidget(desc)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.apps_refresh_button = QPushButton("Refresh Daftar Apps")
        self.apps_refresh_button.setObjectName("action")
        self.apps_refresh_button.clicked.connect(self.refresh_apps_list)

        self.apps_install_button = QPushButton("Install APK...")
        self.apps_install_button.setObjectName("actionPrimary")
        self.apps_install_button.clicked.connect(self.install_apk_dialog)

        btn_row.addWidget(self.apps_refresh_button)
        btn_row.addWidget(self.apps_install_button)
        btn_row.addStretch()

        layout.addLayout(btn_row)

        self.apps_list = QListWidget()
        layout.addWidget(self.apps_list)

        action_row = QHBoxLayout()
        action_row.setSpacing(10)

        self.apps_stop_button = QPushButton("Force Stop")
        self.apps_stop_button.setObjectName("action")
        self.apps_stop_button.clicked.connect(self.force_stop_selected_app)

        self.apps_clear_button = QPushButton("Clear Data")
        self.apps_clear_button.setObjectName("action")
        self.apps_clear_button.clicked.connect(self.clear_data_selected_app)

        self.apps_uninstall_button = QPushButton("Uninstall")
        self.apps_uninstall_button.setObjectName("actionDanger")
        self.apps_uninstall_button.clicked.connect(self.uninstall_selected_app)

        action_row.addWidget(self.apps_stop_button)
        action_row.addWidget(self.apps_clear_button)
        action_row.addWidget(self.apps_uninstall_button)

        layout.addLayout(action_row)

        return page

    def refresh_apps_list(self):
        self.apps_list.clear()

        if not self.current_device:
            self.apps_list.addItem("Tidak ada device terhubung")
            return

        try:
            packages = list_packages(self.current_device.serial, include_system=False)

            if not packages:
                self.apps_list.addItem("Tidak ada aplikasi pihak ketiga terdeteksi.")
                return

            for pkg in packages:
                self.apps_list.addItem(pkg.package_name)
        except ADBError as exc:
            self.apps_list.addItem(f"Error: {exc}")

    def _get_selected_package(self) -> str | None:
        item = self.apps_list.currentItem()

        if not item or not self.current_device:
            return None

        text = item.text()

        if text.startswith("Error") or "Tidak ada" in text:
            return None

        return text

    def force_stop_selected_app(self):
        package = self._get_selected_package()

        if not package:
            QMessageBox.warning(self, "Pilih aplikasi", "Pilih aplikasi dari daftar dulu.")
            return

        try:
            force_stop(self.current_device.serial, package)
            QMessageBox.information(self, "Berhasil", f"{package} dihentikan paksa.")
        except ADBError as exc:
            QMessageBox.critical(self, "Gagal", str(exc))

    def clear_data_selected_app(self):
        package = self._get_selected_package()

        if not package:
            QMessageBox.warning(self, "Pilih aplikasi", "Pilih aplikasi dari daftar dulu.")
            return

        reply = QMessageBox.question(
            self, "Konfirmasi",
            f"Yakin hapus semua data aplikasi {package}?\nTindakan ini tidak bisa dibatalkan.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )

        if reply != QMessageBox.Yes:
            return

        try:
            clear_app_data(self.current_device.serial, package)
            QMessageBox.information(self, "Berhasil", f"Data {package} berhasil dihapus.")
        except ADBError as exc:
            QMessageBox.critical(self, "Gagal", str(exc))

    def uninstall_selected_app(self):
        package = self._get_selected_package()

        if not package:
            QMessageBox.warning(self, "Pilih aplikasi", "Pilih aplikasi dari daftar dulu.")
            return

        reply = QMessageBox.question(
            self, "Konfirmasi Uninstall",
            f"Yakin uninstall {package} dari device ini?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )

        if reply != QMessageBox.Yes:
            return

        try:
            uninstall_package(self.current_device.serial, package)
            QMessageBox.information(self, "Berhasil", f"{package} berhasil di-uninstall.")
            self.refresh_apps_list()
        except ADBError as exc:
            QMessageBox.critical(self, "Gagal", str(exc))

    def install_apk_dialog(self):
        if not self.current_device:
            QMessageBox.warning(self, "Tidak ada device", "Hubungkan device terlebih dahulu.")
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self, "Pilih file APK", "", "APK Files (*.apk)"
        )

        if not file_path:
            return

        try:
            install_apk(self.current_device.serial, file_path)
            QMessageBox.information(self, "Berhasil", "APK berhasil di-install.")
            self.refresh_apps_list()
        except ADBError as exc:
            QMessageBox.critical(self, "Install Gagal", str(exc))

    # ------------------------------------------------------------------
    # File Explorer Page
    # ------------------------------------------------------------------

    def create_files_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(14)

        title = QLabel("File Explorer")
        title.setObjectName("contentTitle")

        desc = QLabel("Browse penyimpanan device, push/pull file via ADB.")
        desc.setObjectName("muted")

        layout.addWidget(title)
        layout.addWidget(desc)

        path_row = QHBoxLayout()
        path_row.setSpacing(8)

        self.files_path_input = QLineEdit(self.file_explorer_path)
        self.files_path_input.returnPressed.connect(self.navigate_to_path_input)

        self.files_up_button = QPushButton("Up")
        self.files_up_button.setObjectName("action")
        self.files_up_button.clicked.connect(self.navigate_up)

        self.files_go_button = QPushButton("Go")
        self.files_go_button.setObjectName("action")
        self.files_go_button.clicked.connect(self.navigate_to_path_input)

        path_row.addWidget(self.files_path_input)
        path_row.addWidget(self.files_up_button)
        path_row.addWidget(self.files_go_button)

        layout.addLayout(path_row)

        self.files_list = QListWidget()
        self.files_list.itemDoubleClicked.connect(self.on_file_double_clicked)
        layout.addWidget(self.files_list)

        action_row = QHBoxLayout()
        action_row.setSpacing(10)

        self.files_pull_button = QPushButton("Pull ke Laptop")
        self.files_pull_button.setObjectName("action")
        self.files_pull_button.clicked.connect(self.pull_selected_file)

        self.files_push_button = QPushButton("Push dari Laptop")
        self.files_push_button.setObjectName("action")
        self.files_push_button.clicked.connect(self.push_file_dialog)

        self.files_delete_button = QPushButton("Hapus")
        self.files_delete_button.setObjectName("actionDanger")
        self.files_delete_button.clicked.connect(self.delete_selected_file)

        action_row.addWidget(self.files_pull_button)
        action_row.addWidget(self.files_push_button)
        action_row.addWidget(self.files_delete_button)

        layout.addLayout(action_row)

        return page

    def refresh_file_list(self):
        self.files_list.clear()
        self.files_path_input.setText(self.file_explorer_path)

        if not self.current_device:
            self.files_list.addItem("Tidak ada device terhubung")
            return

        try:
            entries = list_dir(self.current_device.serial, self.file_explorer_path)

            if not entries:
                self.files_list.addItem("(folder kosong)")
                return

            for entry in entries:
                prefix = "[DIR] " if entry.is_dir else "      "
                label = f"{prefix}{entry.name}" + (f"  ({entry.size})" if not entry.is_dir else "")
                item = QListWidgetItem(label)
                item.setData(Qt.UserRole, entry.name)
                item.setData(Qt.UserRole + 1, entry.is_dir)
                self.files_list.addItem(item)
        except ADBError as exc:
            self.files_list.addItem(f"Error: {exc}")

    def navigate_to_path_input(self):
        self.file_explorer_path = normalize_path(self.files_path_input.text())
        self.refresh_file_list()

    def navigate_up(self):
        self.file_explorer_path = go_up(self.file_explorer_path)
        self.refresh_file_list()

    def on_file_double_clicked(self, item: QListWidgetItem):
        is_dir = item.data(Qt.UserRole + 1)
        name = item.data(Qt.UserRole)

        if not name:
            return

        if is_dir:
            self.file_explorer_path = normalize_path(
                f"{self.file_explorer_path}/{name}"
            )
            self.refresh_file_list()

    def _get_selected_file_entry(self):
        item = self.files_list.currentItem()

        if not item:
            return None, None

        name = item.data(Qt.UserRole)
        is_dir = item.data(Qt.UserRole + 1)

        return name, is_dir

    def pull_selected_file(self):
        if not self.current_device:
            return

        name, is_dir = self._get_selected_file_entry()

        if not name:
            QMessageBox.warning(self, "Pilih file", "Pilih file/folder dari daftar dulu.")
            return

        remote_path = f"{self.file_explorer_path}/{name}"

        save_path, _ = QFileDialog.getSaveFileName(self, "Simpan sebagai", name)

        if not save_path:
            return

        try:
            pull_file(self.current_device.serial, remote_path, save_path)
            QMessageBox.information(self, "Berhasil", f"File tersimpan di:\n{save_path}")
        except ADBError as exc:
            QMessageBox.critical(self, "Pull Gagal", str(exc))

    def push_file_dialog(self):
        if not self.current_device:
            QMessageBox.warning(self, "Tidak ada device", "Hubungkan device terlebih dahulu.")
            return

        file_path, _ = QFileDialog.getOpenFileName(self, "Pilih file untuk di-push")

        if not file_path:
            return

        file_name = Path(file_path).name
        remote_path = f"{self.file_explorer_path}/{file_name}"

        try:
            push_file(self.current_device.serial, file_path, remote_path)
            QMessageBox.information(self, "Berhasil", f"File terkirim ke:\n{remote_path}")
            self.refresh_file_list()
        except ADBError as exc:
            QMessageBox.critical(self, "Push Gagal", str(exc))

    def delete_selected_file(self):
        if not self.current_device:
            return

        name, is_dir = self._get_selected_file_entry()

        if not name:
            QMessageBox.warning(self, "Pilih file", "Pilih file/folder dari daftar dulu.")
            return

        remote_path = f"{self.file_explorer_path}/{name}"

        reply = QMessageBox.question(
            self, "Konfirmasi Hapus",
            f"Yakin hapus {remote_path}?\nTindakan ini tidak bisa dibatalkan.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )

        if reply != QMessageBox.Yes:
            return

        try:
            delete_remote(self.current_device.serial, remote_path)
            QMessageBox.information(self, "Berhasil", "File/folder berhasil dihapus.")
            self.refresh_file_list()
        except ADBError as exc:
            QMessageBox.critical(self, "Gagal", str(exc))

    # ------------------------------------------------------------------
    # Screen Mirror Page
    # ------------------------------------------------------------------

    def create_mirror_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(14)

        title = QLabel("Screen Mirror")
        title.setObjectName("contentTitle")

        desc = QLabel(
            "Preview layar device (refresh berkala) - klik gambar untuk tap, "
            "berbasis ADB tanpa dependency tambahan."
        )
        desc.setObjectName("muted")
        desc.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(desc)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.mirror_start_button = QPushButton("Start Mirror")
        self.mirror_start_button.setObjectName("actionPrimary")
        self.mirror_start_button.clicked.connect(self.start_mirror)

        self.mirror_stop_button = QPushButton("Stop")
        self.mirror_stop_button.setObjectName("actionDanger")
        self.mirror_stop_button.clicked.connect(self.stop_mirror)
        self.mirror_stop_button.setEnabled(False)

        self.mirror_home_button = QPushButton("Home")
        self.mirror_home_button.setObjectName("action")
        self.mirror_home_button.clicked.connect(lambda: self._send_key_safe("KEYCODE_HOME"))

        self.mirror_back_button = QPushButton("Back")
        self.mirror_back_button.setObjectName("action")
        self.mirror_back_button.clicked.connect(lambda: self._send_key_safe("KEYCODE_BACK"))

        btn_row.addWidget(self.mirror_start_button)
        btn_row.addWidget(self.mirror_stop_button)
        btn_row.addWidget(self.mirror_home_button)
        btn_row.addWidget(self.mirror_back_button)
        btn_row.addStretch()

        layout.addLayout(btn_row)

        self.mirror_view = QLabel("Klik Start Mirror untuk mulai preview layar device.")
        self.mirror_view.setObjectName("value")
        self.mirror_view.setAlignment(Qt.AlignCenter)
        self.mirror_view.setMinimumHeight(400)
        self.mirror_view.setStyleSheet(
            "background:#0a0b0e; border:1px solid #22262f; border-radius:10px;"
        )
        self.mirror_view.mousePressEvent = self._on_mirror_clicked

        layout.addWidget(self.mirror_view)

        return page

    def start_mirror(self):
        if not self.current_device:
            QMessageBox.warning(self, "Tidak ada device", "Hubungkan device terlebih dahulu.")
            return

        if self.screen_mirror and self.screen_mirror.is_running():
            return

        self.screen_mirror = ScreenMirror(self.current_device.serial, str(ADB_PATH), self)
        self.screen_mirror.frame_ready.connect(self._on_mirror_frame)
        self.screen_mirror.error_occurred.connect(
            lambda msg: self.mirror_view.setText(f"Error: {msg}")
        )
        self.screen_mirror.start(interval_ms=900)

        self.mirror_start_button.setEnabled(False)
        self.mirror_stop_button.setEnabled(True)

    def stop_mirror(self):
        if self.screen_mirror:
            self.screen_mirror.stop()

        self.mirror_start_button.setEnabled(True)
        self.mirror_stop_button.setEnabled(False)
        self.mirror_view.setText("Mirror dihentikan.")

    def _on_mirror_frame(self, data: bytes):
        pixmap = QPixmap()

        if pixmap.loadFromData(data, "PNG"):
            scaled = pixmap.scaledToHeight(560, Qt.SmoothTransformation)
            self.mirror_view.setPixmap(scaled)
            self._mirror_pixmap_size = scaled.size()
            self._mirror_original_size = pixmap.size()

    def _on_mirror_clicked(self, event):
        if not self.current_device or not self.screen_mirror or not self.screen_mirror.is_running():
            return

        pixmap = self.mirror_view.pixmap()

        if not pixmap or pixmap.isNull():
            return

        label_size = self.mirror_view.size()
        pix_size = pixmap.size()

        offset_x = (label_size.width() - pix_size.width()) / 2
        offset_y = (label_size.height() - pix_size.height()) / 2

        click_x = event.position().x() - offset_x
        click_y = event.position().y() - offset_y

        if click_x < 0 or click_y < 0 or click_x > pix_size.width() or click_y > pix_size.height():
            return

        scale_x = self._mirror_original_size.width() / pix_size.width()
        scale_y = self._mirror_original_size.height() / pix_size.height()

        real_x = int(click_x * scale_x)
        real_y = int(click_y * scale_y)

        try:
            send_tap(run_adb, self.current_device.serial, real_x, real_y)
        except ADBError:
            pass

    def _send_key_safe(self, keycode: str):
        if not self.current_device:
            return

        try:
            send_key(run_adb, self.current_device.serial, keycode)
        except ADBError as exc:
            QMessageBox.critical(self, "Gagal", str(exc))

    # ------------------------------------------------------------------
    # Backup & Restore Page
    # ------------------------------------------------------------------

    def create_backup_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(14)

        title = QLabel("Backup & Restore")
        title.setObjectName("contentTitle")

        desc = QLabel(
            "Backup folder penting (DCIM, Download, Pictures, WhatsApp) ke file ZIP, "
            "dan restore kembali ke device."
        )
        desc.setObjectName("muted")
        desc.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(desc)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.backup_button = QPushButton("Backup Sekarang")
        self.backup_button.setObjectName("actionPrimary")
        self.backup_button.clicked.connect(self.run_backup)

        self.restore_button = QPushButton("Restore dari ZIP...")
        self.restore_button.setObjectName("action")
        self.restore_button.clicked.connect(self.run_restore)

        btn_row.addWidget(self.backup_button)
        btn_row.addWidget(self.restore_button)
        btn_row.addStretch()

        layout.addLayout(btn_row)

        self.backup_log = QPlainTextEdit()
        self.backup_log.setObjectName("logConsole")
        self.backup_log.setReadOnly(True)

        layout.addWidget(self.backup_log)

        return page

    def run_backup(self):
        if not self.current_device:
            QMessageBox.warning(self, "Tidak ada device", "Hubungkan device terlebih dahulu.")
            return

        output_dir = QFileDialog.getExistingDirectory(self, "Pilih folder tujuan backup")

        if not output_dir:
            return

        self.backup_log.appendPlainText(
            f"Memulai backup device {self.current_device.serial} - mohon tunggu..."
        )
        QApplication.processEvents()

        try:
            zip_path = backup_device(self.current_device.serial, Path(output_dir))
            self.backup_log.appendPlainText(f"Backup selesai: {zip_path}")
            QMessageBox.information(self, "Backup Selesai", f"File tersimpan di:\n{zip_path}")
        except Exception as exc:
            self.backup_log.appendPlainText(f"Backup gagal: {exc}")
            QMessageBox.critical(self, "Backup Gagal", str(exc))

    def run_restore(self):
        if not self.current_device:
            QMessageBox.warning(self, "Tidak ada device", "Hubungkan device terlebih dahulu.")
            return

        zip_path, _ = QFileDialog.getOpenFileName(
            self, "Pilih file backup ZIP", "", "ZIP Files (*.zip)"
        )

        if not zip_path:
            return

        reply = QMessageBox.question(
            self, "Konfirmasi Restore",
            "Restore akan menimpa file dengan nama sama di device.\nLanjutkan?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )

        if reply != QMessageBox.Yes:
            return

        self.backup_log.appendPlainText(f"Memulai restore dari {zip_path} - mohon tunggu...")
        QApplication.processEvents()

        try:
            results = restore_device(self.current_device.serial, Path(zip_path))

            for line in results:
                self.backup_log.appendPlainText(line)

            QMessageBox.information(self, "Restore Selesai", "Proses restore selesai.")
        except Exception as exc:
            self.backup_log.appendPlainText(f"Restore gagal: {exc}")
            QMessageBox.critical(self, "Restore Gagal", str(exc))

    # ------------------------------------------------------------------
    # Network & IMEI Page
    # ------------------------------------------------------------------

    def create_network_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(14)

        title = QLabel("Network & IMEI")
        title.setObjectName("contentTitle")

        desc = QLabel("Informasi IMEI, status WiFi/data seluler, IP, dan operator.")
        desc.setObjectName("muted")

        layout.addWidget(title)
        layout.addWidget(desc)

        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(22, 20, 22, 20)
        card_layout.setSpacing(9)

        self.network_status = QLabel("Checking...")
        self.network_status.setObjectName("status")

        self.network_info_label = QLabel("")
        self.network_info_label.setObjectName("value")
        self.network_info_label.setWordWrap(True)

        card_layout.addWidget(self.network_status)
        card_layout.addWidget(self.network_info_label)

        layout.addWidget(card)

        self.network_refresh_button = QPushButton("Refresh Network Info")
        self.network_refresh_button.setObjectName("actionPrimary")
        self.network_refresh_button.clicked.connect(self.refresh_network_info)

        layout.addWidget(self.network_refresh_button)
        layout.addStretch()

        return page

    def refresh_network_info(self):
        if not self.current_device:
            self.network_status.setText("? No device connected")
            self.network_info_label.setText("Hubungkan device terlebih dahulu.")
            return

        try:
            info = get_network_info(self.current_device.serial)

            self.network_status.setText("? Network Info OK")
            self.network_info_label.setText(
                f"IMEI              : {info.imei}\n"
                f"WiFi              : {info.wifi_state}\n"
                f"Mobile Data       : {info.mobile_data_state}\n"
                f"IP Address        : {info.ip_address}\n"
                f"Network Operator  : {info.network_operator}\n"
                f"SIM State         : {info.sim_state}\n"
                f"Phone Type        : {info.phone_type}"
            )
        except ADBError as exc:
            self.network_status.setText("? Gagal membaca network info")
            self.network_info_label.setText(str(exc))

    # ------------------------------------------------------------------
    # Firmware & Flash Page
    # ------------------------------------------------------------------

    def create_firmware_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(14)

        title = QLabel("Firmware & Flash")
        title.setObjectName("contentTitle")

        desc = QLabel(
            "Info build firmware saat ini, dan flash partition via Fastboot. "
            "Fitur flashing hanya aktif saat device dalam mode Bootloader."
        )
        desc.setObjectName("muted")
        desc.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(desc)

        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(22, 20, 22, 20)
        card_layout.setSpacing(9)

        self.firmware_status = QLabel("Checking...")
        self.firmware_status.setObjectName("status")

        self.firmware_info_label = QLabel("")
        self.firmware_info_label.setObjectName("value")

        card_layout.addWidget(self.firmware_status)
        card_layout.addWidget(self.firmware_info_label)

        layout.addWidget(card)

        self.firmware_refresh_button = QPushButton("Refresh Build Info")
        self.firmware_refresh_button.setObjectName("action")
        self.firmware_refresh_button.clicked.connect(self.refresh_firmware_info)
        layout.addWidget(self.firmware_refresh_button)

        # --- Fastboot Flash Section ---
        flash_card = QFrame()
        flash_card.setObjectName("card")
        flash_layout = QVBoxLayout(flash_card)
        flash_layout.setContentsMargins(22, 20, 22, 20)
        flash_layout.setSpacing(10)

        flash_title = QLabel("Flash Partition (Fastboot Mode)")
        flash_title.setObjectName("cardTitle")

        flash_warning = QLabel(
            "PERINGATAN: Flash partition yang salah dapat menyebabkan device "
            "bootloop atau mati total (bricked). Pastikan file image sesuai "
            "dengan model device dan partition target."
        )
        flash_warning.setObjectName("value")
        flash_warning.setWordWrap(True)
        flash_warning.setStyleSheet("color:#ff6b6b;")

        flash_layout.addWidget(flash_title)
        flash_layout.addWidget(flash_warning)

        self.firmware_reboot_bootloader_button = QPushButton(
            "Reboot ke Bootloader"
        )
        self.firmware_reboot_bootloader_button.setObjectName("action")
        self.firmware_reboot_bootloader_button.clicked.connect(
            lambda: self.confirm_reboot("bootloader")
        )
        flash_layout.addWidget(self.firmware_reboot_bootloader_button)

        partition_row = QHBoxLayout()
        partition_row.setSpacing(8)

        self.firmware_partition_combo = QComboBox()
        self.firmware_partition_combo.addItems(COMMON_PARTITIONS)
        self.firmware_partition_combo.setObjectName("deviceSelector")

        self.firmware_select_image_button = QPushButton("Pilih File Image...")
        self.firmware_select_image_button.setObjectName("action")
        self.firmware_select_image_button.clicked.connect(self.select_firmware_image)

        partition_row.addWidget(self.firmware_partition_combo)
        partition_row.addWidget(self.firmware_select_image_button)

        flash_layout.addLayout(partition_row)

        self.firmware_image_path_label = QLabel("Belum ada file dipilih.")
        self.firmware_image_path_label.setObjectName("value")
        self.firmware_image_path_label.setWordWrap(True)
        flash_layout.addWidget(self.firmware_image_path_label)

        self.firmware_flash_button = QPushButton("Flash Partition Sekarang")
        self.firmware_flash_button.setObjectName("actionDanger")
        self.firmware_flash_button.clicked.connect(self.run_flash_partition)
        flash_layout.addWidget(self.firmware_flash_button)

        self.firmware_flash_log = QPlainTextEdit()
        self.firmware_flash_log.setObjectName("logConsole")
        self.firmware_flash_log.setReadOnly(True)
        self.firmware_flash_log.setFixedHeight(140)
        flash_layout.addWidget(self.firmware_flash_log)

        layout.addWidget(flash_card)
        layout.addStretch()

        self._firmware_image_path = None

        return page

    def refresh_firmware_info(self):
        if not self.current_device:
            self.firmware_status.setText("? No device connected")
            self.firmware_info_label.setText(
                "Hubungkan device (mode normal) untuk melihat info build."
            )
            return

        try:
            info = get_build_info(self.current_device.serial)

            self.firmware_status.setText("? Build Info OK")
            self.firmware_info_label.setText(
                f"Android Version   : {info.android_version}\n"
                f"Build ID          : {info.build_id}\n"
                f"Security Patch    : {info.security_patch}\n"
                f"Baseband Version  : {info.baseband_version}\n"
                f"Bootloader        : {info.bootloader_version}\n"
                f"Build Date        : {info.build_date}\n"
                f"Fingerprint       : {info.build_fingerprint}"
            )
        except ADBError as exc:
            self.firmware_status.setText("? Gagal membaca build info")
            self.firmware_info_label.setText(str(exc))

    def select_firmware_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Pilih file image (.img)", "", "Image Files (*.img);;All Files (*)"
        )

        if file_path:
            self._firmware_image_path = file_path
            self.firmware_image_path_label.setText(f"File dipilih: {file_path}")

    def run_flash_partition(self):
        if not self._firmware_image_path:
            QMessageBox.warning(
                self, "Belum pilih file", "Pilih file image (.img) terlebih dahulu."
            )
            return

        partition = self.firmware_partition_combo.currentText()

        try:
            fastboot_devices = list_fastboot_devices()
        except FastbootError as exc:
            QMessageBox.critical(
                self, "Fastboot Tidak Terdeteksi",
                f"{exc}\n\nPastikan device dalam mode Bootloader dan terhubung."
            )
            return

        if not fastboot_devices:
            QMessageBox.warning(
                self, "Device Tidak Terdeteksi",
                "Tidak ada device dalam mode Fastboot/Bootloader.\n\n"
                "Klik 'Reboot ke Bootloader' terlebih dahulu."
            )
            return

        reply = QMessageBox.question(
            self, "Konfirmasi Flash - RISIKO TINGGI",
            f"Anda akan flash partition '{partition}' dengan file:\n"
            f"{self._firmware_image_path}\n\n"
            f"Tindakan ini BERISIKO membuat device tidak bisa boot jika "
            f"file tidak sesuai. Lanjutkan?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )

        if reply != QMessageBox.Yes:
            return

        serial = fastboot_devices[0]

        self.firmware_flash_log.appendPlainText(
            f"Flashing '{partition}' pada device {serial}..."
        )
        QApplication.processEvents()

        try:
            output = flash_partition(partition, self._firmware_image_path, serial=serial)
            self.firmware_flash_log.appendPlainText(output or "Flash selesai.")
            self.firmware_flash_log.appendPlainText("--- SELESAI ---")
            QMessageBox.information(
                self, "Flash Berhasil", f"Partition '{partition}' berhasil diflash."
            )
        except FastbootError as exc:
            self.firmware_flash_log.appendPlainText(f"ERROR: {exc}")
            QMessageBox.critical(self, "Flash Gagal", str(exc))

    # ------------------------------------------------------------------
    # Placeholder Page
    # ------------------------------------------------------------------

    def create_placeholder_page(self, title_text: str, desc_text: str):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(18)

        title = QLabel(title_text)
        title.setObjectName("contentTitle")

        desc = QLabel(desc_text)
        desc.setObjectName("muted")

        layout.addWidget(title)
        layout.addWidget(desc)
        layout.addStretch()

        return page

    # ------------------------------------------------------------------
    # Multi-device handling
    # ------------------------------------------------------------------

    def refresh_device_list(self):
        try:
            devices = get_devices_with_state()
        except ADBError:
            devices = {}

        if devices != self.devices:
            self.devices = devices
            self._rebuild_device_selector()

        self.dashboard_device_count.setText(
            str(sum(1 for state in devices.values() if state == "device"))
        )

        if self.current_serial and self.current_serial in devices:
            if devices[self.current_serial] == "device":
                self.load_current_device_info()
            else:
                self._set_no_device(
                    f"Device {self.current_serial}: {devices[self.current_serial]}"
                )
        elif self.current_serial and self.current_serial not in devices:
            self.current_serial = None
            self.current_device = None
            self._set_no_device("Device terputus.")

    def _rebuild_device_selector(self):
        self.device_selector.blockSignals(True)
        self.device_selector.clear()

        ready_serials = [s for s, state in self.devices.items() if state == "device"]

        if not ready_serials:
            self.device_selector.addItem("Tidak ada device terhubung")
            self.device_selector.setEnabled(False)
            self.current_serial = None
            self.current_device = None
        else:
            self.device_selector.setEnabled(True)

            for serial in ready_serials:
                self.device_selector.addItem(serial)

            if self.current_serial not in ready_serials:
                self.current_serial = ready_serials[0]

            idx = ready_serials.index(self.current_serial)
            self.device_selector.setCurrentIndex(idx)

        self.device_selector.blockSignals(False)

        if not ready_serials:
            self._set_no_device(
                "Connect an Android device via USB dan aktifkan USB debugging."
            )

    def on_device_selected(self, index: int):
        if index < 0 or not self.device_selector.isEnabled():
            return

        serial = self.device_selector.itemText(index)

        if serial and serial != self.current_serial:
            self.current_serial = serial
            self.load_current_device_info()

    def load_current_device_info(self):
        if not self.current_serial:
            return

        try:
            device = get_device_info(self.current_serial)
            self.current_device = device

            self.dashboard_status.setText("? Device connected")
            self.dashboard_info.setText(
                f"{device.manufacturer} {device.model}\n"
                f"Android {device.android_version}"
            )

            self.device_status.setText("? Connected via ADB")
            self.device_info.setText(
                f"Manufacturer : {device.manufacturer}\n"
                f"Model        : {device.model}\n"
                f"Product      : {device.product}\n"
                f"Device       : {device.device}\n"
                f"Android      : {device.android_version}\n"
                f"Build ID     : {device.build_id}\n"
                f"Serial       : {device.serial}"
            )

            self.reboot_button.setEnabled(True)
            self.recovery_button.setEnabled(True)
            self.bootloader_button.setEnabled(True)

        except ADBError as exc:
            self._set_no_device(str(exc))

    def _set_no_device(self, message: str):
        self.current_device = None

        self.dashboard_status.setText("? No device connected")
        self.dashboard_info.setText(message)

        self.device_status.setText("? No device connected")
        self.device_info.setText(message)

        self.reboot_button.setEnabled(False)
        self.recovery_button.setEnabled(False)
        self.bootloader_button.setEnabled(False)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        if self.logcat_streamer:
            self.logcat_streamer.stop()
        if self.screen_mirror:
            self.screen_mirror.stop()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())
