import sys
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
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

from core.adb import ADBError, get_devices_with_state, reboot_device
from core.device import get_device_info
from core.diagnostics import (
    compute_health_score,
    get_diagnostics,
    health_score_label,
)
from core.database import get_history, save_service_record
from core.logcat import LogcatStreamer
from core.report import generate_service_report


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
            ("logs", "Live Logs"),
            ("history", "Service History"),
            ("firmware", "Firmware"),
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
        self.logs_page = self.create_logs_page()
        self.history_page = self.create_history_page()
        self.firmware_page = self.create_placeholder_page(
            "Firmware", "Fitur flashing/firmware akan segera hadir."
        )

        self.pages.addWidget(self.dashboard_page)
        self.pages.addWidget(self.device_page)
        self.pages.addWidget(self.diagnostics_page)
        self.pages.addWidget(self.logs_page)
        self.pages.addWidget(self.history_page)
        self.pages.addWidget(self.firmware_page)

        self.page_widgets = {
            "dashboard": self.dashboard_page,
            "device": self.device_page,
            "diagnostics": self.diagnostics_page,
            "logs": self.logs_page,
            "history": self.history_page,
            "firmware": self.firmware_page,
        }

        root_layout.addWidget(sidebar)
        root_layout.addWidget(self.pages)

        self.setCentralWidget(root)

        self.switch_page("dashboard")

    def switch_page(self, key: str):
        for k, btn in self.nav_buttons.items():
            btn.setChecked(k == key)

        self.pages.setCurrentWidget(self.page_widgets[key])

        if key == "history":
            self.refresh_history_table()

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
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())
