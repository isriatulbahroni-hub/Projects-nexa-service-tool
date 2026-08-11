import sys
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
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
    QScrollArea,
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
from core.device_diagnostics import run_device_diagnostics
from core.logcat import LogcatStreamer
from core.report import generate_service_report
from core.packages import (
    list_packages,
    install_apk,
    uninstall_package,
    force_stop,
    clear_app_data,
    trim_caches,
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
from core.task_runner import run_in_thread
from core.app_logging import configure_logging, get_logger
from core.settings import SettingsStore
from core.async_worker import AsyncWorker
from core import automation
from core.automation import Macro, MacroStep, ACTIONS, MacroError
from core.service_cases import (
    STATUSES as CASE_STATUSES,
    create_case,
    list_cases,
    get_case,
    update_status as update_case_status,
    add_note as add_case_note,
)
from core.recovery_actions import assess_access, factory_reset_guidance
from core.device_access_recovery import diagnose_access_issue
from core.locked_device_recovery import (
    LockedDeviceRecoveryState,
    detect_locked_device_recovery_state,
    plan_locked_device,
)
from core.frp_verification import (
    collect_frp_verification,
    FRPVerificationError,
)
from core.frp_service import (
    FRPServiceError,
    collect_fastboot_variables,
    detect_frp_service_state,
    execute_bootloader_reboot,
    execute_recovery_reboot,
    verify_frp_result,
)
from core.factory_reset_ui import FactoryResetAssistantPanel
from ui.smart_diagnosis_page import SmartDiagnosisPage

logger = get_logger("app")


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

#navScroll, #contentScroll {
    background: transparent;
    border: none;
}

#navScroll QScrollBar:vertical,
#contentScroll QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 0;
}

#navScroll QScrollBar::handle:vertical,
#contentScroll QScrollBar::handle:vertical {
    background: #3a3f4b;
    border-radius: 5px;
    min-height: 24px;
}

#navScroll QScrollBar::handle:vertical:hover,
#contentScroll QScrollBar::handle:vertical:hover {
    background: #ff5a1f;
}

#navScroll QScrollBar::add-line:vertical,
#navScroll QScrollBar::sub-line:vertical,
#contentScroll QScrollBar::add-line:vertical,
#contentScroll QScrollBar::sub-line:vertical {
    height: 0;
    background: transparent;
}

#navScroll QScrollBar::add-page:vertical,
#navScroll QScrollBar::sub-page:vertical,
#contentScroll QScrollBar::add-page:vertical,
#contentScroll QScrollBar::sub-page:vertical {
    background: transparent;
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

QTableWidget QTableCornerButton::section {
    background: #1a1d24;
    border: none;
}

QTextEdit, QPlainTextEdit {
    background: #14161c;
    color: #d3d7de;
    border: 1px solid #22262f;
    border-radius: 10px;
    padding: 8px;
    selection-background-color: #ff5a1f;
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
        self._current_locked_state: LockedDeviceRecoveryState | None = None
        self._last_frp_verification = None
        self.last_diag = None
        self.last_score = None
        self.last_recommendations: list[str] = []

        self.logcat_streamer: LogcatStreamer | None = None
        self.screen_mirror: ScreenMirror | None = None
        self.file_explorer_path = "/sdcard"

        self.settings = SettingsStore()
        self._macro_steps: list[MacroStep] = []
        self.current_case_id: int | None = None
        self._hardware_task_refs = None  # keeps (thread, worker) alive while running

        self.setStyleSheet(STYLESHEET)

        self.build_ui()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_device_list)
        self.timer.start(int(self.settings.get("auto_refresh_ms", 1500)))

        self.refresh_device_list()
        logger.info("Nexa Service Tool started")

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

        # Menu navigasi dibungkus QScrollArea supaya semua 18 fitur tetap
        # bisa dijangkau walau window di-resize kecil. Sebelumnya sidebar
        # adalah QFrame biasa (fixed height), jadi menu di bawah "Service
        # History" (Firmware & Flash, Hardware Test, Smart Diagnosis,
        # Service Cases, Recovery Assistant, Factory Reset, Settings)
        # terpotong dan tidak bisa diklik sama sekali di window default.
        nav_scroll = QScrollArea()
        nav_scroll.setObjectName("navScroll")
        nav_scroll.setWidgetResizable(True)
        nav_scroll.setFrameShape(QFrame.NoFrame)
        nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        nav_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        nav_scroll.verticalScrollBar().setSingleStep(18)

        nav_container = QWidget()
        nav_layout = QVBoxLayout(nav_container)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(6)

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
            ("smart", "Smart Diagnosis"),
            ("cases", "Service Cases"),
            ("recovery", "Recovery Assistant"),
            ("reset", "Factory Reset"),
            ("automation", "Automation"),
            ("settings", "Settings"),
        ]

        for key, label in nav_items:
            btn = QPushButton(label)
            btn.setObjectName("navBtn")
            btn.setCheckable(True)
            btn.clicked.connect(lambda _, k=key: self.switch_page(k))
            nav_layout.addWidget(btn)
            self.nav_buttons[key] = btn

        nav_layout.addStretch()
        nav_scroll.setWidget(nav_container)
        side_layout.addWidget(nav_scroll, 1)

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
        self.smart_page = self.create_smart_diagnosis_page()
        self.cases_page = self.create_service_cases_page()
        self.recovery_page = self.create_recovery_page()
        self.reset_page = self.create_factory_reset_page()
        self.automation_page = self.create_automation_page()
        self.settings_page = self.create_settings_page()

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
        self.pages.addWidget(self.smart_page)
        self.pages.addWidget(self.cases_page)
        self.pages.addWidget(self.recovery_page)
        self.pages.addWidget(self.reset_page)
        self.pages.addWidget(self.automation_page)
        self.pages.addWidget(self.settings_page)

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
            "smart": self.smart_page,
            "cases": self.cases_page,
            "recovery": self.recovery_page,
            "reset": self.reset_page,
            "automation": self.automation_page,
            "settings": self.settings_page,
        }

        root_layout.addWidget(sidebar)

        # Area konten (di samping sidebar) dibungkus QScrollArea supaya
        # halaman dengan banyak section (mis. Firmware & Flash, Recovery
        # Assistant, Automation) tetap bisa di-scroll penuh kalau tingginya
        # melebihi window - pola sama seperti fix sidebar sebelumnya.
        content_scroll = QScrollArea()
        content_scroll.setObjectName("contentScroll")
        content_scroll.setWidgetResizable(True)
        content_scroll.setFrameShape(QFrame.NoFrame)
        content_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        content_scroll.verticalScrollBar().setSingleStep(18)
        content_scroll.setWidget(self.pages)
        root_layout.addWidget(content_scroll, 1)

        self.content_scroll = content_scroll

        self.setCentralWidget(root)

        self.switch_page("dashboard")

    def refresh_all_data(self):
        """Reload device list + semua data yang sudah pernah di-fetch
        (diagnostics/security/network) sekaligus - semua sudah threaded
        di masing-masing fungsi, jadi aman dipanggil bersamaan tanpa
        nge-freeze UI."""
        self.refresh_device_list()

        if not self.current_device:
            return

        self.refresh_diagnostics()
        self.refresh_security_check()
        self.refresh_network_info()

    def switch_page(self, key: str):
        for k, btn in self.nav_buttons.items():
            btn.setChecked(k == key)

        if key != "mirror" and self.screen_mirror and self.screen_mirror.is_running():
            self.stop_mirror()

        self.pages.setCurrentWidget(self.page_widgets[key])

        if key == "history":
            self.refresh_history_table()
        elif key == "diagnostics":
            self.refresh_diagnostics()
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
        elif key == "cases":
            self.refresh_cases_table()
        elif key == "recovery":
            self.refresh_recovery_assessment()
            self.refresh_locked_device_state()
        elif key == "settings":
            self.load_settings_form()

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

        header_row = QHBoxLayout()
        header_col = QVBoxLayout()
        header_col.addWidget(title)
        header_col.addWidget(desc)
        header_row.addLayout(header_col, 1)

        self.dashboard_refresh_all_button = QPushButton("🔄 Refresh Semua")
        self.dashboard_refresh_all_button.setObjectName("action")
        self.dashboard_refresh_all_button.setToolTip(
            "Reload device list, diagnostics, security check, dan network info sekaligus."
        )
        self.dashboard_refresh_all_button.clicked.connect(self.refresh_all_data)
        header_row.addWidget(self.dashboard_refresh_all_button)

        layout.addLayout(header_row)

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
        self.hardware_summary.setText("Running full hardware test...")

        serial = self.current_serial
        thread, worker = run_in_thread(self, run_hardware_test, serial)
        self._hardware_task_refs = (thread, worker)

        worker.finished.connect(self._on_hardware_test_finished)
        worker.failed.connect(self._on_hardware_test_failed)

    def _on_hardware_test_finished(self, report):
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
        self.hardware_run_button.setEnabled(True)
        self._hardware_task_refs = None

    def _on_hardware_test_failed(self, message: str):
        logger.error("Hardware test failed: %s", message)
        QMessageBox.critical(self, "Hardware Test Error", message)
        self.hardware_run_button.setEnabled(True)
        self._hardware_task_refs = None

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

        title = QLabel("Device Diagnostics")
        title.setObjectName("contentTitle")

        desc = QLabel(
            "Komprehensif diagnostics perangkat: ADB, boot, battery, storage, software, dan network."
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

        self.diag_table = QTableWidget(0, 5)
        self.diag_table.setHorizontalHeaderLabels(
            ["Category", "Check", "Status", "Value", "Detail"]
        )
        self.diag_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.diag_table.setSelectionMode(QTableWidget.NoSelection)
        self.diag_table.horizontalHeader().setStretchLastSection(True)
        self.diag_table.setMinimumHeight(260)
        layout.addWidget(self.diag_table)

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
            self.diag_status.setText("⚠ No device connected")
            self.diag_info.setText("Hubungkan device via USB terlebih dahulu.")
            self.diag_score_value.setText("--")
            self.diag_score_bar.setValue(0)
            self.diag_recommendations.setPlainText("")
            return

        if getattr(self, "_diag_worker", None) and self._diag_worker.isRunning():
            return

        self.diag_status.setText("⏳ Memuat diagnostics...")
        serial = self.current_device.serial

        def task():
            diag = get_diagnostics(serial)
            report = run_device_diagnostics(serial)
            score, recommendations = compute_health_score(diag)
            return diag, report, score, recommendations

        self._diag_worker = AsyncWorker(task, self)
        self._diag_worker.succeeded.connect(self._on_diagnostics_ready)
        self._diag_worker.failed.connect(self._on_diagnostics_error)
        self._diag_worker.start()

    def _on_diagnostics_ready(self, result):
        diag, report, score, recommendations = result

        self.last_diag = diag
        self.last_report = report
        self.last_score = score
        self.last_recommendations = recommendations

        self.diag_status.setText("✅ Diagnostics OK")
        self.diag_info.setText(
            f"{report.summary}\n"
            f"Battery Level    : {diag.battery_level}\n"
            f"Battery Status   : {diag.battery_status}\n"
            f"Battery Health   : {diag.battery_health}\n"
            f"Storage          : {diag.storage}\n"
            f"Screen State     : {diag.screen_state}\n"
            f"USB Debugging    : {diag.usb_debugging}"
        )

        self.diag_table.setRowCount(len(report.items))
        for row_index, item in enumerate(report.items):
            self.diag_table.setItem(row_index, 0, QTableWidgetItem(item.category))
            self.diag_table.setItem(row_index, 1, QTableWidgetItem(item.name))
            self.diag_table.setItem(row_index, 2, QTableWidgetItem(item.status.value))
            self.diag_table.setItem(row_index, 3, QTableWidgetItem(item.value))
            self.diag_table.setItem(row_index, 4, QTableWidgetItem(item.detail))

        self.diag_table.resizeColumnsToContents()

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

    def _on_diagnostics_error(self, message: str):
        self.diag_status.setText("❌ Diagnostics error")
        self.diag_info.setText(message)
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
            self.security_status.setText("⚠ No device connected")
            self.security_info.setText("Hubungkan device terlebih dahulu.")
            self.security_warnings.setPlainText("")
            return

        if getattr(self, "_security_worker", None) and self._security_worker.isRunning():
            return

        self.security_status.setText("⏳ Menjalankan security check...")
        serial = self.current_device.serial

        self._security_worker = AsyncWorker(lambda: run_security_check(serial), self)
        self._security_worker.succeeded.connect(self._on_security_ready)
        self._security_worker.failed.connect(self._on_security_error)
        self._security_worker.start()

    def _on_security_ready(self, result):
        root_icon = "⚠️" if result.is_rooted else "✅"

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

    def _on_security_error(self, message: str):
        self.security_status.setText("❌ Security check gagal")
        self.security_info.setText(message)
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

        self.apps_repair_button = QPushButton("🔧 Repair (Trim Cache)")
        self.apps_repair_button.setObjectName("action")
        self.apps_repair_button.setToolTip(
            "Bersihkan cache SEMUA aplikasi (setara 'Free up space' di "
            "Settings Android). Tidak menghapus data/login/foto - aman."
        )
        self.apps_repair_button.clicked.connect(self.repair_trim_caches)

        self.apps_clear_button = QPushButton("Clear Data")
        self.apps_clear_button.setObjectName("action")
        self.apps_clear_button.clicked.connect(self.clear_data_selected_app)

        self.apps_uninstall_button = QPushButton("Uninstall")
        self.apps_uninstall_button.setObjectName("actionDanger")
        self.apps_uninstall_button.clicked.connect(self.uninstall_selected_app)

        action_row.addWidget(self.apps_stop_button)
        action_row.addWidget(self.apps_repair_button)
        action_row.addWidget(self.apps_clear_button)
        action_row.addWidget(self.apps_uninstall_button)

        layout.addLayout(action_row)

        return page

    def refresh_apps_list(self):
        self.apps_list.clear()

        if not self.current_device:
            self.apps_list.addItem("Tidak ada device terhubung")
            return

        if getattr(self, "_apps_worker", None) and self._apps_worker.isRunning():
            return

        self.apps_list.addItem("⏳ Memuat daftar aplikasi...")
        serial = self.current_device.serial

        self._apps_worker = AsyncWorker(
            lambda: list_packages(serial, include_system=False), self
        )
        self._apps_worker.succeeded.connect(self._on_apps_list_ready)
        self._apps_worker.failed.connect(self._on_apps_list_error)
        self._apps_worker.start()

    def _on_apps_list_ready(self, packages):
        self.apps_list.clear()

        if not packages:
            self.apps_list.addItem("Tidak ada aplikasi pihak ketiga terdeteksi.")
            return

        for pkg in packages:
            self.apps_list.addItem(pkg.package_name)

    def _on_apps_list_error(self, message: str):
        self.apps_list.clear()
        self.apps_list.addItem(f"Error: {message}")

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

    def repair_trim_caches(self):
        if not self.current_device:
            QMessageBox.warning(self, "Tidak ada device", "Hubungkan device dulu.")
            return

        if getattr(self, "_repair_worker", None) and self._repair_worker.isRunning():
            return

        reply = QMessageBox.question(
            self, "Repair - Trim Cache",
            "Bersihkan cache SEMUA aplikasi di device ini?\n\n"
            "Ini AMAN - setara fitur 'Free up space' di Settings Android. "
            "Tidak menghapus data, login, foto, atau file apapun - hanya "
            "file cache sementara yang bisa dibuat ulang otomatis oleh app.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
        )
        if reply != QMessageBox.Yes:
            return

        self.apps_repair_button.setEnabled(False)
        self.apps_repair_button.setText("⏳ Membersihkan cache...")
        serial = self.current_device.serial

        self._repair_worker = AsyncWorker(lambda: trim_caches(serial), self)
        self._repair_worker.succeeded.connect(self._on_repair_finished)
        self._repair_worker.failed.connect(self._on_repair_failed)
        self._repair_worker.start()

    def _on_repair_finished(self, _output):
        self.apps_repair_button.setEnabled(True)
        self.apps_repair_button.setText("🔧 Repair (Trim Cache)")
        QMessageBox.information(
            self, "Repair Selesai",
            "Cache semua aplikasi berhasil dibersihkan. Device mungkin "
            "terasa lebih responsif dan ada tambahan storage kosong."
        )

    def _on_repair_failed(self, message: str):
        self.apps_repair_button.setEnabled(True)
        self.apps_repair_button.setText("🔧 Repair (Trim Cache)")
        QMessageBox.critical(self, "Repair Gagal", message)

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

        if getattr(self, "_files_worker", None) and self._files_worker.isRunning():
            return

        self.files_list.addItem("⏳ Memuat isi folder...")
        serial = self.current_device.serial
        path = self.file_explorer_path

        self._files_worker = AsyncWorker(lambda: list_dir(serial, path), self)
        self._files_worker.succeeded.connect(self._on_file_list_ready)
        self._files_worker.failed.connect(self._on_file_list_error)
        self._files_worker.start()

    def _on_file_list_ready(self, entries):
        self.files_list.clear()

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

    def _on_file_list_error(self, message: str):
        self.files_list.clear()
        self.files_list.addItem(f"Error: {message}")

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

        serial = self.current_device.serial
        self.backup_button.setEnabled(False)
        self.restore_button.setEnabled(False)

        worker = AsyncWorker(
            lambda: backup_device(serial, Path(output_dir)),
            self,
        )
        worker.succeeded.connect(self._on_backup_complete)
        worker.failed.connect(self._on_backup_failed)
        worker.start()
        self._backup_worker = worker

    def _on_backup_complete(self, zip_path):
        self.backup_button.setEnabled(True)
        self.restore_button.setEnabled(True)
        self.backup_log.appendPlainText(f"Backup selesai: {zip_path}")
        QMessageBox.information(self, "Backup Selesai", f"File tersimpan di:\n{zip_path}")

    def _on_backup_failed(self, message: str):
        self.backup_button.setEnabled(True)
        self.restore_button.setEnabled(True)
        self.backup_log.appendPlainText(f"Backup gagal: {message}")
        QMessageBox.critical(self, "Backup Gagal", message)

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

        serial = self.current_device.serial
        self.backup_button.setEnabled(False)
        self.restore_button.setEnabled(False)

        worker = AsyncWorker(
            lambda: restore_device(serial, Path(zip_path)),
            self,
        )
        worker.succeeded.connect(self._on_restore_complete)
        worker.failed.connect(self._on_restore_failed)
        worker.start()
        self._restore_worker = worker

    def _on_restore_complete(self, results):
        self.backup_button.setEnabled(True)
        self.restore_button.setEnabled(True)
        for line in results:
            self.backup_log.appendPlainText(line)
        QMessageBox.information(self, "Restore Selesai", "Proses restore selesai.")

    def _on_restore_failed(self, message: str):
        self.backup_button.setEnabled(True)
        self.restore_button.setEnabled(True)
        self.backup_log.appendPlainText(f"Restore gagal: {message}")
        QMessageBox.critical(self, "Restore Gagal", message)

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
            self.network_status.setText("⚠ No device connected")
            self.network_info_label.setText("Hubungkan device terlebih dahulu.")
            return

        if getattr(self, "_network_worker", None) and self._network_worker.isRunning():
            return

        self.network_status.setText("⏳ Membaca network info...")
        serial = self.current_device.serial

        self._network_worker = AsyncWorker(lambda: get_network_info(serial), self)
        self._network_worker.succeeded.connect(self._on_network_ready)
        self._network_worker.failed.connect(self._on_network_error)
        self._network_worker.start()

    def _on_network_ready(self, info):
        self.network_status.setText("✅ Network Info OK")
        self.network_info_label.setText(
            f"IMEI              : {info.imei}\n"
            f"WiFi              : {info.wifi_state}\n"
            f"Mobile Data       : {info.mobile_data_state}\n"
            f"IP Address        : {info.ip_address}\n"
            f"Network Operator  : {info.network_operator}\n"
            f"SIM State         : {info.sim_state}\n"
            f"Phone Type        : {info.phone_type}"
        )

    def _on_network_error(self, message: str):
        self.network_status.setText("❌ Gagal membaca network info")
        self.network_info_label.setText(message)

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
            self.firmware_status.setText("⚠ No device connected")
            self.firmware_info_label.setText(
                "Hubungkan device (mode normal) untuk melihat info build."
            )
            return

        if getattr(self, "_firmware_worker", None) and self._firmware_worker.isRunning():
            return

        self.firmware_status.setText("⏳ Membaca build info...")
        serial = self.current_device.serial

        self._firmware_worker = AsyncWorker(lambda: get_build_info(serial), self)
        self._firmware_worker.succeeded.connect(self._on_firmware_info_ready)
        self._firmware_worker.failed.connect(self._on_firmware_info_error)
        self._firmware_worker.start()

    def _on_firmware_info_ready(self, info):
        self.firmware_status.setText("✅ Build Info OK")
        self.firmware_info_label.setText(
            f"Android Version   : {info.android_version}\n"
            f"Build ID          : {info.build_id}\n"
            f"Security Patch    : {info.security_patch}\n"
            f"Baseband Version  : {info.baseband_version}\n"
            f"Bootloader        : {info.bootloader_version}\n"
            f"Build Date        : {info.build_date}\n"
            f"Fingerprint       : {info.build_fingerprint}"
        )

    def _on_firmware_info_error(self, message: str):
        self.firmware_status.setText("❌ Gagal membaca build info")
        self.firmware_info_label.setText(message)

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

    # ------------------------------------------------------------------
    # Smart Diagnosis Page
    # ------------------------------------------------------------------

    def create_smart_diagnosis_page(self):
        self.smart_diagnosis_widget = SmartDiagnosisPage(
            facts_provider=self._collect_smart_diagnosis_facts
        )
        return self.smart_diagnosis_widget

    def _collect_smart_diagnosis_facts(self) -> dict:
        """Gather real facts from the currently selected device for Smart Diagnosis.

        Best-effort: any single check failing (e.g. root check needs a shell
        that isn't available) must not stop the others from being collected.
        """
        facts: dict = {}

        if not self.current_serial:
            facts["connection_state"] = "not_detected"
            return facts

        state = self.devices.get(self.current_serial, "not_detected")
        facts["connection_state"] = state

        if state != "device":
            return facts

        try:
            diag = get_diagnostics(self.current_serial)
            level = diag.battery_level.replace("%", "").strip()
            if level.lstrip("-").isdigit():
                facts["battery_percent"] = int(level)
        except (ADBError, ValueError, AttributeError) as exc:
            logger.warning("Smart diagnosis: gagal ambil battery info: %s", exc)

        try:
            network = get_network_info(self.current_serial)
            facts["imei"] = network.imei
        except ADBError as exc:
            logger.warning("Smart diagnosis: gagal ambil network info: %s", exc)

        try:
            security = run_security_check(self.current_serial)
            facts["root_detected"] = security.is_rooted
        except ADBError as exc:
            logger.warning("Smart diagnosis: gagal ambil security check: %s", exc)

        if getattr(self, "last_hardware_report", None):
            failed = [
                item.name for item in self.last_hardware_report.results
                if item.status == "FAIL"
            ]
            if failed:
                facts["hardware_failures"] = failed

        return facts

    # ------------------------------------------------------------------
    # Service Cases Page
    # ------------------------------------------------------------------

    def create_service_cases_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(14)

        title = QLabel("Service Cases")
        title.setObjectName("contentTitle")
        desc = QLabel("Catat & lacak setiap job servis dari masuk sampai selesai.")
        desc.setObjectName("muted")
        layout.addWidget(title)
        layout.addWidget(desc)

        form_card = QFrame()
        form_card.setObjectName("card")
        form_layout = QVBoxLayout(form_card)
        form_layout.setContentsMargins(20, 16, 20, 16)
        form_layout.setSpacing(8)

        form_title = QLabel("Case Baru")
        form_title.setObjectName("cardTitle")
        form_layout.addWidget(form_title)

        self.case_customer_name = QLineEdit()
        self.case_customer_name.setPlaceholderText("Nama customer *")
        self.case_customer_phone = QLineEdit()
        self.case_customer_phone.setPlaceholderText("No. HP customer")
        self.case_complaint = QLineEdit()
        self.case_complaint.setPlaceholderText("Keluhan (mis: layar retak, tidak mau nyala) *")
        self.case_technician = QLineEdit()
        self.case_technician.setPlaceholderText("Teknisi penanggung jawab")
        self.case_cost = QLineEdit()
        self.case_cost.setPlaceholderText("Estimasi biaya (Rp)")

        for widget in (
            self.case_customer_name, self.case_customer_phone,
            self.case_complaint, self.case_technician, self.case_cost,
        ):
            form_layout.addWidget(widget)

        self.case_use_current_device = QLabel("")
        self.case_use_current_device.setObjectName("muted")
        self.case_use_current_device.setWordWrap(True)
        form_layout.addWidget(self.case_use_current_device)

        self.case_save_button = QPushButton("Simpan Case Baru")
        self.case_save_button.setObjectName("actionPrimary")
        self.case_save_button.clicked.connect(self.create_new_case)
        form_layout.addWidget(self.case_save_button)

        layout.addWidget(form_card)

        filter_row = QHBoxLayout()
        self.case_search = QLineEdit()
        self.case_search.setPlaceholderText("Cari nama customer / case number...")
        self.case_status_filter = QComboBox()
        self.case_status_filter.addItem("Semua Status")
        for status in CASE_STATUSES:
            self.case_status_filter.addItem(status)
        self.case_refresh_button = QPushButton("Refresh")
        self.case_refresh_button.clicked.connect(self.refresh_cases_table)
        filter_row.addWidget(self.case_search, 2)
        filter_row.addWidget(self.case_status_filter, 1)
        filter_row.addWidget(self.case_refresh_button)
        layout.addLayout(filter_row)

        self.cases_table = QTableWidget(0, 6)
        self.cases_table.setHorizontalHeaderLabels(
            ["Case #", "Customer", "Device", "Complaint", "Status", "Updated"]
        )
        self.cases_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.cases_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.cases_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.cases_table, 1)

        action_row = QHBoxLayout()
        self.case_update_status_button = QPushButton("Update Status")
        self.case_update_status_button.clicked.connect(self.update_selected_case_status)
        self.case_add_note_button = QPushButton("Tambah Catatan")
        self.case_add_note_button.clicked.connect(self.add_note_to_selected_case)
        self.case_response_button = QPushButton("💬 Respons ke Customer")
        self.case_response_button.setObjectName("action")
        self.case_response_button.clicked.connect(self.generate_customer_response)
        action_row.addWidget(self.case_update_status_button)
        action_row.addWidget(self.case_add_note_button)
        action_row.addWidget(self.case_response_button)
        action_row.addStretch()
        layout.addLayout(action_row)

        self.case_search.textChanged.connect(self.refresh_cases_table)
        self.case_status_filter.currentIndexChanged.connect(self.refresh_cases_table)

        return page

    def create_new_case(self):
        customer_name = self.case_customer_name.text().strip()
        complaint = self.case_complaint.text().strip()

        if not customer_name or not complaint:
            QMessageBox.warning(self, "Data Kurang", "Nama customer dan keluhan wajib diisi.")
            return

        try:
            cost_text = self.case_cost.text().strip().replace(".", "").replace(",", "")
            cost = float(cost_text) if cost_text else 0
        except ValueError:
            QMessageBox.warning(self, "Biaya Tidak Valid", "Estimasi biaya harus berupa angka.")
            return

        device = self.current_device
        try:
            case = create_case(
                customer_name=customer_name,
                complaint=complaint,
                customer_phone=self.case_customer_phone.text().strip(),
                device_serial=device.serial if device else "",
                manufacturer=device.manufacturer if device else "",
                model=device.model if device else "",
                technician=self.case_technician.text().strip(),
                estimated_cost=cost,
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Gagal Menyimpan Case", str(exc))
            return

        logger.info("Service case dibuat: %s", case.case_number)
        QMessageBox.information(self, "Case Dibuat", f"Case {case.case_number} berhasil disimpan.")

        for widget in (
            self.case_customer_name, self.case_customer_phone,
            self.case_complaint, self.case_technician, self.case_cost,
        ):
            widget.clear()

        self.refresh_cases_table()

    def generate_customer_response(self):
        case_id = self._selected_case_id()
        if case_id is None:
            QMessageBox.information(self, "Pilih Case", "Pilih case dari tabel dulu.")
            return

        try:
            case = get_case(case_id)
        except Exception as exc:
            QMessageBox.critical(self, "Gagal", str(exc))
            return

        device_label = f"{case.manufacturer} {case.model}".strip() or "device Anda"
        name = case.customer_name or "Bapak/Ibu"

        templates = {
            "Received": (
                f"Halo {name}, {device_label} Anda (No. Servis: {case.case_number}) "
                f"sudah kami terima dan masuk antrian pengecekan. Kami akan kabari "
                f"lagi setelah diagnosa awal selesai. Terima kasih."
            ),
            "Diagnosing": (
                f"Halo {name}, {device_label} Anda (No. Servis: {case.case_number}) "
                f"sedang dalam proses diagnosa oleh teknisi kami. Estimasi hasil "
                f"diagnosa akan kami informasikan segera."
            ),
            "Repairing": (
                f"Halo {name}, {device_label} Anda (No. Servis: {case.case_number}) "
                f"sedang dalam proses perbaikan. "
                + (f"Estimasi biaya: Rp{case.estimated_cost:,.0f}. ".replace(",", ".") if case.estimated_cost else "")
                + "Kami akan kabari begitu selesai."
            ),
            "Testing": (
                f"Halo {name}, perbaikan {device_label} Anda (No. Servis: {case.case_number}) "
                f"sudah selesai dan sedang tahap pengujian akhir sebelum diserahkan kembali."
            ),
            "Completed": (
                f"Halo {name}, {device_label} Anda (No. Servis: {case.case_number}) "
                f"sudah SELESAI diperbaiki dan siap diambil. "
                + (f"Total biaya: Rp{case.estimated_cost:,.0f}. ".replace(",", ".") if case.estimated_cost else "")
                + "Ditunggu kedatangannya, terima kasih!"
            ),
            "Cancelled": (
                f"Halo {name}, servis {device_label} Anda (No. Servis: {case.case_number}) "
                f"telah dibatalkan. Silakan hubungi kami jika ada pertanyaan."
            ),
        }

        message = templates.get(
            case.status,
            f"Halo {name}, update untuk servis {device_label} (No. Servis: {case.case_number}): {case.status}.",
        )

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Respons untuk {case.customer_name} ({case.case_number})")
        dialog.setMinimumWidth(420)
        dlg_layout = QVBoxLayout(dialog)

        info_label = QLabel(
            f"Template otomatis berdasarkan status case saat ini: <b>{case.status}</b>. "
            f"Edit dulu sesuai kebutuhan, lalu copy untuk dikirim manual via WhatsApp/SMS."
        )
        info_label.setWordWrap(True)
        dlg_layout.addWidget(info_label)

        text_edit = QTextEdit()
        text_edit.setPlainText(message)
        text_edit.setMinimumHeight(140)
        dlg_layout.addWidget(text_edit)

        btn_row = QHBoxLayout()
        copy_button = QPushButton("Copy ke Clipboard")

        def do_copy():
            QApplication.clipboard().setText(text_edit.toPlainText())
            copy_button.setText("✅ Tersalin!")

        copy_button.clicked.connect(do_copy)
        close_button = QPushButton("Tutup")
        close_button.clicked.connect(dialog.accept)
        btn_row.addWidget(copy_button)
        btn_row.addWidget(close_button)
        dlg_layout.addLayout(btn_row)

        dialog.exec()

    def refresh_cases_table(self):
        status_text = self.case_status_filter.currentText()
        status = None if status_text == "Semua Status" else status_text
        search = self.case_search.text().strip()

        try:
            cases = list_cases(status=status, search=search)
        except Exception as exc:
            logger.error("Gagal memuat service cases: %s", exc)
            return

        self.cases_table.setRowCount(len(cases))
        for row, case in enumerate(cases):
            device_label = f"{case.manufacturer} {case.model}".strip() or "-"
            values = [
                case.case_number, case.customer_name, device_label,
                case.complaint, case.status, case.updated_at,
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.UserRole, case.id)
                self.cases_table.setItem(row, col, item)

    def _selected_case_id(self) -> int | None:
        row = self.cases_table.currentRow()
        if row < 0:
            return None
        item = self.cases_table.item(row, 0)
        return item.data(Qt.UserRole) if item else None

    def update_selected_case_status(self):
        case_id = self._selected_case_id()
        if case_id is None:
            QMessageBox.information(self, "Pilih Case", "Pilih case dari tabel dulu.")
            return

        status, ok = QInputDialog.getItem(
            self, "Update Status", "Status baru:", list(CASE_STATUSES), 0, False
        )
        if not ok:
            return

        note, _ = QInputDialog.getText(self, "Catatan (opsional)", "Catatan perubahan status:")

        try:
            update_case_status(case_id, status, note.strip())
        except ValueError as exc:
            QMessageBox.warning(self, "Gagal Update", str(exc))
            return

        self.refresh_cases_table()

    def add_note_to_selected_case(self):
        case_id = self._selected_case_id()
        if case_id is None:
            QMessageBox.information(self, "Pilih Case", "Pilih case dari tabel dulu.")
            return

        note, ok = QInputDialog.getMultiLineText(self, "Tambah Catatan", "Catatan:")
        if not ok or not note.strip():
            return

        add_case_note(case_id, note.strip())
        QMessageBox.information(self, "Catatan Ditambahkan", "Catatan berhasil disimpan ke case ini.")

    # ------------------------------------------------------------------
    # Recovery Assistant Page (locked / inaccessible devices)
    #
    # Read-only guidance only. Never bypasses PIN/pattern/password/FRP --
    # this deliberately mirrors the safety guarantees already enforced in
    # core/recovery_actions.py, core/device_access_recovery.py, and
    # core/locked_device_recovery.py.
    # ------------------------------------------------------------------

    def create_recovery_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(14)

        title = QLabel("Recovery Assistant")
        title.setObjectName("contentTitle")

        desc = QLabel(
            "Assessment read-only untuk device yang tidak bisa diakses. "
            "Nexa tidak melakukan bypass PIN/pattern/password/FRP. "
            "Gunakan verifikasi kepemilikan resmi sebelum tindakan lanjutan."
        )
        desc.setObjectName("muted")
        desc.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(desc)

        # --------------------------------------------------------
        # Access / Recovery Assessment
        # --------------------------------------------------------
        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(22, 20, 22, 20)
        card_layout.setSpacing(9)

        self.recovery_status = QLabel("Belum ada device dipilih.")
        self.recovery_status.setObjectName("status")

        self.recovery_recommended = QLabel("")
        self.recovery_recommended.setObjectName("value")
        self.recovery_recommended.setWordWrap(True)

        self.recovery_warning = QLabel("")
        self.recovery_warning.setObjectName("value")
        self.recovery_warning.setWordWrap(True)

        card_layout.addWidget(self.recovery_status)
        card_layout.addWidget(self.recovery_recommended)
        card_layout.addWidget(self.recovery_warning)

        layout.addWidget(card)

        # --------------------------------------------------------
        # FRP / Owner Verification - READ ONLY
        # --------------------------------------------------------
        frp_title = QLabel("FRP / Owner Verification")
        frp_title.setObjectName("cardTitle")
        layout.addWidget(frp_title)

        frp_card = QFrame()
        frp_card.setObjectName("card")
        frp_layout = QVBoxLayout(frp_card)
        frp_layout.setContentsMargins(22, 20, 22, 20)
        frp_layout.setSpacing(8)

        self.frp_status_label = QLabel(
            "FRP Status: Belum diperiksa"
        )
        self.frp_status_label.setObjectName("status")

        self.frp_owner_label = QLabel(
            "Owner Verification: -"
        )
        self.frp_owner_label.setObjectName("value")

        self.frp_device_label = QLabel(
            "Device: -"
        )
        self.frp_device_label.setObjectName("value")

        self.frp_setup_label = QLabel(
            "Setup Wizard: -"
        )
        self.frp_setup_label.setObjectName("value")

        self.frp_provisioned_label = QLabel(
            "Device Provisioned: -"
        )
        self.frp_provisioned_label.setObjectName("value")

        self.frp_indicator_label = QLabel(
            "FRP Provisioned Indicator: -"
        )
        self.frp_indicator_label.setObjectName("value")

        self.frp_bootloader_label = QLabel(
            "Bootloader: -"
        )
        self.frp_bootloader_label.setObjectName("value")

        self.frp_verified_boot_label = QLabel(
            "Verified Boot: -"
        )
        self.frp_verified_boot_label.setObjectName("value")

        self.frp_service_state_label = QLabel(
            "Service State: -"
        )
        self.frp_service_state_label.setObjectName("value")

        self.frp_fastboot_label = QLabel(
            "Fastboot: -"
        )
        self.frp_fastboot_label.setObjectName("value")

        self.frp_fastboot_info_label = QLabel(
            "Fastboot vars: -"
        )
        self.frp_fastboot_info_label.setObjectName("value")
        self.frp_fastboot_info_label.setWordWrap(True)

        self.frp_service_message_label = QLabel("")
        self.frp_service_message_label.setObjectName("muted")
        self.frp_service_message_label.setWordWrap(True)

        self.frp_brand_label = QLabel("Brand/Family: -")
        self.frp_brand_label.setObjectName("value")

        self.frp_model_label = QLabel("Model: -")
        self.frp_model_label.setObjectName("value")

        self.frp_guidance_label = QLabel("Workflow Guidance: -")
        self.frp_guidance_label.setObjectName("muted")
        self.frp_guidance_label.setWordWrap(True)

        self.frp_message_label = QLabel("")
        self.frp_message_label.setObjectName("muted")
        self.frp_message_label.setWordWrap(True)

        self.frp_operation_message_label = QLabel("")
        self.frp_operation_message_label.setObjectName("muted")
        self.frp_operation_message_label.setWordWrap(True)

        for widget in (
            self.frp_status_label,
            self.frp_owner_label,
            self.frp_device_label,
            self.frp_brand_label,
            self.frp_model_label,
            self.frp_setup_label,
            self.frp_provisioned_label,
            self.frp_indicator_label,
            self.frp_bootloader_label,
            self.frp_verified_boot_label,
            self.frp_service_state_label,
            self.frp_fastboot_label,
            self.frp_fastboot_info_label,
            self.frp_message_label,
            self.frp_service_message_label,
            self.frp_guidance_label,
            self.frp_operation_message_label,
        ):
            frp_layout.addWidget(widget)

        self.frp_refresh_button = QPushButton(
            "Refresh FRP / Owner Verification"
        )
        self.frp_refresh_button.setObjectName("action")
        self.frp_refresh_button.clicked.connect(
            self.refresh_frp_verification
        )
        frp_layout.addWidget(self.frp_refresh_button)

        self.frp_service_refresh_button = QPushButton(
            "Refresh FRP Service State"
        )
        self.frp_service_refresh_button.setObjectName("action")
        self.frp_service_refresh_button.clicked.connect(
            self.refresh_frp_service_state
        )
        frp_layout.addWidget(self.frp_service_refresh_button)

        self.frp_recovery_button = QPushButton("Reboot ke Recovery")
        self.frp_recovery_button.setObjectName("action")
        self.frp_recovery_button.setEnabled(False)
        self.frp_recovery_button.clicked.connect(self.reboot_to_recovery)
        frp_layout.addWidget(self.frp_recovery_button)

        self.frp_bootloader_button = QPushButton("Reboot ke Bootloader")
        self.frp_bootloader_button.setObjectName("action")
        self.frp_bootloader_button.setEnabled(False)
        self.frp_bootloader_button.clicked.connect(
            self.reboot_to_bootloader
        )
        frp_layout.addWidget(self.frp_bootloader_button)

        self.frp_verify_button = QPushButton("Verify FRP Result")
        self.frp_verify_button.setObjectName("action")
        self.frp_verify_button.setEnabled(False)
        self.frp_verify_button.clicked.connect(self.verify_frp_result_action)
        frp_layout.addWidget(self.frp_verify_button)

        layout.addWidget(frp_card)

        # --------------------------------------------------------
        # Locked Device Recovery Workflow
        # --------------------------------------------------------
        recovery_title = QLabel("Locked Device Recovery Workflow")
        recovery_title.setObjectName("cardTitle")
        layout.addWidget(recovery_title)

        recovery_card = QFrame()
        recovery_card.setObjectName("card")
        recovery_layout = QVBoxLayout(recovery_card)
        recovery_layout.setContentsMargins(22, 20, 22, 20)
        recovery_layout.setSpacing(8)

        self.locked_state_label = QLabel("Locked Recovery State: -")
        self.locked_state_label.setObjectName("status")

        self.locked_identity_label = QLabel("Device Identity: -")
        self.locked_identity_label.setObjectName("value")

        self.locked_mode_label = QLabel("Mode: -")
        self.locked_mode_label.setObjectName("value")

        self.locked_options_label = QLabel("Recovery Options: -")
        self.locked_options_label.setObjectName("muted")
        self.locked_options_label.setWordWrap(True)

        self.locked_supported_label = QLabel("Supported Actions: -")
        self.locked_supported_label.setObjectName("value")

        self.locked_tools_label = QLabel("Recommended Tools: -")
        self.locked_tools_label.setObjectName("muted")
        self.locked_tools_label.setWordWrap(True)

        self.locked_confirm_label = QLabel("Confirmation: -")
        self.locked_confirm_label.setObjectName("value")

        self.locked_action_message_label = QLabel("")
        self.locked_action_message_label.setObjectName("muted")
        self.locked_action_message_label.setWordWrap(True)

        for widget in (
            self.locked_state_label,
            self.locked_identity_label,
            self.locked_mode_label,
            self.locked_options_label,
            self.locked_supported_label,
            self.locked_tools_label,
            self.locked_confirm_label,
            self.locked_action_message_label,
        ):
            recovery_layout.addWidget(widget)

        self.locked_detect_button = QPushButton("Detect Locked Device State")
        self.locked_detect_button.setObjectName("action")
        self.locked_detect_button.clicked.connect(self.refresh_locked_device_state)
        recovery_layout.addWidget(self.locked_detect_button)

        self.locked_confirm_button = QPushButton("Confirm Recovery Action")
        self.locked_confirm_button.setObjectName("action")
        self.locked_confirm_button.setEnabled(False)
        self.locked_confirm_button.clicked.connect(self.confirm_recovery_action)
        recovery_layout.addWidget(self.locked_confirm_button)

        self.locked_recovery_button = QPushButton("Reboot ke Recovery (Locked Device)")
        self.locked_recovery_button.setObjectName("action")
        self.locked_recovery_button.setEnabled(False)
        self.locked_recovery_button.clicked.connect(self.reboot_locked_recovery)
        recovery_layout.addWidget(self.locked_recovery_button)

        self.locked_bootloader_button = QPushButton("Reboot ke Bootloader (Locked Device)")
        self.locked_bootloader_button.setObjectName("action")
        self.locked_bootloader_button.setEnabled(False)
        self.locked_bootloader_button.clicked.connect(self.reboot_locked_bootloader)
        recovery_layout.addWidget(self.locked_bootloader_button)

        self.locked_verify_button = QPushButton("Verify Locked Device Result")
        self.locked_verify_button.setObjectName("action")
        self.locked_verify_button.setEnabled(False)
        self.locked_verify_button.clicked.connect(self.verify_locked_result)
        recovery_layout.addWidget(self.locked_verify_button)

        layout.addWidget(recovery_card)

        # --------------------------------------------------------
        # Recovery Plan
        # --------------------------------------------------------
        plan_title = QLabel(
            "Rencana Pemulihan (Locked Device Plan)"
        )
        plan_title.setObjectName("cardTitle")
        layout.addWidget(plan_title)

        self.recovery_plan_text = QTextEdit()
        self.recovery_plan_text.setObjectName("value")
        self.recovery_plan_text.setReadOnly(True)
        self.recovery_plan_text.setFixedHeight(160)
        layout.addWidget(self.recovery_plan_text)

        self.recovery_refresh_button = QPushButton(
            "Jalankan Assessment"
        )
        self.recovery_refresh_button.setObjectName(
            "actionPrimary"
        )
        self.recovery_refresh_button.clicked.connect(
            self.refresh_recovery_assessment
        )
        layout.addWidget(self.recovery_refresh_button)

        layout.addStretch()

        return page

    def refresh_frp_verification(self):
        """Run read-only FRP/owner verification on active device."""

        if not self.current_serial:
            self.frp_status_label.setText(
                "FRP Status: Tidak ada device"
            )
            self.frp_owner_label.setText(
                "Owner Verification: -"
            )
            self.frp_device_label.setText(
                "Device: -"
            )
            self.frp_message_label.setText(
                "Hubungkan dan authorize device melalui ADB terlebih dahulu."
            )
            return

        serial = self.current_serial

        self.frp_status_label.setText(
            "FRP Status: Memeriksa..."
        )
        self.frp_owner_label.setText(
            "Owner Verification: Memeriksa..."
        )
        self.frp_message_label.setText(
            "Menjalankan pemeriksaan ADB read-only..."
        )
        self.frp_refresh_button.setEnabled(False)

        try:
            result = collect_frp_verification(serial)

            self.frp_status_label.setText(
                f"FRP Status: {result.frp_status}"
            )

            owner_text = (
                "REQUIRED"
                if result.owner_verification_required
                else "NOT REQUIRED"
            )

            self.frp_owner_label.setText(
                f"Owner Verification: {owner_text}"
            )

            self.frp_device_label.setText(
                f"Device: {result.manufacturer} "
                f"{result.model} | Android {result.android_version}"
            )

            setup_text = (
                "COMPLETE"
                if result.setup_complete is True
                else "INCOMPLETE"
                if result.setup_complete is False
                else "UNKNOWN"
            )

            self.frp_setup_label.setText(
                f"Setup Wizard: {setup_text}"
            )

            provisioned_text = (
                "YES"
                if result.device_provisioned is True
                else "NO"
                if result.device_provisioned is False
                else "UNKNOWN"
            )

            self.frp_provisioned_label.setText(
                f"Device Provisioned: {provisioned_text}"
            )

            self.frp_indicator_label.setText(
                "FRP Provisioned Indicator: "
                f"{result.frp_provisioned}"
            )

            self.frp_bootloader_label.setText(
                f"Bootloader: {result.bootloader_locked}"
            )

            self.frp_verified_boot_label.setText(
                f"Verified Boot: {result.verified_boot_state}"
            )

            self.frp_message_label.setText(
                f"Catatan: {result.message}"
            )

            # Simpan hasil verifikasi terakhir dan gerbang (gate) tombol
            # reboot recovery/bootloader berdasarkan hasil ini. Default
            # aman: kalau owner_verification_required True, tombol lanjutan
            # dikunci sampai ada verifikasi ulang yang mengizinkan.
            self._last_frp_verification = result
            self.frp_recovery_button.setEnabled(
                not result.owner_verification_required
            )
            self.frp_bootloader_button.setEnabled(
                not result.owner_verification_required
            )

        except FRPVerificationError as exc:
            self.frp_status_label.setText(
                "FRP Status: ERROR"
            )
            self.frp_owner_label.setText(
                "Owner Verification: UNKNOWN"
            )
            self.frp_message_label.setText(str(exc))
            # Status tak diketahui -> anggap verifikasi belum aman,
            # kunci tombol lanjutan sampai berhasil dibaca ulang.
            self._last_frp_verification = None
            self.frp_recovery_button.setEnabled(False)
            self.frp_bootloader_button.setEnabled(False)

        except Exception as exc:
            logger.exception(
                "FRP verification UI failed"
            )
            self.frp_status_label.setText(
                "FRP Status: ERROR"
            )
            self.frp_owner_label.setText(
                "Owner Verification: UNKNOWN"
            )
            self.frp_message_label.setText(
                f"Gagal melakukan verifikasi: {exc}"
            )
            self._last_frp_verification = None
            self.frp_recovery_button.setEnabled(False)
            self.frp_bootloader_button.setEnabled(False)

        finally:
            self.frp_refresh_button.setEnabled(True)
            self.frp_service_refresh_button.setEnabled(True)

    def refresh_frp_service_state(self):
        if not self.current_serial:
            self.frp_service_state_label.setText("Service State: Tidak ada device")
            self.frp_fastboot_label.setText("Fastboot: -")
            self.frp_service_message_label.setText(
                "Hubungkan dan authorize device melalui ADB terlebih dahulu."
            )
            self.frp_recovery_button.setEnabled(False)
            self.frp_bootloader_button.setEnabled(False)
            self.frp_verify_button.setEnabled(False)
            return

        serial = self.current_serial
        self.frp_service_state_label.setText("Service State: Memeriksa...")
        self.frp_fastboot_label.setText("Fastboot: Memeriksa...")
        self.frp_service_message_label.setText(
            "Menjalankan deteksi FRP service nyata..."
        )
        self.frp_operation_message_label.setText("")
        self.frp_refresh_button.setEnabled(False)
        self.frp_service_refresh_button.setEnabled(False)
        self.frp_recovery_button.setEnabled(False)
        self.frp_bootloader_button.setEnabled(False)
        self.frp_verify_button.setEnabled(False)

        if getattr(self, "_frp_service_worker", None) and self._frp_service_worker.isRunning():
            return

        self._frp_service_worker = AsyncWorker(
            lambda: detect_frp_service_state(serial),
            self,
        )
        self._frp_service_worker.succeeded.connect(
            self._on_frp_service_state_ready
        )
        self._frp_service_worker.failed.connect(
            self._on_frp_service_state_error
        )
        self._frp_service_worker.start()

    def _on_frp_service_state_ready(self, state):
        self.frp_service_state_label.setText(
            f"Service State: {state.adb_state}"
        )
        self.frp_fastboot_label.setText(
            "Fastboot: Connected" if state.fastboot_connected else "Fastboot: Not connected"
        )
        self.frp_service_message_label.setText(state.message)
        self.frp_brand_label.setText(f"Brand/Family: {state.brand_group}")
        self.frp_model_label.setText(
            f"Model: {state.device_properties.get('model', 'Unknown')}"
        )
        self.frp_guidance_label.setText(
            "Workflow Guidance: " + " ".join(state.workflow_guidance)
        )
        self.frp_operation_message_label.setText(
            "Supported: " + ", ".join(state.supported_operations)
            if state.supported_operations
            else "Supported: none"
        )

        if state.authorized and not state.owner_auth_required:
            self.frp_recovery_button.setEnabled(True)
            self.frp_bootloader_button.setEnabled(True)
            self.frp_verify_button.setEnabled(True)
        else:
            self.frp_recovery_button.setEnabled(False)
            self.frp_bootloader_button.setEnabled(False)
            self.frp_verify_button.setEnabled(state.authorized)

        if state.fastboot_vars:
            vars_preview = []
            for key in [
                "version-bootloader",
                "product",
                "model",
                "secure",
                "unlocked",
            ]:
                if key in state.fastboot_vars:
                    vars_preview.append(f"{key}={state.fastboot_vars[key]}")
            self.frp_fastboot_info_label.setText(
                ", ".join(vars_preview) if vars_preview else "Fastboot vars available"
            )
        else:
            self.frp_fastboot_info_label.setText("Fastboot vars: -")

        if state.owner_auth_required:
            self.frp_operation_message_label.setText(
                "REQUIRES OWNER/OEM AUTHORIZATION"
            )

        self.frp_refresh_button.setEnabled(True)
        self.frp_service_refresh_button.setEnabled(True)

    def _on_frp_service_state_error(self, message: str):
        self.frp_service_state_label.setText("Service State: ERROR")
        self.frp_service_message_label.setText(message)
        self.frp_operation_message_label.setText("REQUIRES OWNER/OEM AUTHORIZATION")
        self.frp_recovery_button.setEnabled(False)
        self.frp_bootloader_button.setEnabled(False)
        self.frp_verify_button.setEnabled(False)
        self.frp_refresh_button.setEnabled(True)
        self.frp_service_refresh_button.setEnabled(True)

    def reboot_to_recovery(self):
        if not self.current_serial:
            return

        self.frp_operation_message_label.setText("Executing reboot to recovery...")
        self.frp_recovery_button.setEnabled(False)
        self.frp_bootloader_button.setEnabled(False)
        self.frp_verify_button.setEnabled(False)

        worker = AsyncWorker(
            lambda: execute_recovery_reboot(self.current_serial),
            self,
        )
        worker.succeeded.connect(
            lambda result: self._on_frp_action_complete(
                result,
                "Rebooting to recovery. Reconnect after device restarts."
            )
        )
        worker.failed.connect(self._on_frp_action_error)
        worker.start()

    def reboot_to_bootloader(self):
        if not self.current_serial:
            return

        self.frp_operation_message_label.setText("Executing reboot to bootloader...")
        self.frp_recovery_button.setEnabled(False)
        self.frp_bootloader_button.setEnabled(False)
        self.frp_verify_button.setEnabled(False)

        worker = AsyncWorker(
            lambda: execute_bootloader_reboot(self.current_serial),
            self,
        )
        worker.succeeded.connect(
            lambda result: self._on_frp_action_complete(
                result,
                "Rebooting to bootloader. Reconnect after device restarts."
            )
        )
        worker.failed.connect(self._on_frp_action_error)
        worker.start()

    def verify_frp_result_action(self):
        if not self.current_serial:
            return

        self.frp_operation_message_label.setText("Verifying FRP result...")
        self.frp_verify_button.setEnabled(False)
        self.frp_recovery_button.setEnabled(False)
        self.frp_bootloader_button.setEnabled(False)

        worker = AsyncWorker(
            lambda: verify_frp_result(self.current_serial),
            self,
        )
        worker.succeeded.connect(self._on_frp_verify_ready)
        worker.failed.connect(self._on_frp_action_error)
        worker.start()

    def _on_frp_verify_ready(self, result):
        self.frp_operation_message_label.setText(
            f"Result verified: {result.frp_status}. Owner verification required: {result.owner_verification_required}"
        )
        self._last_frp_verification = result
        self.frp_verify_button.setEnabled(True)
        self.frp_recovery_button.setEnabled(
            not result.owner_verification_required
        )
        self.frp_bootloader_button.setEnabled(
            not result.owner_verification_required
        )

    def _reboot_action_buttons_allowed(self) -> bool:
        """Tombol reboot recovery/bootloader hanya boleh aktif kalau hasil
        verifikasi FRP terakhir yang tersimpan memang tidak mewajibkan
        verifikasi kepemilikan. Default aman (False) kalau belum pernah
        ada hasil verifikasi yang valid."""
        return (
            self._last_frp_verification is not None
            and not self._last_frp_verification.owner_verification_required
        )

    def _on_frp_action_complete(self, command_output: str, message: str):
        self.frp_operation_message_label.setText(
            f"Operation complete. {message}"
        )
        self.frp_verify_button.setEnabled(True)
        allowed = self._reboot_action_buttons_allowed()
        self.frp_recovery_button.setEnabled(allowed)
        self.frp_bootloader_button.setEnabled(allowed)

    def _on_frp_action_error(self, message: str):
        self.frp_operation_message_label.setText(
            f"Action failed: {message}"
        )
        self.frp_verify_button.setEnabled(True)
        allowed = self._reboot_action_buttons_allowed()
        self.frp_recovery_button.setEnabled(allowed)
        self.frp_bootloader_button.setEnabled(allowed)

    def _set_locked_recovery_buttons_enabled(self, enabled: bool):
        self.locked_recovery_button.setEnabled(enabled)
        self.locked_bootloader_button.setEnabled(enabled)
        self.locked_verify_button.setEnabled(enabled)

    def _apply_locked_state_action_enablement(self):
        if not self._current_locked_state:
            return

        self.locked_recovery_button.setEnabled(
            "reboot_recovery" in self._current_locked_state.supported_actions
        )
        self.locked_bootloader_button.setEnabled(
            "reboot_bootloader" in self._current_locked_state.supported_actions
        )
        self.locked_verify_button.setEnabled(
            "verify_result" in self._current_locked_state.supported_actions
        )

    def refresh_locked_device_state(self):
        if not self.current_serial:
            self._current_locked_state = None
            self.locked_state_label.setText("Locked Recovery State: Tidak ada device")
            self.locked_identity_label.setText("Device Identity: -")
            self.locked_mode_label.setText("Mode: -")
            self.locked_options_label.setText("Recovery Options: -")
            self.locked_supported_label.setText("Supported Actions: -")
            self.locked_confirm_label.setText("Confirmation: -")
            self.locked_action_message_label.setText("")
            self.locked_confirm_button.setEnabled(False)
            self._set_locked_recovery_buttons_enabled(False)
            return

        self.locked_state_label.setText("Locked Recovery State: Memeriksa...")
        self.locked_identity_label.setText("Device Identity: -")
        self.locked_mode_label.setText("Mode: -")
        self.locked_options_label.setText("Recovery Options: -")
        self.locked_supported_label.setText("Supported Actions: -")
        self.locked_confirm_label.setText("Confirmation: -")
        self.locked_action_message_label.setText("Mendeteksi kondisi locked device recovery...")
        self.locked_confirm_button.setEnabled(False)
        self._set_locked_recovery_buttons_enabled(False)

        if getattr(self, "_locked_state_worker", None) and self._locked_state_worker.isRunning():
            return

        serial = self.current_serial
        self._locked_state_worker = AsyncWorker(
            lambda: detect_locked_device_recovery_state(serial),
            self,
        )
        self._locked_state_worker.succeeded.connect(
            self._on_locked_device_state_ready
        )
        self._locked_state_worker.failed.connect(
            self._on_locked_device_state_error
        )
        self._locked_state_worker.start()

    def _on_locked_device_state_ready(self, state: LockedDeviceRecoveryState):
        self._current_locked_state = state
        self.locked_state_label.setText(
            f"Locked Recovery State: {state.adb_state}"
        )
        identity_items = [
            f"{key}={value}" for key, value in state.device_identity.items()
            if value and value != "Unknown"
        ]
        self.locked_identity_label.setText(
            "Device Identity: " + ", ".join(identity_items)
            if identity_items else "Device Identity: Unknown"
        )
        self.locked_mode_label.setText(f"Mode: {state.device_mode}")
        self.locked_options_label.setText(
            "Recovery Options: " + " \n".join(state.recovery_options)
            if state.recovery_options else "Recovery Options: none"
        )
        supported_text = (
            ", ".join(state.supported_actions)
            if state.supported_actions else "none"
        )
        self.locked_supported_label.setText(
            f"Supported Actions: {supported_text}"
        )
        self.locked_tools_label.setText(
            "Recommended Tools: " + ", ".join(state.recommended_tools)
            if state.recommended_tools else "Recommended Tools: none"
        )
        self.locked_confirm_label.setText(
            "Confirmation: required"
            if state.confirmation_required else "Confirmation: not required"
        )
        self.locked_action_message_label.setText(state.message)

        self.locked_confirm_button.setEnabled(state.confirmation_required)
        if not state.confirmation_required:
            self._apply_locked_state_action_enablement()

    def _on_locked_device_state_error(self, message: str):
        self._current_locked_state = None
        self.locked_state_label.setText("Locked Recovery State: ERROR")
        self.locked_identity_label.setText("Device Identity: -")
        self.locked_mode_label.setText("Mode: -")
        self.locked_options_label.setText("Recovery Options: -")
        self.locked_supported_label.setText("Supported Actions: -")
        self.locked_confirm_label.setText("Confirmation: -")
        self.locked_action_message_label.setText(
            f"Gagal mendeteksi locked device recovery: {message}"
        )
        self.locked_confirm_button.setEnabled(False)
        self._set_locked_recovery_buttons_enabled(False)

    def confirm_recovery_action(self):
        if not self._current_locked_state:
            return

        if not self._current_locked_state.supported_actions:
            self.locked_action_message_label.setText(
                "Tidak ada recovery action yang didukung untuk kondisi ini."
            )
            return

        if not self._current_locked_state.confirmation_required:
            self.locked_action_message_label.setText(
                "Tidak diperlukan konfirmasi. Menjalankan aksi yang tersedia."
            )
            self._apply_locked_state_action_enablement()
            return

        answer = QMessageBox.question(
            self,
            "Konfirmasi Recovery",
            "Tindakan ini berisiko dan hanya boleh dilakukan jika otorisasi owner/OEM sudah tersedia. Lanjutkan?",
            QMessageBox.Yes | QMessageBox.No,
        )

        if answer != QMessageBox.Yes:
            self.locked_action_message_label.setText("Konfirmasi dibatalkan.")
            return

        self.locked_confirm_label.setText("Confirmation: technician confirmed")
        self.locked_action_message_label.setText(
            "Teknisi telah mengonfirmasi. Jalankan salah satu supported action dengan hati-hati."
        )
        self._apply_locked_state_action_enablement()
        self.locked_confirm_button.setEnabled(False)

    def reboot_locked_recovery(self):
        if not self.current_serial:
            return

        self.locked_action_message_label.setText(
            "Executing locked device reboot to recovery..."
        )
        self._set_locked_recovery_buttons_enabled(False)

        worker = AsyncWorker(
            lambda: execute_recovery_reboot(self.current_serial),
            self,
        )
        worker.succeeded.connect(
            lambda result: self._on_locked_action_complete(
                result,
                "Rebooting to recovery. Reconnect after device restarts."
            )
        )
        worker.failed.connect(self._on_locked_action_error)
        worker.start()

    def reboot_locked_bootloader(self):
        if not self.current_serial:
            return

        self.locked_action_message_label.setText(
            "Executing locked device reboot to bootloader..."
        )
        self._set_locked_recovery_buttons_enabled(False)

        worker = AsyncWorker(
            lambda: execute_bootloader_reboot(self.current_serial),
            self,
        )
        worker.succeeded.connect(
            lambda result: self._on_locked_action_complete(
                result,
                "Rebooting to bootloader. Reconnect after device restarts."
            )
        )
        worker.failed.connect(self._on_locked_action_error)
        worker.start()

    def verify_locked_result(self):
        if not self.current_serial:
            return

        self.locked_action_message_label.setText("Verifying locked device result...")
        self._set_locked_recovery_buttons_enabled(False)

        worker = AsyncWorker(
            lambda: verify_frp_result(self.current_serial),
            self,
        )
        worker.succeeded.connect(self._on_locked_verify_ready)
        worker.failed.connect(self._on_locked_action_error)
        worker.start()

    def _on_locked_verify_ready(self, result):
        self.locked_action_message_label.setText(
            f"Verify result: {result.frp_status}. Owner verification required: {result.owner_verification_required}"
        )
        self._apply_locked_state_action_enablement()

    def _on_locked_action_complete(self, command_output: str, message: str):
        self.locked_action_message_label.setText(f"Operation complete. {message}")
        self._apply_locked_state_action_enablement()

    def _on_locked_action_error(self, message: str):
        self.locked_action_message_label.setText(f"Action failed: {message}")
        self._apply_locked_state_action_enablement()

    def refresh_recovery_assessment(self):
        if not self.current_serial:
            self.recovery_status.setText("Tidak ada device terhubung.")
            self.recovery_recommended.setText("")
            self.recovery_warning.setText("")
            self.recovery_plan_text.setPlainText(
                "\n".join(
                    f"- {action}"
                    for action in plan_locked_device(adb_state="not_detected").actions
                )
            )
            return

        state = self.devices.get(self.current_serial, "not_detected")

        # Bagian logic lokal (tidak panggil ADB) - tetap sinkron karena cepat.
        access_report = diagnose_access_issue({"adb_state": state})
        plan = plan_locked_device(adb_state=state)

        lines = [f"[{plan.title}]"]
        lines.extend(f"- {action}" for action in plan.actions)
        if getattr(access_report, "findings", None):
            lines.append("")
            lines.append("Findings tambahan:")
            for finding in access_report.findings:
                lines.append(f"- [{finding.severity.upper()}] {finding.title}: {finding.action}")

        self.recovery_plan_text.setPlainText("\n".join(lines))

        # Bagian yang panggil ADB (assess_access) - jalankan di background.
        if getattr(self, "_recovery_worker", None) and self._recovery_worker.isRunning():
            return

        self.recovery_status.setText("⏳ Menilai akses device...")
        serial = self.current_serial

        self._recovery_worker = AsyncWorker(lambda: assess_access(serial), self)
        self._recovery_worker.succeeded.connect(self._on_recovery_assessment_ready)
        self._recovery_worker.failed.connect(self._on_recovery_assessment_error)
        self._recovery_worker.start()

    def _on_recovery_assessment_ready(self, assessment):
        self.recovery_status.setText(f"State ADB: {assessment.adb_state}")
        self.recovery_recommended.setText(f"Rekomendasi: {assessment.recommended_path}")
        self.recovery_warning.setText(f"Catatan: {assessment.warning}")

    def _on_recovery_assessment_error(self, message: str):
        self.recovery_status.setText("Gagal menilai akses.")
        self.recovery_recommended.setText(message)
        self.recovery_warning.setText("")

    # ------------------------------------------------------------------
    # Factory Reset Assistant Page
    # ------------------------------------------------------------------

    def create_factory_reset_page(self):
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)

        model = "Unknown device"
        self.factory_reset_panel = FactoryResetAssistantPanel(model=model)
        layout.addWidget(self.factory_reset_panel)

        return wrapper

    # ------------------------------------------------------------------
    # Settings Page
    # ------------------------------------------------------------------

    def create_settings_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(14)

        title = QLabel("Settings")
        title.setObjectName("contentTitle")
        desc = QLabel("Preferensi aplikasi Nexa Service Tool.")
        desc.setObjectName("muted")
        layout.addWidget(title)
        layout.addWidget(desc)

        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(22, 20, 22, 20)
        card_layout.setSpacing(10)

        refresh_label = QLabel("Auto-refresh device list (ms)")
        refresh_label.setObjectName("muted")
        self.settings_refresh_ms = QLineEdit()
        card_layout.addWidget(refresh_label)
        card_layout.addWidget(self.settings_refresh_ms)

        loglevel_label = QLabel("Log level")
        loglevel_label.setObjectName("muted")
        self.settings_log_level = QComboBox()
        self.settings_log_level.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        card_layout.addWidget(loglevel_label)
        card_layout.addWidget(self.settings_log_level)

        self.settings_confirm_dangerous = QPushButton("Konfirmasi aksi berbahaya: ON")
        self.settings_confirm_dangerous.setCheckable(True)
        self.settings_confirm_dangerous.clicked.connect(self._toggle_confirm_dangerous_label)
        card_layout.addWidget(self.settings_confirm_dangerous)

        self.settings_mask_identifiers = QPushButton("Sembunyikan IMEI/Serial sensitif: ON")
        self.settings_mask_identifiers.setCheckable(True)
        self.settings_mask_identifiers.clicked.connect(self._toggle_mask_identifiers_label)
        card_layout.addWidget(self.settings_mask_identifiers)

        layout.addWidget(card)

        self.settings_save_button = QPushButton("Simpan Settings")
        self.settings_save_button.setObjectName("actionPrimary")
        self.settings_save_button.clicked.connect(self.save_settings_form)
        layout.addWidget(self.settings_save_button)
        layout.addStretch()

        return page

    def _toggle_confirm_dangerous_label(self, checked: bool):
        self.settings_confirm_dangerous.setText(
            f"Konfirmasi aksi berbahaya: {'ON' if checked else 'OFF'}"
        )

    def _toggle_mask_identifiers_label(self, checked: bool):
        self.settings_mask_identifiers.setText(
            f"Sembunyikan IMEI/Serial sensitif: {'ON' if checked else 'OFF'}"
        )

    def load_settings_form(self):
        self.settings_refresh_ms.setText(str(self.settings.get("auto_refresh_ms", 1500)))

        log_level = self.settings.get("log_level", "INFO")
        idx = self.settings_log_level.findText(log_level)
        self.settings_log_level.setCurrentIndex(idx if idx >= 0 else 1)

        confirm = bool(self.settings.get("confirm_dangerous_actions", True))
        self.settings_confirm_dangerous.setChecked(confirm)
        self._toggle_confirm_dangerous_label(confirm)

        mask = bool(self.settings.get("mask_sensitive_identifiers", True))
        self.settings_mask_identifiers.setChecked(mask)
        self._toggle_mask_identifiers_label(mask)

    def save_settings_form(self):
        try:
            refresh_ms = int(self.settings_refresh_ms.text().strip())
            if refresh_ms < 250:
                raise ValueError("Auto-refresh minimal 250ms.")
        except ValueError as exc:
            QMessageBox.warning(self, "Nilai Tidak Valid", str(exc) or "Auto-refresh harus berupa angka.")
            return

        self.settings.update({
            "auto_refresh_ms": refresh_ms,
            "log_level": self.settings_log_level.currentText(),
            "confirm_dangerous_actions": self.settings_confirm_dangerous.isChecked(),
            "mask_sensitive_identifiers": self.settings_mask_identifiers.isChecked(),
        })

        self.timer.setInterval(refresh_ms)
        logger.info("Settings disimpan: refresh=%sms, log_level=%s", refresh_ms, self.settings_log_level.currentText())
        QMessageBox.information(self, "Settings Disimpan", "Preferensi berhasil disimpan.")

    # ------------------------------------------------------------------
    # Automation / Macro Runner Page
    # ------------------------------------------------------------------

    def create_automation_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(14)

        title = QLabel("Automation")
        title.setObjectName("contentTitle")

        desc = QLabel(
            "Susun langkah-langkah (macro) dan jalankan berurutan pada device aktif. "
            "Berguna untuk pekerjaan servis yang berulang."
        )
        desc.setObjectName("muted")
        desc.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(desc)

        builder_row = QHBoxLayout()
        builder_row.setSpacing(8)

        self.automation_action_combo = QComboBox()
        self.automation_action_combo.setObjectName("deviceSelector")
        self.automation_action_combo.addItems(sorted(ACTIONS.keys()))

        self.automation_param_input = QLineEdit()
        self.automation_param_input.setPlaceholderText(
            "Parameter (contoh: package=com.whatsapp atau cmd=pm list packages)"
        )

        self.automation_add_step_button = QPushButton("Tambah Step")
        self.automation_add_step_button.setObjectName("action")
        self.automation_add_step_button.clicked.connect(self.add_macro_step)

        builder_row.addWidget(self.automation_action_combo)
        builder_row.addWidget(self.automation_param_input, 1)
        builder_row.addWidget(self.automation_add_step_button)

        layout.addLayout(builder_row)

        self.automation_steps_list = QListWidget()
        self.automation_steps_list.setMaximumHeight(150)
        layout.addWidget(self.automation_steps_list)

        step_btn_row = QHBoxLayout()
        step_btn_row.setSpacing(8)

        self.automation_remove_step_button = QPushButton("Hapus Step Terpilih")
        self.automation_remove_step_button.setObjectName("action")
        self.automation_remove_step_button.clicked.connect(self.remove_macro_step)

        self.automation_clear_steps_button = QPushButton("Kosongkan")
        self.automation_clear_steps_button.setObjectName("action")
        self.automation_clear_steps_button.clicked.connect(self.clear_macro_steps)

        step_btn_row.addWidget(self.automation_remove_step_button)
        step_btn_row.addWidget(self.automation_clear_steps_button)
        step_btn_row.addStretch()

        layout.addLayout(step_btn_row)

        self.automation_run_button = QPushButton("Jalankan Macro pada Device Aktif")
        self.automation_run_button.setObjectName("actionPrimary")
        self.automation_run_button.clicked.connect(self.run_macro_now)
        layout.addWidget(self.automation_run_button)

        self.automation_log = QPlainTextEdit()
        self.automation_log.setObjectName("logConsole")
        self.automation_log.setReadOnly(True)
        layout.addWidget(self.automation_log)

        return page

    @staticmethod
    def _parse_macro_params(text: str) -> dict:
        """Parse 'key=value, key2=value2' jadi dict sederhana."""
        params = {}
        text = text.strip()

        if not text:
            return params

        for pair in text.split(","):
            if "=" not in pair:
                continue
            key, value = pair.split("=", 1)
            params[key.strip()] = value.strip()

        return params

    def add_macro_step(self):
        action = self.automation_action_combo.currentText()
        params = self._parse_macro_params(self.automation_param_input.text())

        step = MacroStep(action=action, params=params, label=f"{action}({params})")
        self._macro_steps.append(step)

        self.automation_steps_list.addItem(f"{len(self._macro_steps)}. {step.label}")
        self.automation_param_input.clear()

    def remove_macro_step(self):
        row = self.automation_steps_list.currentRow()

        if row < 0 or row >= len(self._macro_steps):
            return

        del self._macro_steps[row]
        self._rebuild_macro_steps_list()

    def clear_macro_steps(self):
        self._macro_steps.clear()
        self._rebuild_macro_steps_list()

    def _rebuild_macro_steps_list(self):
        self.automation_steps_list.clear()

        for i, step in enumerate(self._macro_steps, start=1):
            self.automation_steps_list.addItem(f"{i}. {step.label}")

    def run_macro_now(self):
        if not self.current_device:
            QMessageBox.warning(self, "Tidak ada device", "Hubungkan device terlebih dahulu.")
            return

        if not self._macro_steps:
            QMessageBox.warning(self, "Macro Kosong", "Tambahkan minimal 1 step dulu.")
            return

        reply = QMessageBox.question(
            self, "Konfirmasi Jalankan Macro",
            f"Jalankan {len(self._macro_steps)} step pada device "
            f"{self.current_device.serial}?\n\n"
            f"Beberapa aksi (uninstall, delete file, reboot) tidak bisa dibatalkan.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )

        if reply != QMessageBox.Yes:
            return

        if getattr(self, "_automation_worker", None) and self._automation_worker.isRunning():
            QMessageBox.information(self, "Sedang Berjalan", "Macro lain sedang berjalan.")
            return

        self.automation_log.clear()
        self.automation_log.appendPlainText(
            f"Menjalankan {len(self._macro_steps)} step pada {self.current_device.serial}..."
        )
        self.automation_run_button.setEnabled(False)

        serial = self.current_device.serial
        macro = Macro(name="Manual Macro", steps=list(self._macro_steps))

        def task():
            return automation.run_macro(serial, macro, stop_on_error=False)

        self._automation_worker = AsyncWorker(task, self)
        self._automation_worker.succeeded.connect(self._on_macro_ready)
        self._automation_worker.failed.connect(self._on_macro_error)
        self._automation_worker.start()

    def _on_macro_ready(self, results: list):
        for i, line in enumerate(results, start=1):
            self.automation_log.appendPlainText(f"[{i}] {line}")

        self.automation_log.appendPlainText("--- Macro selesai ---")
        self.automation_run_button.setEnabled(True)

    def _on_macro_error(self, message: str):
        self.automation_log.appendPlainText(f"ERROR: {message}")
        self.automation_run_button.setEnabled(True)

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

            self.dashboard_status.setText("✅ Device connected")
            self.dashboard_info.setText(
                f"{device.manufacturer} {device.model}\n"
                f"Android {device.android_version}"
            )

            self.device_status.setText("✅ Connected via ADB")
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

        self.dashboard_status.setText("⚠ No device connected")
        self.dashboard_info.setText(message)

        self.device_status.setText("⚠ No device connected")
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
    configure_logging()
    logger.info("Launching Nexa Service Tool")

    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())
