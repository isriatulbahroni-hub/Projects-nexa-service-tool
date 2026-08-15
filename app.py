import platform
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    import psutil
except ImportError:  # pragma: no cover - optional dependency
    psutil = None

from PySide6.QtCore import QTimer, Qt, QPropertyAnimation, QEasingCurve, QUrl
from PySide6.QtGui import QPixmap, QColor, QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
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

from core.adb import (
    ADBError,
    get_devices_with_state,
    reboot_device,
    run_adb,
    run_adb_binary,
    _resolve_adb_path,
)
from core.config import ADB_PATH, PROJECT_ROOT
from core.device import get_device_info
from core.diagnostics import (
    compute_health_score,
    get_diagnostics,
    health_score_label,
)
from core.database import (
    get_history,
    save_service_record,
    log_action as log_action_db,
    get_action_log,
)
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
from core.backup import backup_device, restore_device, cleanup_old_backups, is_zip_password_protected
from core.security_check import run_security_check
from core.firmware import (
    get_build_info,
    list_fastboot_devices,
    flash_partition,
    reboot_from_fastboot,
    COMMON_PARTITIONS,
    CRITICAL_PARTITIONS,
    FastbootError,
    _resolve_fastboot_path,
)
from core.network_info import get_network_info
from core.hardware_test import run_hardware_test
from core.task_runner import run_in_thread
from core.app_logging import configure_logging, get_logger
from core.settings import get_settings_store
from core.async_worker import AsyncWorker
from core import automation
from core.automation import Macro, MacroStep, ACTIONS, MacroError
from core.service_cases import (
    STATUSES as CASE_STATUSES,
    PAYMENT_STATUSES as CASE_PAYMENT_STATUSES,
    create_case,
    list_cases,
    get_case,
    update_status as update_case_status,
    add_note as add_case_note,
    get_timeline as get_case_timeline,
    update_payment as update_case_payment_db,
    add_photo as add_case_photo_db,
    get_photos as get_case_photos_db,
    delete_photo as delete_case_photo_db,
)
from core.invoice import generate_case_invoice, generate_case_label
from core.whatsapp import build_whatsapp_link, build_case_status_message
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

#sidebarRail {
    background: #0e0f13;
    border-right: 1px solid #22262f;
}

#sidebarToggle {
    background: #1a1d24;
    color: #e8eaed;
    border: 1px solid #2b2f3a;
    border-radius: 8px;
    font-size: 15px;
}

#sidebarToggle:hover {
    background: #ff5a1f;
    color: white;
    border-color: #ff5a1f;
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
        self._info_loaded_for: str | None = None
        self._current_locked_state: LockedDeviceRecoveryState | None = None
        self.last_diag = None
        self.last_score = None
        self.last_recommendations: list[str] = []

        self.logcat_streamer: LogcatStreamer | None = None
        self.screen_mirror: ScreenMirror | None = None
        self.file_explorer_path = "/sdcard"

        # Pakai singleton yang sama dengan core.adb/core.firmware, supaya
        # perubahan adb_path_override/fastboot_path_override dari halaman
        # Settings langsung kepakai tanpa perlu restart aplikasi.
        self.settings = get_settings_store()
        self._macro_steps: list[MacroStep] = []
        self.current_case_id: int | None = None
        self._hardware_task_refs = None  # keeps (thread, worker) alive while running

        self.setStyleSheet(STYLESHEET)

        self.build_ui()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_device_list)
        self.timer.start(int(self.settings.get("auto_refresh_ms", 1500)))

        self._app_start_time = time.time()
        self.sysinfo_timer = QTimer(self)
        self.sysinfo_timer.timeout.connect(self._update_system_info)
        self.sysinfo_timer.start(2000)
        self._update_system_info()

        self.refresh_device_list()
        logger.info("Nexa Service Tool started")

        # First-run check: kalau ADB/Fastboot tidak bisa auto-detect,
        # arahkan user ke Settings untuk isi path manual - daripada
        # dibiarkan bingung karena semua fitur device diam-diam gagal
        # tanpa penjelasan yang jelas kenapa.
        QTimer.singleShot(300, self._check_first_run_tools)

    def _check_first_run_tools(self):
        adb_ok = Path(_resolve_adb_path()).exists()
        fastboot_ok = Path(_resolve_fastboot_path()).exists()

        if adb_ok and fastboot_ok:
            return

        missing = []
        if not adb_ok:
            missing.append("ADB")
        if not fastboot_ok:
            missing.append("Fastboot")

        reply = QMessageBox.warning(
            self, "Setup Diperlukan",
            f"{' dan '.join(missing)} tidak ditemukan secara otomatis di komputer ini.\n\n"
            "Sebagian besar fitur (deteksi device, diagnostics, flash, dll) "
            "tidak akan berfungsi sampai ini diatur.\n\n"
            "Buka halaman Settings sekarang untuk atur path manual?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
        )

        if reply == QMessageBox.Yes:
            self.switch_page("settings")

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    SIDEBAR_WIDTH = 230
    SIDEBAR_RAIL_WIDTH = 44

    def build_ui(self):
        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Rail tipis & selalu terlihat berisi tombol hamburger, supaya
        # sidebar tetap bisa dimunculkan lagi walau lagi disembunyikan.
        rail = QFrame()
        rail.setObjectName("sidebarRail")
        rail.setFixedWidth(self.SIDEBAR_RAIL_WIDTH)
        rail_layout = QVBoxLayout(rail)
        rail_layout.setContentsMargins(6, 16, 6, 16)
        rail_layout.setSpacing(0)

        self.sidebar_toggle_button = QPushButton("☰")
        self.sidebar_toggle_button.setObjectName("sidebarToggle")
        self.sidebar_toggle_button.setFixedSize(32, 32)
        self.sidebar_toggle_button.setToolTip("Tampilkan/sembunyikan menu")
        self.sidebar_toggle_button.clicked.connect(self.toggle_sidebar)
        rail_layout.addWidget(self.sidebar_toggle_button)
        rail_layout.addStretch()

        root_layout.addWidget(rail)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        # minimumWidth 0 supaya lebarnya bisa dianimasikan sampai 0 saat
        # disembunyikan; maximumWidth dipakai sebagai "lebar target" normal.
        sidebar.setMinimumWidth(0)
        sidebar.setMaximumWidth(self.SIDEBAR_WIDTH)
        self.sidebar_frame = sidebar
        self._sidebar_collapsed = False

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

        # Semua label yang menampilkan info device/diagnostics/status
        # (objectName "value"/"status"/"muted") sebelumnya QLabel polos -
        # teksnya tidak bisa di-select/copy sama sekali, dan kursor tidak
        # berubah saat di-hover. Diaktifkan sekali di sini untuk SEMUA
        # label sekaligus (bukan satu-satu di ~67 tempat pembuatan label),
        # supaya teknisi bisa select+copy info seperti serial number,
        # IMEI, error message, dll untuk ditempel ke WhatsApp/nota/dsb.
        self._enable_text_selection_for_info_labels()

        self.switch_page("dashboard")

    def _enable_text_selection_for_info_labels(self):
        selectable_object_names = {"value", "status", "muted"}

        for label in self.findChildren(QLabel):
            if label.objectName() in selectable_object_names:
                label.setTextInteractionFlags(
                    Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
                )
                label.setCursor(Qt.IBeamCursor)

    def refresh_all_data(self):
        """Reload device list + semua data yang sudah pernah di-fetch
        (diagnostics/security/network/dashboard) sekaligus - semua sudah
        threaded di masing-masing fungsi, jadi aman dipanggil bersamaan
        tanpa nge-freeze UI."""
        self.refresh_device_list()

        if not self.current_device:
            QMessageBox.information(
                self, "Tidak Ada Device", "Hubungkan device dulu sebelum refresh."
            )
            return

        # Sebelumnya tombol ini tidak kasih tanda apapun kalau lagi
        # bekerja - user tidak tahu apakah klik-nya kepencet atau
        # prosesnya masih jalan. Sekarang tombol dinonaktifkan + labelnya
        # berubah selama proses berjalan, dan otomatis balik normal begitu
        # SEMUA sub-refresh (diagnostics/security/network/dashboard)
        # benar-benar selesai (dilacak lewat sinyal `finished` bawaan
        # QThread di masing-masing AsyncWorker, bukan asal timer/delay).
        self.dashboard_refresh_all_button.setEnabled(False)
        self.dashboard_refresh_all_button.setText("🔄 Memuat...")

        self.refresh_diagnostics()
        self.refresh_security_check()
        self.refresh_network_info()
        # Sebelumnya baris ini tidak ada - card FRP Status/Bootloader/
        # Battery/FRP Service/Device Connection di dashboard cuma keisi
        # sekali saat device baru konek, tidak pernah ke-refresh lagi
        # walau tombol "Refresh Semua" diklik. Sekarang ikut di-refresh.
        self.refresh_dashboard_details()

        workers = [
            getattr(self, "_diag_worker", None),
            getattr(self, "_security_worker", None),
            getattr(self, "_network_worker", None),
            getattr(self, "_dashboard_worker", None),
        ]
        workers = [w for w in workers if w is not None]

        if not workers:
            # Semua sub-refresh ternyata di-skip (mis. worker sebelumnya
            # masih jalan) - jangan biarkan tombol nyangkut "Memuat...".
            self.dashboard_refresh_all_button.setEnabled(True)
            self.dashboard_refresh_all_button.setText("🔄 Refresh Semua")
            return

        self._refresh_all_pending = len(workers)

        def _mark_one_done(_result=None):
            self._refresh_all_pending -= 1
            if self._refresh_all_pending <= 0:
                self.dashboard_refresh_all_button.setEnabled(True)
                self.dashboard_refresh_all_button.setText("🔄 Refresh Semua")
                self._dash_log("Refresh Semua selesai.")

        for worker in workers:
            # Kalau worker-nya kebetulan SUDAH selesai duluan sebelum
            # sempat kita hook (mis. worker lama yang direuse karena
            # refresh_dashboard_details() punya guard 'skip kalau masih
            # jalan'), sinyal finished-nya sudah lewat dan tidak akan
            # pernah terdeteksi kalau cuma connect - tombol bisa nyangkut
            # "Memuat..." selamanya. Makanya dicek isFinished() dulu.
            if worker.isFinished():
                _mark_one_done()
            else:
                worker.finished.connect(_mark_one_done)

    def toggle_sidebar(self):
        target_width = 0 if not self._sidebar_collapsed else self.SIDEBAR_WIDTH
        self._sidebar_collapsed = not self._sidebar_collapsed

        self._sidebar_anim = QPropertyAnimation(self.sidebar_frame, b"maximumWidth", self)
        self._sidebar_anim.setDuration(180)
        self._sidebar_anim.setStartValue(self.sidebar_frame.width())
        self._sidebar_anim.setEndValue(target_width)
        self._sidebar_anim.setEasingCurve(QEasingCurve.InOutCubic)
        self._sidebar_anim.start()

        self.sidebar_toggle_button.setText("☰" if self._sidebar_collapsed else "✕")

    def switch_page(self, key: str):
        for k, btn in self.nav_buttons.items():
            btn.setChecked(k == key)

        if key != "mirror" and self.screen_mirror and self.screen_mirror.is_running():
            self.stop_mirror()

        self.pages.setCurrentWidget(self.page_widgets[key])

        # BUG: seluruh QStackedWidget (semua halaman) dibungkus SATU
        # QScrollArea yang sama (self.content_scroll). Kalau user scroll ke
        # bawah di halaman yang panjang (mis. Dashboard) lalu pindah ke
        # halaman yang lebih pendek (mis. Security Check, Screen Mirror,
        # Firmware Flash), posisi scroll TIDAK ikut reset - jadi bagian
        # atas halaman baru itu ketutup/keluar dari viewport, kelihatan
        # seperti "ruang kosong besar" padahal cuma halamannya nyangkut di
        # posisi scroll halaman sebelumnya. Selalu reset ke atas setiap
        # ganti halaman. Pakai singleShot(0, ...) supaya reset-nya jalan
        # SETELAH Qt selesai menghitung ulang layout halaman baru -
        # kalau di-set langsung, kadang keburu ketimpa ulang oleh proses
        # resize internal QStackedWidget/QScrollArea.
        if hasattr(self, "content_scroll"):
            QTimer.singleShot(0, lambda: self.content_scroll.verticalScrollBar().setValue(0))

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
            # Bug: label case_use_current_device dibuat tapi textnya
            # tidak pernah di-set - teknisi tidak tahu device mana yang
            # bakal otomatis ke-attach ke case baru yang dibuat.
            self._update_case_device_hint()
        elif key == "recovery":
            self.refresh_recovery_assessment()
            self.refresh_locked_device_state()
        elif key == "settings":
            self.load_settings_form()

    # ------------------------------------------------------------------
    # Dashboard Page
    # ------------------------------------------------------------------

    def _page_header(self, title_text: str, desc_text: str) -> QVBoxLayout:
        """Header standar (judul besar + deskripsi abu-abu) dipakai di
        hampir semua halaman - disatukan di sini supaya konsisten dan
        tidak perlu diulang manual di tiap create_*_page()."""
        header = QVBoxLayout()
        title = QLabel(title_text)
        title.setObjectName("contentTitle")
        desc = QLabel(desc_text)
        desc.setObjectName("muted")
        desc.setWordWrap(True)
        header.addWidget(title)
        header.addWidget(desc)
        return header

    def _card_panel(
        self, title_text: str, refresh_handler=None, refresh_label: str = "🔄 Refresh"
    ) -> tuple[QFrame, QVBoxLayout]:
        """Bikin satu panel bergaya '#card' dengan judul (dan tombol
        refresh opsional di kanan judul) - dipakai konsisten di semua
        halaman supaya visualnya seragam dengan Dashboard, bukan cuma
        label/tombol polos langsung di atas background gelap."""
        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(22, 18, 22, 18)
        card_layout.setSpacing(10)

        if title_text:
            head_row = QHBoxLayout()
            head = QLabel(title_text)
            head.setObjectName("cardTitle")
            head_row.addWidget(head, 1)

            if refresh_handler is not None:
                refresh_btn = QPushButton(refresh_label)
                refresh_btn.setObjectName("action")
                refresh_btn.clicked.connect(refresh_handler)
                head_row.addWidget(refresh_btn)

            card_layout.addLayout(head_row)

        return card, card_layout

    def create_dashboard_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)

        title = QLabel("Dashboard")
        title.setObjectName("contentTitle")

        desc = QLabel("Overview perangkat, status FRP, dan koneksi service tool.")
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

        # ---------------------------------------------------------------
        # Baris 4 stat card: Device Status, FRP Status, Bootloader, Battery
        # ---------------------------------------------------------------
        stats_row = QHBoxLayout()
        stats_row.setSpacing(14)

        def make_stat_card(title_text: str):
            card = QFrame()
            card.setObjectName("card")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(18, 16, 18, 16)
            card_layout.setSpacing(4)

            label = QLabel(title_text)
            label.setObjectName("muted")

            value = QLabel("--")
            value.setObjectName("status")
            value.setStyleSheet("font-size:20px;")

            sub = QLabel("")
            sub.setObjectName("muted")
            sub.setWordWrap(True)

            card_layout.addWidget(label)
            card_layout.addWidget(value)
            card_layout.addWidget(sub)
            return card, value, sub

        device_card, self.dashboard_status, self.dashboard_info = make_stat_card("DEVICE STATUS")
        frp_card, self.dash_frp_value, self.dash_frp_sub = make_stat_card("FRP STATUS")
        boot_card, self.dash_boot_value, self.dash_boot_sub = make_stat_card("BOOTLOADER")
        batt_card, self.dash_batt_value, self.dash_batt_sub = make_stat_card("BATTERY")

        for card in (device_card, frp_card, boot_card, batt_card):
            stats_row.addWidget(card, 1)

        layout.addLayout(stats_row)

        # ---------------------------------------------------------------
        # Kolom kiri (Device Information, FRP Service, Quick Actions)
        # dan kolom kanan (Device Connection, System Information)
        # ---------------------------------------------------------------
        main_row = QHBoxLayout()
        main_row.setSpacing(16)

        left_col = QVBoxLayout()
        left_col.setSpacing(16)
        right_col = QVBoxLayout()
        right_col.setSpacing(16)

        def make_panel(title_text: str, with_refresh: bool = False) -> tuple[QFrame, QVBoxLayout]:
            card = QFrame()
            card.setObjectName("card")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(22, 18, 22, 18)
            card_layout.setSpacing(8)

            head_row = QHBoxLayout()
            head = QLabel(title_text)
            head.setObjectName("cardTitle")
            head_row.addWidget(head, 1)

            if with_refresh:
                refresh_btn = QPushButton("🔄 Refresh")
                refresh_btn.setObjectName("action")
                refresh_btn.setToolTip("Ambil ulang data ini dari device sekarang.")
                refresh_btn.clicked.connect(self.refresh_dashboard_details)
                head_row.addWidget(refresh_btn)

            card_layout.addLayout(head_row)
            return card, card_layout

        info_card, info_layout = make_panel("Device Information", with_refresh=True)
        self.dash_device_info = QLabel("Belum ada device terhubung.")
        self.dash_device_info.setObjectName("value")
        self.dash_device_info.setWordWrap(True)
        info_layout.addWidget(self.dash_device_info)
        left_col.addWidget(info_card)

        frp_service_card, frp_service_layout = make_panel("FRP Service", with_refresh=True)
        self.dash_frp_detail = QLabel("Belum ada data. Klik Refresh Semua setelah device terhubung.")
        self.dash_frp_detail.setObjectName("value")
        self.dash_frp_detail.setWordWrap(True)
        frp_service_layout.addWidget(self.dash_frp_detail)
        left_col.addWidget(frp_service_card)

        qa_card, qa_layout = make_panel("Quick Actions")
        qa_grid = QGridLayout()
        qa_grid.setSpacing(10)
        quick_actions = [
            ("🔄 Reboot to Recovery", self.dashboard_quick_reboot_recovery),
            ("🔧 Reboot to Bootloader", self.dashboard_quick_reboot_bootloader),
            ("🛡️ Verify FRP Result", self.dashboard_quick_verify_frp),
            ("⚙️ Hardware Diagnostic", lambda: self.switch_page("hardware")),
            ("☁️ Backup Data", lambda: self.switch_page("backup")),
            ("📷 Screenshot", self.dashboard_quick_screenshot),
            ("💾 Save Log", self.dashboard_quick_save_log),
            ("🖨️ Export Laporan PDF", lambda: self.switch_page("diagnostics")),
            ("📜 Activity Log", lambda: self.switch_page("history")),
        ]
        for i, (label_text, handler) in enumerate(quick_actions):
            btn = QPushButton(label_text)
            btn.setObjectName("action")
            btn.clicked.connect(handler)
            qa_grid.addWidget(btn, i // 3, i % 3)
        qa_layout.addLayout(qa_grid)
        left_col.addWidget(qa_card)

        conn_card, conn_layout = make_panel("Device Connection")
        self.dash_connection_detail = QLabel("Tidak ada device terhubung.")
        self.dash_connection_detail.setObjectName("value")
        self.dash_connection_detail.setWordWrap(True)
        conn_layout.addWidget(self.dash_connection_detail)
        right_col.addWidget(conn_card)

        sysinfo_card, sysinfo_layout = make_panel("System Information")

        def make_meter_row(label_text: str):
            row_layout = QHBoxLayout()
            lbl = QLabel(label_text)
            lbl.setObjectName("muted")
            lbl.setFixedWidth(46)
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(0)
            bar.setTextVisible(True)
            row_layout.addWidget(lbl)
            row_layout.addWidget(bar, 1)
            return row_layout, bar

        cpu_row, self.dash_cpu_bar = make_meter_row("CPU")
        ram_row, self.dash_ram_bar = make_meter_row("RAM")
        disk_row, self.dash_disk_bar = make_meter_row("DISK")
        sysinfo_layout.addLayout(cpu_row)
        sysinfo_layout.addLayout(ram_row)
        sysinfo_layout.addLayout(disk_row)

        self.dash_sysinfo_label = QLabel("")
        self.dash_sysinfo_label.setObjectName("value")
        self.dash_sysinfo_label.setWordWrap(True)
        sysinfo_layout.addWidget(self.dash_sysinfo_label)

        right_col.addWidget(sysinfo_card)
        right_col.addStretch()

        main_row.addLayout(left_col, 2)
        main_row.addLayout(right_col, 1)
        layout.addLayout(main_row)

        # ---------------------------------------------------------------
        # Quick Health Check (skor diagnostics ringkas, sudah ada sebelumnya)
        # ---------------------------------------------------------------
        score_card = QFrame()
        score_card.setObjectName("card")
        score_layout = QVBoxLayout(score_card)
        score_layout.setContentsMargins(22, 18, 22, 18)
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

        # ---------------------------------------------------------------
        # Activity log / output console
        # ---------------------------------------------------------------
        console_card = QFrame()
        console_card.setObjectName("card")
        console_layout = QVBoxLayout(console_card)
        console_layout.setContentsMargins(22, 18, 22, 18)
        console_layout.setSpacing(8)

        console_head_row = QHBoxLayout()
        console_title = QLabel("Activity Log / Output Console")
        console_title.setObjectName("cardTitle")
        console_head_row.addWidget(console_title, 1)

        console_clear_button = QPushButton("Clear")
        console_clear_button.setObjectName("action")
        console_clear_button.clicked.connect(lambda: self.dashboard_console.clear())
        console_head_row.addWidget(console_clear_button)
        console_layout.addLayout(console_head_row)

        self.dashboard_console = QPlainTextEdit()
        self.dashboard_console.setObjectName("logConsole")
        self.dashboard_console.setReadOnly(True)
        self.dashboard_console.setFixedHeight(160)
        console_layout.addWidget(self.dashboard_console)

        layout.addWidget(console_card)
        layout.addStretch()

        # Widget siap - device count/status akan diisi oleh refresh_device_list
        # / load_current_device_info yang sudah dipanggil dari __init__.
        self.dash_frp_value.setText("--")

        return page

    def _dash_log(self, text: str):
        if not hasattr(self, "dashboard_console"):
            return
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.dashboard_console.appendPlainText(f"[{timestamp}] {text}")

    def _update_case_device_hint(self):
        if not hasattr(self, "case_use_current_device"):
            return

        if self.current_device:
            self.case_use_current_device.setText(
                f"📱 Case baru akan otomatis terhubung ke device aktif: "
                f"{self.current_device.manufacturer} {self.current_device.model} "
                f"({self.current_device.serial})"
            )
        else:
            self.case_use_current_device.setText(
                "⚠ Tidak ada device terhubung - case akan dibuat tanpa info device "
                "(bisa diisi manual nanti)."
            )

    def refresh_dashboard_details(self):
        """Ambil status FRP + diagnostics ringkas untuk dashboard. Dipanggil
        sekali saat device baru terkonek / berubah / user klik refresh -
        BUKAN di setiap tick timer (lihat catatan di refresh_device_list)."""
        if not self.current_serial:
            self._dash_log("Refresh dilewati - tidak ada device terhubung.")
            self.dash_frp_value.setText("--")
            self.dash_frp_sub.setText("")
            self.dash_boot_value.setText("--")
            self.dash_boot_sub.setText("")
            self.dash_batt_value.setText("--")
            self.dash_batt_sub.setText("")
            self.dash_frp_detail.setText("Belum ada device terhubung.")
            self.dash_device_info.setText("Belum ada device terhubung.")
            self.dash_connection_detail.setText("Tidak ada device terhubung.")
            return

        if getattr(self, "_dashboard_worker", None) and self._dashboard_worker.isRunning():
            return

        serial = self.current_serial
        self._dash_log(f"Mengambil status FRP & diagnostics untuk {serial}...")

        def _gather():
            frp_state = detect_frp_service_state(serial)
            try:
                diag = get_diagnostics(serial)
            except ADBError:
                diag = None
            return frp_state, diag

        self._dashboard_worker = AsyncWorker(_gather, self)
        self._dashboard_worker.succeeded.connect(self._on_dashboard_details_ready)
        self._dashboard_worker.failed.connect(self._on_dashboard_details_error)
        self._dashboard_worker.start()

    def _on_dashboard_details_ready(self, result):
        frp_state, diag = result

        locked = frp_state.owner_auth_required
        if frp_state.authorized:
            self.dash_frp_value.setText("LOCKED" if locked else "UNLOCKED")
            self.dash_frp_value.setStyleSheet(
                f"font-size:20px; color:{'#ff6b6b' if locked else '#3ddc84'};"
            )
        else:
            self.dash_frp_value.setText("N/A")
            self.dash_frp_value.setStyleSheet("font-size:20px; color:#7d8590;")
        self.dash_frp_sub.setText(
            "Owner Verification Required" if locked else frp_state.message
        )

        unlocked_flag = (frp_state.fastboot_vars or {}).get("unlocked", "").lower()
        if unlocked_flag in ("yes", "true", "1"):
            boot_text, boot_color = "Unlocked", "#ffb020"
        elif unlocked_flag in ("no", "false", "0"):
            boot_text, boot_color = "Locked", "#3ddc84"
        else:
            boot_text, boot_color = "Unknown", "#7d8590"
        self.dash_boot_value.setText(boot_text)
        self.dash_boot_value.setStyleSheet(f"font-size:20px; color:{boot_color};")
        self.dash_boot_sub.setText(
            "Fastboot connected" if frp_state.fastboot_connected else "Fastboot not detected"
        )

        if diag:
            self.dash_batt_value.setText(diag.battery_level)
            self.dash_batt_value.setStyleSheet("font-size:20px; color:#3ddc84;")
            self.dash_batt_sub.setText(diag.battery_status)
        else:
            self.dash_batt_value.setText("--")
            self.dash_batt_value.setStyleSheet("font-size:20px;")
            self.dash_batt_sub.setText("Tidak terbaca")

        self.dash_frp_detail.setText(
            f"Current Status       : {'LOCKED' if locked else ('UNLOCKED' if frp_state.authorized else 'N/A')}\n"
            f"Owner Auth Required  : {'Yes' if frp_state.owner_auth_required else 'No'}\n"
            f"FRP State            : {frp_state.frp_status or 'Unknown'}\n"
            f"Brand Group          : {frp_state.brand_group}\n"
            f"{frp_state.message}"
        )

        props = frp_state.device_properties or {}
        if props:
            self.dash_device_info.setText(
                f"Manufacturer : {props.get('manufacturer', 'Unknown')}\n"
                f"Brand        : {props.get('brand', 'Unknown')}\n"
                f"Model        : {props.get('model', 'Unknown')}\n"
                f"Device       : {props.get('device', 'Unknown')}\n"
                f"Serial       : {frp_state.serial}"
            )

        self.dash_connection_detail.setText(
            f"Connection     : USB\n"
            f"ADB State      : {frp_state.adb_state}\n"
            f"Fastboot State : {'Connected' if frp_state.fastboot_connected else '-'}"
        )

        self._dash_log("Status FRP & diagnostics diperbarui.")

    def _on_dashboard_details_error(self, message: str):
        self._dash_log(f"Gagal mengambil detail dashboard: {message}")

    def _run_dashboard_action(self, fn, success_message: str, fail_prefix: str, action_name: str = ""):
        serial = self.current_serial
        worker = AsyncWorker(fn, self)

        def _ok(_result):
            self._dash_log(success_message)
            if action_name:
                self.log_action(action_name, detail=success_message, status="OK", serial=serial)
            self.refresh_dashboard_details()

        def _fail(msg):
            self._dash_log(f"{fail_prefix}: {msg}")
            if action_name:
                self.log_action(action_name, detail=msg, status="GAGAL", serial=serial)

        worker.succeeded.connect(_ok)
        worker.failed.connect(_fail)

        if not hasattr(self, "_dashboard_action_workers"):
            self._dashboard_action_workers = []
        self._dashboard_action_workers.append(worker)
        worker.finished.connect(
            lambda: self._dashboard_action_workers.remove(worker)
            if worker in self._dashboard_action_workers
            else None
        )
        worker.start()

    def dashboard_quick_reboot_recovery(self):
        serial = self.current_serial
        if not serial:
            QMessageBox.warning(self, "No Device", "Hubungkan device terlebih dahulu.")
            return
        self._dash_log(f"Reboot to Recovery diminta untuk {serial}...")
        self._run_dashboard_action(
            lambda: execute_recovery_reboot(serial),
            "Device reboot ke Recovery.",
            "Reboot Recovery gagal",
            action_name="Reboot to Recovery",
        )

    def dashboard_quick_reboot_bootloader(self):
        serial = self.current_serial
        if not serial:
            QMessageBox.warning(self, "No Device", "Hubungkan device terlebih dahulu.")
            return
        self._dash_log(f"Reboot to Bootloader diminta untuk {serial}...")
        self._run_dashboard_action(
            lambda: execute_bootloader_reboot(serial),
            "Device reboot ke Bootloader.",
            "Reboot Bootloader gagal",
            action_name="Reboot to Bootloader",
        )

    def dashboard_quick_verify_frp(self):
        serial = self.current_serial
        if not serial:
            QMessageBox.warning(self, "No Device", "Hubungkan device terlebih dahulu.")
            return
        self._dash_log(f"Verifikasi ulang status FRP untuk {serial}...")
        self._run_dashboard_action(
            lambda: verify_frp_result(serial),
            "Verifikasi FRP selesai.",
            "Verifikasi FRP gagal",
            action_name="Verify FRP Result",
        )

    def dashboard_quick_screenshot(self):
        serial = self.current_serial
        if not serial:
            QMessageBox.warning(self, "No Device", "Hubungkan device terlebih dahulu.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Simpan Screenshot", f"{serial}_screenshot.png", "PNG Files (*.png)"
        )
        if not path:
            return

        self._dash_log(f"Mengambil screenshot dari {serial}...")

        def _run():
            # Sengaja pakai run_adb_binary(), BUKAN run_adb() - output
            # screencap adalah PNG biner, kalau lewat run_adb() yang men-
            # decode sebagai UTF-8 text, datanya akan rusak/corrupt.
            return run_adb_binary("-s", serial, "exec-out", "screencap", "-p")

        def _ok(data: bytes):
            try:
                Path(path).write_bytes(data)
                self._dash_log(f"Screenshot disimpan: {path}")
            except OSError as exc:
                self._dash_log(f"Gagal menyimpan screenshot: {exc}")

        worker = AsyncWorker(_run, self)
        worker.succeeded.connect(_ok)
        worker.failed.connect(lambda msg: self._dash_log(f"Screenshot gagal: {msg}"))

        if not hasattr(self, "_dashboard_action_workers"):
            self._dashboard_action_workers = []
        self._dashboard_action_workers.append(worker)
        worker.finished.connect(
            lambda: self._dashboard_action_workers.remove(worker)
            if worker in self._dashboard_action_workers
            else None
        )
        worker.start()

    def dashboard_quick_save_log(self):
        if not hasattr(self, "dashboard_console"):
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Simpan Log", "nexa_dashboard_log.txt", "Text Files (*.txt)"
        )
        if not path:
            return

        try:
            Path(path).write_text(self.dashboard_console.toPlainText(), encoding="utf-8")
            self._dash_log(f"Log disimpan: {path}")
        except OSError as exc:
            self._dash_log(f"Gagal menyimpan log: {exc}")

    def _update_system_info(self):
        if not hasattr(self, "dash_cpu_bar"):
            return

        if psutil is None:
            self.dash_sysinfo_label.setText(
                "psutil belum terpasang.\nJalankan: pip install psutil"
            )
            return

        try:
            cpu = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory()
            disk_path = str(Path.home().anchor) or "/"
            disk = psutil.disk_usage(disk_path)
        except Exception:
            return

        self.dash_cpu_bar.setValue(int(cpu))
        self.dash_ram_bar.setValue(int(mem.percent))
        self.dash_disk_bar.setValue(int(disk.percent))

        uptime_seconds = int(time.time() - self._app_start_time)
        hours, remainder = divmod(uptime_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        self.dash_sysinfo_label.setText(
            f"OS           : {platform.system()} {platform.release()}\n"
            f"Tool Version : Nexa Service Tool - Smart Edition\n"
            f"Uptime       : {hours:02d}:{minutes:02d}:{seconds:02d}"
        )

    # ------------------------------------------------------------------
    # Hardware Test Page
    # ------------------------------------------------------------------

    def create_hardware_test_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)

        layout.addLayout(self._page_header(
            "Hardware Test", "Safe, read-only checks for the connected Android device."
        ))

        summary = QFrame()
        summary.setObjectName("card")
        summary_layout = QHBoxLayout(summary)
        summary_layout.setContentsMargins(20, 16, 20, 16)
        self.hardware_score = QLabel("-- / 100")
        self.hardware_score.setObjectName("scoreBig")
        self.hardware_summary = QLabel("Run a full hardware test to collect a report.")
        self.hardware_summary.setObjectName("value")
        self.hardware_summary.setWordWrap(True)
        summary_layout.addWidget(self.hardware_score)
        summary_layout.addWidget(self.hardware_summary, 1)
        layout.addWidget(summary)

        card, card_layout = self._card_panel("Hasil Pengujian")

        actions = QHBoxLayout()
        self.hardware_run_button = QPushButton("🧪 RUN FULL HARDWARE TEST")
        self.hardware_run_button.setObjectName("actionPrimary")
        self.hardware_run_button.clicked.connect(self.run_full_hardware_test)
        self.hardware_refresh_button = QPushButton("🔄 Refresh")
        self.hardware_refresh_button.setObjectName("action")
        self.hardware_refresh_button.clicked.connect(self.refresh_hardware_test_status)
        actions.addWidget(self.hardware_run_button)
        actions.addWidget(self.hardware_refresh_button)
        actions.addStretch()
        card_layout.addLayout(actions)

        self.hardware_table = QTableWidget(0, 4)
        self.hardware_table.setHorizontalHeaderLabels(["Check", "Status", "Value", "Detail"])
        self.hardware_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.hardware_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.hardware_table.horizontalHeader().setStretchLastSection(True)
        self.hardware_table.setMinimumHeight(320)
        card_layout.addWidget(self.hardware_table)

        warning = QLabel(
            "Read-only diagnostics: camera, speaker, microphone, sensors, "
            "fingerprint and touchscreen still require physical interaction tests."
        )
        warning.setObjectName("muted")
        warning.setWordWrap(True)
        card_layout.addWidget(warning)

        layout.addWidget(card)
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
        layout.setSpacing(16)

        layout.addLayout(self._page_header(
            "Device", "Informasi perangkat Android yang sedang terhubung."
        ))

        card, card_layout = self._card_panel("Status Device")

        self.device_status = QLabel("Checking...")
        self.device_status.setObjectName("status")

        self.device_info = QLabel("")
        self.device_info.setObjectName("value")
        self.device_info.setWordWrap(True)

        card_layout.addWidget(self.device_status)
        card_layout.addWidget(self.device_info)

        layout.addWidget(card)

        actions, actions_layout = self._card_panel("Device Actions")

        self.refresh_button = QPushButton("🔄 Refresh Device")
        self.refresh_button.setObjectName("action")

        self.reboot_button = QPushButton("🔁 Reboot System")
        self.reboot_button.setObjectName("action")
        self.reboot_button.setEnabled(False)

        self.recovery_button = QPushButton("🛠 Reboot Recovery")
        self.recovery_button.setObjectName("action")
        self.recovery_button.setEnabled(False)

        self.bootloader_button = QPushButton("⚠ Reboot Bootloader")
        self.bootloader_button.setObjectName("actionDanger")
        self.bootloader_button.setEnabled(False)

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
        layout.setSpacing(16)

        layout.addLayout(self._page_header(
            "Device Diagnostics",
            "Komprehensif diagnostics perangkat: ADB, boot, battery, storage, software, dan network."
        ))

        row = QHBoxLayout()
        row.setSpacing(16)

        info_card, info_layout = self._card_panel("Status Device")

        self.diag_status = QLabel("Checking...")
        self.diag_status.setObjectName("status")

        self.diag_info = QLabel("")
        self.diag_info.setObjectName("value")
        self.diag_info.setWordWrap(True)

        info_layout.addWidget(self.diag_status)
        info_layout.addWidget(self.diag_info)

        score_card, score_layout = self._card_panel("Health Score")

        self.diag_score_value = QLabel("--")
        self.diag_score_value.setObjectName("scoreBig")

        self.diag_score_bar = QProgressBar()
        self.diag_score_bar.setRange(0, 100)
        self.diag_score_bar.setValue(0)

        self.diag_recommendations = QTextEdit()
        self.diag_recommendations.setObjectName("value")
        self.diag_recommendations.setReadOnly(True)
        self.diag_recommendations.setFixedHeight(140)

        score_layout.addWidget(self.diag_score_value)
        score_layout.addWidget(self.diag_score_bar)
        score_layout.addWidget(QLabel("Rekomendasi:"))
        score_layout.addWidget(self.diag_recommendations)

        row.addWidget(info_card, 1)
        row.addWidget(score_card, 1)

        layout.addLayout(row)

        table_card, table_layout = self._card_panel("Detail Pemeriksaan")

        self.diag_table = QTableWidget(0, 5)
        self.diag_table.setHorizontalHeaderLabels(
            ["Category", "Check", "Status", "Value", "Detail"]
        )
        self.diag_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.diag_table.setSelectionMode(QTableWidget.NoSelection)
        self.diag_table.horizontalHeader().setStretchLastSection(True)
        self.diag_table.setMinimumHeight(260)
        table_layout.addWidget(self.diag_table)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.diag_refresh_button = QPushButton("🔄 Refresh Diagnostics")
        self.diag_refresh_button.setObjectName("action")
        self.diag_refresh_button.clicked.connect(self.refresh_diagnostics)

        self.diag_save_button = QPushButton("💾 Simpan ke Riwayat")
        self.diag_save_button.setObjectName("action")
        self.diag_save_button.clicked.connect(self.save_diagnostics_to_history)

        self.diag_export_button = QPushButton("🖨 Export PDF")
        self.diag_export_button.setObjectName("actionPrimary")
        self.diag_export_button.clicked.connect(self.export_pdf_report)

        btn_row.addWidget(self.diag_refresh_button)
        btn_row.addWidget(self.diag_save_button)
        btn_row.addWidget(self.diag_export_button)

        table_layout.addLayout(btn_row)
        layout.addWidget(table_card)
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
            self.log_action(
                "Save Diagnostics", detail=f"Score {self.last_score}", status="OK",
                serial=self.current_device.serial,
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
            self.log_action(
                "Export Laporan PDF", detail=file_path, status="OK",
                serial=self.current_device.serial,
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
        layout.setSpacing(16)

        layout.addLayout(self._page_header(
            "Live Logs", "Streaming logcat real-time dari device yang aktif."
        ))

        card, card_layout = self._card_panel("Logcat Controller")

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.log_start_button = QPushButton("▶ Start Logcat")
        self.log_start_button.setObjectName("actionPrimary")
        self.log_start_button.clicked.connect(self.start_logcat)

        self.log_stop_button = QPushButton("⏹ Stop")
        self.log_stop_button.setObjectName("actionDanger")
        self.log_stop_button.clicked.connect(self.stop_logcat)
        self.log_stop_button.setEnabled(False)

        self.log_clear_button = QPushButton("🧹 Clear")
        self.log_clear_button.setObjectName("action")
        self.log_clear_button.clicked.connect(lambda: self.log_console.clear())

        btn_row.addWidget(self.log_start_button)
        btn_row.addWidget(self.log_stop_button)
        btn_row.addWidget(self.log_clear_button)
        btn_row.addStretch()

        card_layout.addLayout(btn_row)

        self.log_console = QPlainTextEdit()
        self.log_console.setObjectName("logConsole")
        self.log_console.setReadOnly(True)
        self.log_console.setMaximumBlockCount(2000)
        self.log_console.setMinimumHeight(420)

        card_layout.addWidget(self.log_console)
        layout.addWidget(card)

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
        layout.setSpacing(16)

        layout.addLayout(self._page_header(
            "Service History", "Riwayat diagnostics yang pernah disimpan per device."
        ))

        history_card, history_layout = self._card_panel(
            "Riwayat Diagnostics", refresh_handler=self.refresh_history_table
        )

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
        self.history_table.setMinimumHeight(220)

        history_layout.addWidget(self.history_table)
        layout.addWidget(history_card)

        # -----------------------------------------------------------
        # Activity Log / Audit Trail - catatan tindakan berisiko
        # (backup, restore, uninstall, install, flash, verifikasi FRP,
        # reboot recovery/bootloader) yang sebelumnya tidak tercatat
        # sama sekali. Penting untuk akuntabilitas ke pelanggan.
        # -----------------------------------------------------------
        audit_card, audit_layout = self._card_panel("Activity Log (Audit Trail)")

        audit_desc = QLabel(
            "Catatan semua tindakan berisiko yang dilakukan lewat service tool ini."
        )
        audit_desc.setObjectName("muted")
        audit_layout.addWidget(audit_desc)

        # Filter serial - dipakai untuk lihat "timeline" gabungan
        # (diagnostics history + audit trail) untuk 1 device/case tertentu,
        # menyambungkan Activity Log dengan Service Cases lewat serial yang
        # sama (sebelumnya user harus loncat-loncat antar halaman).
        filter_row = QHBoxLayout()
        self.history_filter_serial = QLineEdit()
        self.history_filter_serial.setPlaceholderText("Filter berdasarkan Serial (kosongkan untuk semua)...")
        filter_button = QPushButton("Filter")
        filter_button.setObjectName("action")
        filter_button.clicked.connect(self.refresh_history_table)
        clear_filter_button = QPushButton("Reset")
        clear_filter_button.setObjectName("action")
        clear_filter_button.clicked.connect(self._clear_history_filter)
        filter_row.addWidget(self.history_filter_serial, 1)
        filter_row.addWidget(filter_button)
        filter_row.addWidget(clear_filter_button)
        audit_layout.addLayout(filter_row)

        self.action_log_table = QTableWidget(0, 6)
        self.action_log_table.setHorizontalHeaderLabels(
            ["Tanggal", "Serial", "Aksi", "Status", "Teknisi", "Detail"]
        )
        self.action_log_table.horizontalHeader().setStretchLastSection(True)
        self.action_log_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.action_log_table.setFixedHeight(220)

        audit_layout.addWidget(self.action_log_table)
        layout.addWidget(audit_card)
        layout.addStretch()

        return page

    def _clear_history_filter(self):
        self.history_filter_serial.setText("")
        self.refresh_history_table()

    def refresh_history_table(self):
        serial_filter = self.history_filter_serial.text().strip() or None
        records = get_history(serial=serial_filter, limit=200)

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

        self.refresh_action_log_table()

    def refresh_action_log_table(self):
        if not hasattr(self, "action_log_table"):
            return

        serial_filter = None
        if hasattr(self, "history_filter_serial"):
            serial_filter = self.history_filter_serial.text().strip() or None

        entries = get_action_log(serial=serial_filter, limit=200)
        self.action_log_table.setRowCount(len(entries))

        for row_idx, entry in enumerate(entries):
            values = [
                entry.created_at,
                entry.serial or "-",
                entry.action,
                entry.status,
                entry.technician or "-",
                entry.detail,
            ]

            for col_idx, val in enumerate(values):
                item = QTableWidgetItem(val)
                self.action_log_table.setItem(row_idx, col_idx, item)

    def log_action(
        self, action: str, detail: str = "", status: str = "OK", serial: str | None = None
    ):
        """Wrapper tipis di atas core.database.log_action() - dipanggil dari
        semua handler tindakan berisiko. Kalau gagal menulis ke DB, gagal
        diam-diam (jangan sampai audit logging error malah menggagalkan
        aksi utamanya) tapi tetap dicatat ke logger aplikasi."""
        technician = (self.settings.get("active_technician", "") or "Technician").strip() or "Technician"

        try:
            log_action_db(
                action=action,
                detail=detail,
                status=status,
                serial=serial or self.current_serial or "",
                technician=technician,
            )
        except Exception:
            logger.exception("Gagal menulis audit log: %s", action)

        if hasattr(self, "action_log_table"):
            self.refresh_action_log_table()

    # ------------------------------------------------------------------
    # Security Check Page
    # ------------------------------------------------------------------

    def create_security_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)

        layout.addLayout(self._page_header(
            "Security Check", "Auto-detect root, status bootloader, dan patch keamanan."
        ))

        card, card_layout = self._card_panel("Status Keamanan")

        self.security_status = QLabel("Checking...")
        self.security_status.setObjectName("status")

        self.security_info = QLabel("")
        self.security_info.setObjectName("value")
        self.security_info.setWordWrap(True)

        card_layout.addWidget(self.security_status)
        card_layout.addWidget(self.security_info)

        layout.addWidget(card)

        warn_card, warn_layout = self._card_panel("Peringatan & Rekomendasi")

        self.security_warnings = QTextEdit()
        self.security_warnings.setObjectName("value")
        self.security_warnings.setReadOnly(True)
        self.security_warnings.setFixedHeight(150)

        warn_layout.addWidget(self.security_warnings)

        layout.addWidget(warn_card)

        self.security_refresh_button = QPushButton("🛡 Jalankan Security Check")
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
        layout.setSpacing(16)

        layout.addLayout(self._page_header(
            "App Manager", "Kelola aplikasi terinstall di device: install, uninstall, force-stop."
        ))

        card, card_layout = self._card_panel("Daftar Aplikasi")

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.apps_refresh_button = QPushButton("🔄 Refresh Daftar Apps")
        self.apps_refresh_button.setObjectName("action")
        self.apps_refresh_button.clicked.connect(self.refresh_apps_list)

        self.apps_install_button = QPushButton("⬇ Install APK...")
        self.apps_install_button.setObjectName("actionPrimary")
        self.apps_install_button.clicked.connect(self.install_apk_dialog)

        btn_row.addWidget(self.apps_refresh_button)
        btn_row.addWidget(self.apps_install_button)
        btn_row.addStretch()

        card_layout.addLayout(btn_row)

        self.apps_list = QListWidget()
        self.apps_list.setMinimumHeight(340)
        card_layout.addWidget(self.apps_list)

        action_row = QHBoxLayout()
        action_row.setSpacing(10)

        self.apps_stop_button = QPushButton("⏹ Force Stop")
        self.apps_stop_button.setObjectName("action")
        self.apps_stop_button.clicked.connect(self.force_stop_selected_app)

        self.apps_repair_button = QPushButton("🔧 Repair (Trim Cache)")
        self.apps_repair_button.setObjectName("action")
        self.apps_repair_button.setToolTip(
            "Bersihkan cache SEMUA aplikasi (setara 'Free up space' di "
            "Settings Android). Tidak menghapus data/login/foto - aman."
        )
        self.apps_repair_button.clicked.connect(self.repair_trim_caches)

        self.apps_clear_button = QPushButton("🗑 Clear Data")
        self.apps_clear_button.setObjectName("action")
        self.apps_clear_button.clicked.connect(self.clear_data_selected_app)

        self.apps_uninstall_button = QPushButton("❌ Uninstall")
        self.apps_uninstall_button.setObjectName("actionDanger")
        self.apps_uninstall_button.clicked.connect(self.uninstall_selected_app)

        action_row.addWidget(self.apps_stop_button)
        action_row.addWidget(self.apps_repair_button)
        action_row.addWidget(self.apps_clear_button)
        action_row.addWidget(self.apps_uninstall_button)

        card_layout.addLayout(action_row)
        layout.addWidget(card)

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

        serial = self.current_device.serial
        worker = AsyncWorker(lambda: clear_app_data(serial, package), self)

        def _ok(_r):
            QMessageBox.information(self, "Berhasil", f"Data {package} berhasil dihapus.")
            self.log_action("Clear App Data", detail=package, status="OK", serial=serial)

        def _fail(msg):
            QMessageBox.critical(self, "Gagal", msg)
            self.log_action("Clear App Data", detail=f"{package}: {msg}", status="GAGAL", serial=serial)

        worker.succeeded.connect(_ok)
        worker.failed.connect(_fail)
        self._apps_action_worker = worker
        worker.start()

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

        serial = self.current_device.serial

        def _ok(_result):
            QMessageBox.information(self, "Berhasil", f"{package} berhasil di-uninstall.")
            self.log_action("Uninstall App", detail=package, status="OK", serial=serial)
            self.refresh_apps_list()

        def _fail(msg):
            QMessageBox.critical(self, "Gagal", msg)
            self.log_action("Uninstall App", detail=f"{package}: {msg}", status="GAGAL", serial=serial)

        worker = AsyncWorker(lambda: uninstall_package(serial, package), self)
        worker.succeeded.connect(_ok)
        worker.failed.connect(_fail)
        self._apps_action_worker = worker
        worker.start()

    def install_apk_dialog(self):
        if not self.current_device:
            QMessageBox.warning(self, "Tidak ada device", "Hubungkan device terlebih dahulu.")
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self, "Pilih file APK", "", "APK Files (*.apk)"
        )

        if not file_path:
            return

        serial = self.current_device.serial

        def _ok(_result):
            QMessageBox.information(self, "Berhasil", "APK berhasil di-install.")
            self.log_action("Install APK", detail=file_path, status="OK", serial=serial)
            self.refresh_apps_list()

        def _fail(msg):
            QMessageBox.critical(self, "Install Gagal", msg)
            self.log_action("Install APK", detail=f"{file_path}: {msg}", status="GAGAL", serial=serial)

        worker = AsyncWorker(lambda: install_apk(serial, file_path), self)
        worker.succeeded.connect(_ok)
        worker.failed.connect(_fail)
        self._apps_action_worker = worker
        worker.start()

    # ------------------------------------------------------------------
    # File Explorer Page
    # ------------------------------------------------------------------

    def create_files_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)

        layout.addLayout(self._page_header(
            "File Explorer", "Browse penyimpanan device, push/pull file via ADB."
        ))

        card, card_layout = self._card_panel("Penjelajah File")

        path_row = QHBoxLayout()
        path_row.setSpacing(8)

        self.files_path_input = QLineEdit(self.file_explorer_path)
        self.files_path_input.returnPressed.connect(self.navigate_to_path_input)

        self.files_up_button = QPushButton("⬆ Up")
        self.files_up_button.setObjectName("action")
        self.files_up_button.clicked.connect(self.navigate_up)

        self.files_go_button = QPushButton("➜ Go")
        self.files_go_button.setObjectName("action")
        self.files_go_button.clicked.connect(self.navigate_to_path_input)

        path_row.addWidget(self.files_path_input)
        path_row.addWidget(self.files_up_button)
        path_row.addWidget(self.files_go_button)

        card_layout.addLayout(path_row)

        self.files_list = QListWidget()
        self.files_list.setMinimumHeight(340)
        self.files_list.itemDoubleClicked.connect(self.on_file_double_clicked)
        card_layout.addWidget(self.files_list)

        action_row = QHBoxLayout()
        action_row.setSpacing(10)

        self.files_pull_button = QPushButton("⬇ Pull ke Laptop")
        self.files_pull_button.setObjectName("action")
        self.files_pull_button.clicked.connect(self.pull_selected_file)

        self.files_push_button = QPushButton("⬆ Push dari Laptop")
        self.files_push_button.setObjectName("action")
        self.files_push_button.clicked.connect(self.push_file_dialog)

        self.files_delete_button = QPushButton("🗑 Hapus")
        self.files_delete_button.setObjectName("actionDanger")
        self.files_delete_button.clicked.connect(self.delete_selected_file)

        action_row.addWidget(self.files_pull_button)
        action_row.addWidget(self.files_push_button)
        action_row.addWidget(self.files_delete_button)

        card_layout.addLayout(action_row)
        layout.addWidget(card)

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
        layout.setSpacing(16)

        layout.addLayout(self._page_header(
            "Screen Mirror",
            "Preview layar device (refresh berkala) - klik gambar untuk tap, "
            "berbasis ADB tanpa dependency tambahan."
        ))

        card, card_layout = self._card_panel("Live Preview")

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.mirror_start_button = QPushButton("▶ Start Mirror")
        self.mirror_start_button.setObjectName("actionPrimary")
        self.mirror_start_button.clicked.connect(self.start_mirror)

        self.mirror_stop_button = QPushButton("⏹ Stop")
        self.mirror_stop_button.setObjectName("actionDanger")
        self.mirror_stop_button.clicked.connect(self.stop_mirror)
        self.mirror_stop_button.setEnabled(False)

        self.mirror_home_button = QPushButton("⌂ Home")
        self.mirror_home_button.setObjectName("action")
        self.mirror_home_button.clicked.connect(lambda: self._send_key_safe("KEYCODE_HOME"))

        self.mirror_back_button = QPushButton("◀ Back")
        self.mirror_back_button.setObjectName("action")
        self.mirror_back_button.clicked.connect(lambda: self._send_key_safe("KEYCODE_BACK"))

        btn_row.addWidget(self.mirror_start_button)
        btn_row.addWidget(self.mirror_stop_button)
        btn_row.addWidget(self.mirror_home_button)
        btn_row.addWidget(self.mirror_back_button)
        btn_row.addStretch()

        card_layout.addLayout(btn_row)

        self.mirror_view = QLabel("Klik Start Mirror untuk mulai preview layar device.")
        self.mirror_view.setObjectName("value")
        self.mirror_view.setAlignment(Qt.AlignCenter)
        self.mirror_view.setMinimumHeight(420)
        self.mirror_view.setStyleSheet(
            "background:#0a0b0e; border:1px solid #22262f; border-radius:10px;"
        )
        self.mirror_view.mousePressEvent = self._on_mirror_clicked

        card_layout.addWidget(self.mirror_view)
        layout.addWidget(card)

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
        layout.setSpacing(16)

        layout.addLayout(self._page_header(
            "Backup & Restore",
            "Backup folder penting (DCIM, Download, Pictures, WhatsApp) ke file ZIP, "
            "dan restore kembali ke device."
        ))

        card, card_layout = self._card_panel("Backup Device")

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.backup_button = QPushButton("☁ Backup Sekarang")
        self.backup_button.setObjectName("actionPrimary")
        self.backup_button.clicked.connect(self.run_backup)

        self.restore_button = QPushButton("⤴ Restore dari ZIP...")
        self.restore_button.setObjectName("action")
        self.restore_button.clicked.connect(self.run_restore)

        btn_row.addWidget(self.backup_button)
        btn_row.addWidget(self.restore_button)
        btn_row.addStretch()

        card_layout.addLayout(btn_row)

        self.backup_restore_progress = QProgressBar()
        self.backup_restore_progress.setRange(0, 1)
        self.backup_restore_progress.setValue(0)
        self.backup_restore_progress.setFormat("Belum ada proses berjalan")
        card_layout.addWidget(self.backup_restore_progress)

        self.backup_log = QPlainTextEdit()
        self.backup_log.setObjectName("logConsole")
        self.backup_log.setReadOnly(True)
        self.backup_log.setMinimumHeight(320)

        card_layout.addWidget(self.backup_log)
        layout.addWidget(card)

        return page

    def _on_backup_restore_progress(self, current: int, total: int, label: str):
        self.backup_restore_progress.setRange(0, max(total, 1))
        self.backup_restore_progress.setValue(current)
        self.backup_restore_progress.setFormat(f"{current}/{total} - {label}")
        self.backup_log.appendPlainText(f"[{current}/{total}] Memproses {label}...")

    def run_backup(self):
        if not self.current_device:
            QMessageBox.warning(self, "Tidak ada device", "Hubungkan device terlebih dahulu.")
            return

        output_dir = QFileDialog.getExistingDirectory(self, "Pilih folder tujuan backup")

        if not output_dir:
            return

        if getattr(self, "_backup_worker", None) and self._backup_worker.isRunning():
            return

        # Isi backup (DCIM, WhatsApp media, dst) adalah data pribadi
        # pelanggan yang sensitif. Sebelumnya selalu tersimpan sebagai ZIP
        # polos tanpa proteksi apapun - kalau laptop teknisi dicuri/kena
        # malware, semua foto/chat pelanggan lama bisa bocor. Sekarang
        # ditawarkan opsi enkripsi AES.
        encrypt_reply = QMessageBox.question(
            self, "Enkripsi Backup?",
            "Backup ini akan berisi data pribadi pelanggan (foto, chat "
            "WhatsApp, dll).\n\nEnkripsi dengan password supaya lebih aman "
            "kalau file backup ini hilang/dicuri?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
        )

        password = None
        if encrypt_reply == QMessageBox.Yes:
            password, ok = QInputDialog.getText(
                self, "Password Backup",
                "Masukkan password untuk backup ini (min. 4 karakter):",
                QLineEdit.Password,
            )
            if not ok:
                return
            password = password.strip()
            if password and len(password) < 4:
                QMessageBox.warning(self, "Password Terlalu Pendek", "Minimal 4 karakter.")
                return
            if not password:
                QMessageBox.information(
                    self, "Tanpa Enkripsi", "Password kosong - backup akan disimpan tanpa enkripsi."
                )
                password = None

        self.backup_log.appendPlainText(
            f"Memulai backup device {self.current_device.serial} - mohon tunggu..."
        )
        # backup_device() bisa makan waktu bermenit-menit (pull DCIM/
        # WhatsApp/Pictures/Download). Sebelumnya dipanggil langsung di
        # main thread - UI freeze total selama itu, sama seperti bug flash
        # partition. Sekarang dijalankan di background thread.
        self.backup_button.setEnabled(False)
        self.backup_restore_progress.setRange(0, 1)
        self.backup_restore_progress.setValue(0)
        self.backup_restore_progress.setFormat("Memulai backup...")
        serial = self.current_device.serial
        self._last_backup_output_dir = output_dir
        self._last_backup_password = password

        def _do_backup():
            return backup_device(
                serial,
                Path(output_dir),
                progress_callback=lambda i, t, name: worker.progress.emit(i, t, name),
                password=password,
            )

        worker = AsyncWorker(_do_backup, self)
        worker.progress.connect(self._on_backup_restore_progress)

        def _ok(zip_path):
            enc_note = " (terenkripsi)" if password else ""
            self.backup_log.appendPlainText(f"Backup selesai{enc_note}: {zip_path}")
            self.backup_button.setEnabled(True)
            self.log_action(
                "Backup",
                detail=f"Tersimpan di {zip_path}{enc_note}",
                status="OK",
                serial=serial,
            )
            QMessageBox.information(self, "Backup Selesai", f"File tersimpan di:\n{zip_path}")

        def _fail(message):
            self.backup_log.appendPlainText(f"Backup gagal: {message}")
            self.backup_button.setEnabled(True)
            self.log_action("Backup", detail=message, status="GAGAL", serial=serial)
            QMessageBox.critical(self, "Backup Gagal", message)

        worker.succeeded.connect(_ok)
        worker.failed.connect(_fail)
        self._backup_worker = worker
        worker.start()

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

        if getattr(self, "_restore_worker", None) and self._restore_worker.isRunning():
            return

        password = None
        if is_zip_password_protected(Path(zip_path)):
            password, ok = QInputDialog.getText(
                self, "Password Backup",
                "File backup ini dienkripsi. Masukkan password:",
                QLineEdit.Password,
            )
            if not ok:
                return
            password = password.strip()
            if not password:
                QMessageBox.warning(self, "Password Kosong", "Password wajib diisi untuk backup terenkripsi.")
                return

        self.backup_log.appendPlainText(f"Memulai restore dari {zip_path} - mohon tunggu...")
        self.restore_button.setEnabled(False)
        self.backup_restore_progress.setRange(0, 1)
        self.backup_restore_progress.setValue(0)
        self.backup_restore_progress.setFormat("Memulai restore...")
        serial = self.current_device.serial

        def _do_restore():
            return restore_device(
                serial,
                Path(zip_path),
                progress_callback=lambda i, t, name: worker.progress.emit(i, t, name),
                password=password,
            )

        worker = AsyncWorker(_do_restore, self)
        worker.progress.connect(self._on_backup_restore_progress)

        def _ok(results):
            for line in results:
                self.backup_log.appendPlainText(line)
            self.restore_button.setEnabled(True)
            self.log_action(
                "Restore", detail=f"Dari {zip_path}", status="OK", serial=serial
            )
            QMessageBox.information(self, "Restore Selesai", "Proses restore selesai.")

        def _fail(message):
            self.backup_log.appendPlainText(f"Restore gagal: {message}")
            self.restore_button.setEnabled(True)
            self.log_action("Restore", detail=message, status="GAGAL", serial=serial)
            QMessageBox.critical(self, "Restore Gagal", message)

        worker.succeeded.connect(_ok)
        worker.failed.connect(_fail)
        self._restore_worker = worker
        worker.start()

    # ------------------------------------------------------------------
    # Network & IMEI Page
    # ------------------------------------------------------------------

    def create_network_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)

        layout.addLayout(self._page_header(
            "Network & IMEI", "Informasi IMEI, status WiFi/data seluler, IP, dan operator."
        ))

        card, card_layout = self._card_panel("Status Jaringan")

        self.network_status = QLabel("Checking...")
        self.network_status.setObjectName("status")

        self.network_info_label = QLabel("")
        self.network_info_label.setObjectName("value")
        self.network_info_label.setWordWrap(True)

        card_layout.addWidget(self.network_status)
        card_layout.addWidget(self.network_info_label)

        layout.addWidget(card)

        self.network_refresh_button = QPushButton("🔄 Refresh Network Info")
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
        layout.setSpacing(16)

        layout.addLayout(self._page_header(
            "Firmware & Flash",
            "Info build firmware saat ini, dan flash partition via Fastboot. "
            "Fitur flashing hanya aktif saat device dalam mode Bootloader."
        ))

        card, card_layout = self._card_panel(
            "Build Info", refresh_handler=lambda: self.refresh_firmware_info(),
            refresh_label="🔄 Refresh Build Info",
        )

        self.firmware_status = QLabel("Checking...")
        self.firmware_status.setObjectName("status")

        self.firmware_info_label = QLabel("")
        self.firmware_info_label.setObjectName("value")
        self.firmware_info_label.setWordWrap(True)

        card_layout.addWidget(self.firmware_status)
        card_layout.addWidget(self.firmware_info_label)

        layout.addWidget(card)

        # --- Fastboot Flash Section ---
        flash_card, flash_layout = self._card_panel("Flash Partition (Fastboot Mode)")

        flash_warning = QLabel(
            "⚠ PERINGATAN: Flash partition yang salah dapat menyebabkan device "
            "bootloop atau mati total (bricked). Pastikan file image sesuai "
            "dengan model device dan partition target."
        )
        flash_warning.setObjectName("value")
        flash_warning.setWordWrap(True)
        flash_warning.setStyleSheet("color:#ff6b6b;")
        flash_layout.addWidget(flash_warning)

        self.firmware_reboot_bootloader_button = QPushButton(
            "🔁 Reboot ke Bootloader"
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

        self.firmware_select_image_button = QPushButton("📁 Pilih File Image...")
        self.firmware_select_image_button.setObjectName("action")
        self.firmware_select_image_button.clicked.connect(self.select_firmware_image)

        partition_row.addWidget(self.firmware_partition_combo)
        partition_row.addWidget(self.firmware_select_image_button)

        flash_layout.addLayout(partition_row)

        self.firmware_image_path_label = QLabel("Belum ada file dipilih.")
        self.firmware_image_path_label.setObjectName("value")
        self.firmware_image_path_label.setWordWrap(True)
        flash_layout.addWidget(self.firmware_image_path_label)

        self.firmware_flash_button = QPushButton("⚡ Flash Partition Sekarang")
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
        image_path = self._firmware_image_path

        self.firmware_flash_log.appendPlainText(
            f"Flashing '{partition}' pada device {serial}..."
        )
        # PENTING: flash_partition() bisa makan waktu sampai 180 detik.
        # Sebelumnya ini dipanggil langsung di main thread - UI freeze
        # total selama proses flash berlangsung, yang berisiko bikin user
        # mengira app hang lalu force-close di tengah proses flash. Force-
        # close di tengah operasi flash BISA MERUSAK PARTITION/BRICK
        # DEVICE. Sekarang dijalankan di background thread supaya UI tetap
        # responsif dan progress terlihat jelas.
        self.firmware_flash_button.setEnabled(False)
        self.firmware_flash_button.setText("Sedang Flashing... Jangan cabut kabel!")

        worker = AsyncWorker(
            lambda: flash_partition(partition, image_path, serial=serial), self
        )

        def _on_success(output):
            self.firmware_flash_log.appendPlainText(output or "Flash selesai.")
            self.firmware_flash_log.appendPlainText("--- SELESAI ---")
            self.firmware_flash_button.setEnabled(True)
            self.firmware_flash_button.setText("Flash Partition Sekarang")
            self.log_action(
                "Flash Partition",
                detail=f"{partition} <- {image_path}",
                status="OK",
                serial=serial,
            )
            QMessageBox.information(
                self, "Flash Berhasil", f"Partition '{partition}' berhasil diflash."
            )

        def _on_error(message):
            self.firmware_flash_log.appendPlainText(f"ERROR: {message}")
            self.firmware_flash_button.setEnabled(True)
            self.firmware_flash_button.setText("Flash Partition Sekarang")
            self.log_action(
                "Flash Partition",
                detail=f"{partition} <- {image_path}: {message}",
                status="GAGAL",
                serial=serial,
            )
            QMessageBox.critical(self, "Flash Gagal", message)

        worker.succeeded.connect(_on_success)
        worker.failed.connect(_on_error)
        self._flash_worker = worker
        worker.start()

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
        layout.setSpacing(16)

        layout.addLayout(self._page_header(
            "Service Cases", "Catat & lacak setiap job servis dari masuk sampai selesai."
        ))

        form_card, form_layout = self._card_panel("Case Baru")

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
        self.case_sla = QLineEdit()
        self.case_sla.setPlaceholderText("Estimasi selesai (mis: 2026-08-16 atau 'Besok sore')")

        for widget in (
            self.case_customer_name, self.case_customer_phone,
            self.case_complaint, self.case_technician, self.case_cost,
            self.case_sla,
        ):
            form_layout.addWidget(widget)

        self.case_use_current_device = QLabel("")
        self.case_use_current_device.setObjectName("muted")
        self.case_use_current_device.setWordWrap(True)
        form_layout.addWidget(self.case_use_current_device)

        self.case_save_button = QPushButton("💾 Simpan Case Baru")
        self.case_save_button.setObjectName("actionPrimary")
        self.case_save_button.clicked.connect(self.create_new_case)
        form_layout.addWidget(self.case_save_button)

        layout.addWidget(form_card)

        list_card, list_layout = self._card_panel("Daftar Case")

        filter_row = QHBoxLayout()
        self.case_search = QLineEdit()
        self.case_search.setPlaceholderText("Cari nama customer / case number...")
        self.case_status_filter = QComboBox()
        self.case_status_filter.setObjectName("deviceSelector")
        self.case_status_filter.addItem("Semua Status")
        for status in CASE_STATUSES:
            self.case_status_filter.addItem(status)
        self.case_refresh_button = QPushButton("🔄 Refresh")
        self.case_refresh_button.setObjectName("action")
        self.case_refresh_button.clicked.connect(self.refresh_cases_table)
        filter_row.addWidget(self.case_search, 2)
        filter_row.addWidget(self.case_status_filter, 1)
        filter_row.addWidget(self.case_refresh_button)
        list_layout.addLayout(filter_row)

        self.cases_table = QTableWidget(0, 8)
        self.cases_table.setHorizontalHeaderLabels(
            ["Case #", "Customer", "Device", "Complaint", "Status", "Pembayaran", "Estimasi Selesai", "Updated"]
        )
        self.cases_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.cases_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.cases_table.horizontalHeader().setStretchLastSection(True)
        self.cases_table.setMinimumHeight(260)
        list_layout.addWidget(self.cases_table)

        action_row = QHBoxLayout()
        self.case_update_status_button = QPushButton("✏ Update Status")
        self.case_update_status_button.setObjectName("action")
        self.case_update_status_button.clicked.connect(self.update_selected_case_status)
        self.case_add_note_button = QPushButton("📝 Tambah Catatan")
        self.case_add_note_button.setObjectName("action")
        self.case_add_note_button.clicked.connect(self.add_note_to_selected_case)
        self.case_response_button = QPushButton("💬 Respons ke Customer")
        self.case_response_button.setObjectName("action")
        self.case_response_button.clicked.connect(self.generate_customer_response)
        self.case_timeline_button = QPushButton("📜 Lihat Timeline")
        self.case_timeline_button.setObjectName("action")
        self.case_timeline_button.clicked.connect(self.view_case_timeline)
        action_row.addWidget(self.case_update_status_button)
        action_row.addWidget(self.case_add_note_button)
        action_row.addWidget(self.case_response_button)
        action_row.addWidget(self.case_timeline_button)
        action_row.addStretch()
        list_layout.addLayout(action_row)

        # Baris kedua: fitur untuk teknisi service center - dokumentasi
        # foto (proteksi dari komplain "HP saya lecet gara-gara diservis"),
        # cetak nota/label fisik, update pembayaran, notifikasi WhatsApp.
        action_row2 = QHBoxLayout()
        self.case_photo_button = QPushButton("📷 Kelola Foto")
        self.case_photo_button.setObjectName("action")
        self.case_photo_button.clicked.connect(self.manage_case_photos)
        self.case_payment_button = QPushButton("💳 Update Pembayaran")
        self.case_payment_button.setObjectName("action")
        self.case_payment_button.clicked.connect(self.update_case_payment)
        self.case_invoice_button = QPushButton("🖨 Cetak Nota")
        self.case_invoice_button.setObjectName("action")
        self.case_invoice_button.clicked.connect(self.print_case_invoice)
        self.case_label_button = QPushButton("🏷 Cetak Label")
        self.case_label_button.setObjectName("action")
        self.case_label_button.clicked.connect(self.print_case_label)
        self.case_whatsapp_button = QPushButton("📲 Notifikasi WA")
        self.case_whatsapp_button.setObjectName("action")
        self.case_whatsapp_button.clicked.connect(self.send_case_whatsapp_notification)
        action_row2.addWidget(self.case_photo_button)
        action_row2.addWidget(self.case_payment_button)
        action_row2.addWidget(self.case_invoice_button)
        action_row2.addWidget(self.case_label_button)
        action_row2.addWidget(self.case_whatsapp_button)
        action_row2.addStretch()
        list_layout.addLayout(action_row2)

        layout.addWidget(list_card)

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
                estimated_completion=self.case_sla.text().strip(),
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Gagal Menyimpan Case", str(exc))
            return

        logger.info("Service case dibuat: %s", case.case_number)
        QMessageBox.information(self, "Case Dibuat", f"Case {case.case_number} berhasil disimpan.")

        for widget in (
            self.case_customer_name, self.case_customer_phone,
            self.case_complaint, self.case_technician, self.case_cost,
            self.case_sla,
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

        # Pakai build_case_status_message() yang sama dengan fitur
        # 'Notifikasi WA' - sebelumnya function ini punya dict template
        # terpisah sendiri yang gampang tidak sinkron kalau salah satu
        # diedit tapi yang lain tidak.
        message = build_case_status_message(case)

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
                case.complaint, case.status, case.payment_status,
                case.estimated_completion or "-", case.updated_at,
            ]
            # Sorotan visual kalau SLA sudah lewat dan case belum selesai -
            # supaya teknisi/owner langsung lihat mana case yang kelamaan
            # ngendon tanpa harus buka satu-satu.
            overdue = self._is_case_overdue(case)

            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.UserRole, case.id)
                if overdue:
                    item.setForeground(QColor("#ff6b6b"))
                self.cases_table.setItem(row, col, item)

    @staticmethod
    def _is_case_overdue(case) -> bool:
        if case.status in ("Completed", "Cancelled") or not case.estimated_completion:
            return False
        try:
            deadline = datetime.fromisoformat(case.estimated_completion[:19])
        except ValueError:
            return False
        return datetime.now() > deadline

    def _selected_case_id(self) -> int | None:
        row = self.cases_table.currentRow()
        if row < 0:
            return None
        item = self.cases_table.item(row, 0)
        return item.data(Qt.UserRole) if item else None

    def view_case_timeline(self):
        """Timeline gabungan untuk 1 case: perubahan status case +
        riwayat diagnostics + audit trail tindakan (backup/restore/flash/
        dst) - semuanya disatukan berdasarkan device_serial, yang
        sebelumnya cuma bisa dilihat terpisah-pisah di halaman berbeda."""
        case_id = self._selected_case_id()

        if case_id is None:
            QMessageBox.warning(self, "Pilih Case", "Pilih salah satu case dari daftar dulu.")
            return

        try:
            case = get_case(case_id)
            case_events = get_case_timeline(case_id)
        except Exception as exc:
            QMessageBox.critical(self, "Gagal Memuat Timeline", str(exc))
            return

        entries = []

        for ev in case_events:
            entries.append((
                ev.get("created_at", ""),
                "Case",
                f"{ev.get('event_type', '')}: {ev.get('old_value', '') or '-'} → {ev.get('new_value', '') or '-'}"
                + (f" ({ev.get('note')})" if ev.get("note") else ""),
            ))

        if case.device_serial:
            for rec in get_history(serial=case.device_serial, limit=100):
                entries.append((
                    rec.created_at, "Diagnostics",
                    f"Health score {rec.health_score} - {rec.recommendations or '-'}",
                ))

            for act in get_action_log(serial=case.device_serial, limit=100):
                entries.append((
                    act.created_at, "Aksi",
                    f"{act.action} [{act.status}] oleh {act.technician or '-'} - {act.detail or '-'}",
                ))

        entries.sort(key=lambda e: e[0])

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Timeline - {case.case_number} ({case.customer_name})")
        dialog.resize(640, 480)
        dialog_layout = QVBoxLayout(dialog)

        header = QLabel(
            f"<b>{case.case_number}</b> - {case.customer_name}<br>"
            f"Device: {case.device_serial or '-'} | Status: {case.status}<br>"
            f"Keluhan: {case.complaint}"
        )
        header.setWordWrap(True)
        dialog_layout.addWidget(header)

        timeline_table = QTableWidget(len(entries), 3)
        timeline_table.setHorizontalHeaderLabels(["Waktu", "Tipe", "Detail"])
        timeline_table.horizontalHeader().setStretchLastSection(True)
        timeline_table.setEditTriggers(QTableWidget.NoEditTriggers)

        for row_idx, (ts, kind, detail) in enumerate(entries):
            for col_idx, val in enumerate([ts, kind, detail]):
                timeline_table.setItem(row_idx, col_idx, QTableWidgetItem(str(val)))

        dialog_layout.addWidget(timeline_table)

        close_button = QPushButton("Tutup")
        close_button.clicked.connect(dialog.accept)
        dialog_layout.addWidget(close_button)

        dialog.exec()

    # ------------------------------------------------------------------
    # Dokumentasi foto - proteksi teknisi dari komplain "device rusak
    # gara-gara diservis" dengan bukti foto kondisi sebelum dikerjakan.
    # ------------------------------------------------------------------
    def manage_case_photos(self):
        case_id = self._selected_case_id()
        if case_id is None:
            QMessageBox.warning(self, "Pilih Case", "Pilih case dari tabel dulu.")
            return

        try:
            case = get_case(case_id)
        except Exception as exc:
            QMessageBox.critical(self, "Gagal", str(exc))
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Foto - {case.case_number} ({case.customer_name})")
        dialog.resize(520, 420)
        dialog_layout = QVBoxLayout(dialog)

        info = QLabel(
            "Dokumentasikan kondisi device (mis. sebelum diservis) sebagai "
            "bukti untuk pelanggan maupun perlindungan teknisi."
        )
        info.setWordWrap(True)
        info.setObjectName("muted")
        dialog_layout.addWidget(info)

        photo_list = QListWidget()
        dialog_layout.addWidget(photo_list)

        def _reload_list():
            photo_list.clear()
            for photo in get_case_photos_db(case_id):
                label = Path(photo.photo_path).name
                if photo.caption:
                    label += f" - {photo.caption}"
                item = QListWidgetItem(label)
                item.setData(Qt.UserRole, photo)
                photo_list.addItem(item)

        _reload_list()

        btn_row = QHBoxLayout()
        add_button = QPushButton("➕ Tambah Foto...")
        add_button.setObjectName("actionPrimary")
        open_button = QPushButton("🖼 Buka")
        open_button.setObjectName("action")
        delete_button = QPushButton("🗑 Hapus")
        delete_button.setObjectName("actionDanger")
        btn_row.addWidget(add_button)
        btn_row.addWidget(open_button)
        btn_row.addWidget(delete_button)
        dialog_layout.addLayout(btn_row)

        close_button = QPushButton("Tutup")
        close_button.clicked.connect(dialog.accept)
        dialog_layout.addWidget(close_button)

        def _add_photo():
            file_path, _ = QFileDialog.getOpenFileName(
                dialog, "Pilih Foto", "", "Images (*.jpg *.jpeg *.png *.webp)"
            )
            if not file_path:
                return

            caption, ok = QInputDialog.getText(
                dialog, "Keterangan Foto",
                "Keterangan (mis: 'Kondisi awal - layar retak'):",
            )
            if not ok:
                caption = ""

            # Foto disalin ke folder lokal per-case supaya tidak hilang
            # kalau file aslinya dipindah/dihapus dari lokasi awal.
            dest_dir = PROJECT_ROOT / "data" / "case_photos" / case.case_number
            dest_dir.mkdir(parents=True, exist_ok=True)
            src = Path(file_path)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            dest = dest_dir / f"{timestamp}_{src.name}"

            try:
                shutil.copy2(src, dest)
                add_case_photo_db(case_id, str(dest), caption)
                self.log_action(
                    "Tambah Foto Case", detail=f"{case.case_number}: {caption or dest.name}",
                    status="OK", serial=case.device_serial,
                )
                _reload_list()
            except OSError as exc:
                QMessageBox.critical(dialog, "Gagal", f"Gagal menyalin foto: {exc}")

        def _open_photo():
            item = photo_list.currentItem()
            if not item:
                QMessageBox.information(dialog, "Pilih Foto", "Pilih foto dari daftar dulu.")
                return
            photo = item.data(Qt.UserRole)
            QDesktopServices.openUrl(QUrl.fromLocalFile(photo.photo_path))

        def _delete_photo():
            item = photo_list.currentItem()
            if not item:
                QMessageBox.information(dialog, "Pilih Foto", "Pilih foto dari daftar dulu.")
                return
            photo = item.data(Qt.UserRole)
            reply = QMessageBox.question(
                dialog, "Konfirmasi", "Hapus foto ini dari catatan case?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                delete_case_photo_db(photo.id)
                _reload_list()

        add_button.clicked.connect(_add_photo)
        open_button.clicked.connect(_open_photo)
        delete_button.clicked.connect(_delete_photo)

        dialog.exec()

    # ------------------------------------------------------------------
    # Pembayaran
    # ------------------------------------------------------------------
    def update_case_payment(self):
        case_id = self._selected_case_id()
        if case_id is None:
            QMessageBox.warning(self, "Pilih Case", "Pilih case dari tabel dulu.")
            return

        try:
            case = get_case(case_id)
        except Exception as exc:
            QMessageBox.critical(self, "Gagal", str(exc))
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Update Pembayaran - {case.case_number}")
        dialog_layout = QVBoxLayout(dialog)

        info = QLabel(
            f"Estimasi biaya: Rp {case.estimated_cost:,.0f}\n"
            f"Status saat ini: {case.payment_status} (Rp {case.paid_amount:,.0f})"
        )
        dialog_layout.addWidget(info)

        status_combo = QComboBox()
        status_combo.addItems(CASE_PAYMENT_STATUSES)
        status_combo.setCurrentText(case.payment_status)
        dialog_layout.addWidget(QLabel("Status Pembayaran"))
        dialog_layout.addWidget(status_combo)

        amount_input = QLineEdit(str(int(case.paid_amount)))
        dialog_layout.addWidget(QLabel("Jumlah Dibayar (Rp)"))
        dialog_layout.addWidget(amount_input)

        save_button = QPushButton("💾 Simpan")
        save_button.setObjectName("actionPrimary")
        dialog_layout.addWidget(save_button)

        def _save():
            try:
                amount = float(amount_input.text().strip().replace(".", "").replace(",", "") or "0")
            except ValueError:
                QMessageBox.warning(dialog, "Jumlah Tidak Valid", "Jumlah dibayar harus berupa angka.")
                return

            try:
                update_case_payment_db(case_id, status_combo.currentText(), amount)
                self.log_action(
                    "Update Pembayaran", detail=f"{case.case_number}: {status_combo.currentText()} (Rp{amount:,.0f})",
                    status="OK", serial=case.device_serial,
                )
                self.refresh_cases_table()
                dialog.accept()
            except (ValueError, KeyError) as exc:
                QMessageBox.critical(dialog, "Gagal", str(exc))

        save_button.clicked.connect(_save)
        dialog.exec()

    # ------------------------------------------------------------------
    # Cetak nota & label
    # ------------------------------------------------------------------
    def print_case_invoice(self):
        case_id = self._selected_case_id()
        if case_id is None:
            QMessageBox.warning(self, "Pilih Case", "Pilih case dari tabel dulu.")
            return

        try:
            case = get_case(case_id)
        except Exception as exc:
            QMessageBox.critical(self, "Gagal", str(exc))
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Simpan Nota", f"Nota_{case.case_number}.pdf", "PDF Files (*.pdf)"
        )
        if not file_path:
            return

        try:
            generate_case_invoice(case, Path(file_path))
            self.log_action(
                "Cetak Nota", detail=f"{case.case_number} -> {file_path}",
                status="OK", serial=case.device_serial,
            )
            QDesktopServices.openUrl(QUrl.fromLocalFile(file_path))
        except Exception as exc:
            QMessageBox.critical(self, "Gagal Membuat Nota", str(exc))

    def print_case_label(self):
        case_id = self._selected_case_id()
        if case_id is None:
            QMessageBox.warning(self, "Pilih Case", "Pilih case dari tabel dulu.")
            return

        try:
            case = get_case(case_id)
        except Exception as exc:
            QMessageBox.critical(self, "Gagal", str(exc))
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Simpan Label", f"Label_{case.case_number}.pdf", "PDF Files (*.pdf)"
        )
        if not file_path:
            return

        try:
            generate_case_label(case, Path(file_path))
            self.log_action(
                "Cetak Label", detail=f"{case.case_number} -> {file_path}",
                status="OK", serial=case.device_serial,
            )
            QDesktopServices.openUrl(QUrl.fromLocalFile(file_path))
        except Exception as exc:
            QMessageBox.critical(self, "Gagal Membuat Label", str(exc))

    # ------------------------------------------------------------------
    # Notifikasi WhatsApp (link click-to-chat, bukan pengiriman otomatis)
    # ------------------------------------------------------------------
    def send_case_whatsapp_notification(self):
        case_id = self._selected_case_id()
        if case_id is None:
            QMessageBox.warning(self, "Pilih Case", "Pilih case dari tabel dulu.")
            return

        try:
            case = get_case(case_id)
        except Exception as exc:
            QMessageBox.critical(self, "Gagal", str(exc))
            return

        if not case.customer_phone.strip():
            QMessageBox.warning(
                self, "No. HP Kosong", "Case ini tidak punya nomor HP pelanggan."
            )
            return

        default_message = build_case_status_message(case)
        message, ok = QInputDialog.getMultiLineText(
            self, "Notifikasi WhatsApp",
            "Edit pesan sebelum dikirim (akan membuka WhatsApp - klik Send secara manual):",
            default_message,
        )
        if not ok or not message.strip():
            return

        try:
            link = build_whatsapp_link(case.customer_phone, message)
        except ValueError as exc:
            QMessageBox.warning(self, "Nomor Tidak Valid", str(exc))
            return

        QDesktopServices.openUrl(QUrl(link))
        self.log_action(
            "Kirim Notifikasi WA", detail=f"{case.case_number} -> {case.customer_phone}",
            status="OK", serial=case.device_serial,
        )

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
        layout.setSpacing(16)

        layout.addLayout(self._page_header(
            "Recovery Assistant",
            "Assessment read-only untuk device yang tidak bisa diakses. "
            "Nexa tidak melakukan bypass PIN/pattern/password/FRP. "
            "Gunakan verifikasi kepemilikan resmi sebelum tindakan lanjutan."
        ))

        # --------------------------------------------------------
        # Access / Recovery Assessment
        # --------------------------------------------------------
        card, card_layout = self._card_panel("Ringkasan Akses")

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
        frp_card, frp_layout = self._card_panel("FRP / Owner Verification")

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

        btn_grid = QHBoxLayout()
        btn_grid.setSpacing(8)

        self.frp_refresh_button = QPushButton(
            "🔄 Refresh FRP / Owner Verification"
        )
        self.frp_refresh_button.setObjectName("action")
        self.frp_refresh_button.clicked.connect(
            self.refresh_frp_verification
        )

        self.frp_service_refresh_button = QPushButton(
            "🔄 Refresh FRP Service State"
        )
        self.frp_service_refresh_button.setObjectName("action")
        self.frp_service_refresh_button.clicked.connect(
            self.refresh_frp_service_state
        )

        frp_layout.addWidget(self.frp_refresh_button)
        frp_layout.addWidget(self.frp_service_refresh_button)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)

        self.frp_recovery_button = QPushButton("🔁 Reboot ke Recovery")
        self.frp_recovery_button.setObjectName("action")
        self.frp_recovery_button.setEnabled(False)
        self.frp_recovery_button.clicked.connect(self.reboot_to_recovery)

        self.frp_bootloader_button = QPushButton("🔧 Reboot ke Bootloader")
        self.frp_bootloader_button.setObjectName("action")
        self.frp_bootloader_button.setEnabled(False)
        self.frp_bootloader_button.clicked.connect(
            self.reboot_to_bootloader
        )

        self.frp_verify_button = QPushButton("🛡 Verify FRP Result")
        self.frp_verify_button.setObjectName("action")
        self.frp_verify_button.setEnabled(False)
        self.frp_verify_button.clicked.connect(self.verify_frp_result_action)

        action_row.addWidget(self.frp_recovery_button)
        action_row.addWidget(self.frp_bootloader_button)
        action_row.addWidget(self.frp_verify_button)
        frp_layout.addLayout(action_row)

        layout.addWidget(frp_card)

        # --------------------------------------------------------
        # Locked Device Recovery Workflow
        # --------------------------------------------------------
        recovery_card, recovery_layout = self._card_panel("Locked Device Recovery Workflow")

        self.locked_state_label = QLabel("Locked Recovery State: -")
        self.locked_state_label.setObjectName("status")

        self.locked_identity_label = QLabel("Device Identity: -")
        self.locked_identity_label.setObjectName("value")
        self.locked_identity_label.setWordWrap(True)

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

        self.locked_detect_button = QPushButton("🔍 Detect Locked Device State")
        self.locked_detect_button.setObjectName("action")
        self.locked_detect_button.clicked.connect(self.refresh_locked_device_state)
        recovery_layout.addWidget(self.locked_detect_button)

        locked_action_row = QHBoxLayout()
        locked_action_row.setSpacing(8)

        self.locked_confirm_button = QPushButton("✅ Confirm Recovery Action")
        self.locked_confirm_button.setObjectName("action")
        self.locked_confirm_button.setEnabled(False)
        self.locked_confirm_button.clicked.connect(self.confirm_recovery_action)

        self.locked_recovery_button = QPushButton("🔁 Reboot ke Recovery")
        self.locked_recovery_button.setObjectName("action")
        self.locked_recovery_button.setEnabled(False)
        self.locked_recovery_button.clicked.connect(self.reboot_locked_recovery)

        self.locked_bootloader_button = QPushButton("🔧 Reboot ke Bootloader")
        self.locked_bootloader_button.setObjectName("action")
        self.locked_bootloader_button.setEnabled(False)
        self.locked_bootloader_button.clicked.connect(self.reboot_locked_bootloader)

        self.locked_verify_button = QPushButton("🛡 Verify Result")
        self.locked_verify_button.setObjectName("action")
        self.locked_verify_button.setEnabled(False)
        self.locked_verify_button.clicked.connect(self.verify_locked_result)

        locked_action_row.addWidget(self.locked_confirm_button)
        locked_action_row.addWidget(self.locked_recovery_button)
        locked_action_row.addWidget(self.locked_bootloader_button)
        locked_action_row.addWidget(self.locked_verify_button)
        recovery_layout.addLayout(locked_action_row)

        layout.addWidget(recovery_card)

        # --------------------------------------------------------
        # Recovery Plan
        # --------------------------------------------------------
        plan_card, plan_layout = self._card_panel("Rencana Pemulihan (Locked Device Plan)")

        self.recovery_plan_text = QTextEdit()
        self.recovery_plan_text.setObjectName("value")
        self.recovery_plan_text.setReadOnly(True)
        self.recovery_plan_text.setFixedHeight(160)
        plan_layout.addWidget(self.recovery_plan_text)

        self.recovery_refresh_button = QPushButton(
            "▶ Jalankan Assessment"
        )
        self.recovery_refresh_button.setObjectName(
            "actionPrimary"
        )
        self.recovery_refresh_button.clicked.connect(
            self.refresh_recovery_assessment
        )
        plan_layout.addWidget(self.recovery_refresh_button)

        layout.addWidget(plan_card)
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

        except FRPVerificationError as exc:
            self.frp_status_label.setText(
                "FRP Status: ERROR"
            )
            self.frp_owner_label.setText(
                "Owner Verification: UNKNOWN"
            )
            self.frp_message_label.setText(str(exc))

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
        self.frp_verify_button.setEnabled(True)
        self.frp_recovery_button.setEnabled(
            not result.owner_verification_required
        )
        self.frp_bootloader_button.setEnabled(
            not result.owner_verification_required
        )

    def _on_frp_action_complete(self, command_output: str, message: str):
        self.frp_operation_message_label.setText(
            f"Operation complete. {message}"
        )
        self.frp_verify_button.setEnabled(True)
        self.frp_recovery_button.setEnabled(True)
        self.frp_bootloader_button.setEnabled(True)

    def _on_frp_action_error(self, message: str):
        self.frp_operation_message_label.setText(
            f"Action failed: {message}"
        )
        self.frp_verify_button.setEnabled(True)
        self.frp_recovery_button.setEnabled(True)
        self.frp_bootloader_button.setEnabled(True)

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
        layout.setSpacing(16)

        layout.addLayout(self._page_header(
            "Settings", "Preferensi aplikasi Nexa Service Tool."
        ))

        card, card_layout = self._card_panel("Umum")

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

        # ------------------------------------------------------------
        # Identitas Teknisi - dipakai sebagai default di audit trail
        # (action_log), supaya tercatat siapa yang melakukan tindakan,
        # bukan cuma "Technician" generik.
        # ------------------------------------------------------------
        technician_card = QFrame()
        technician_card.setObjectName("card")
        technician_layout = QVBoxLayout(technician_card)
        technician_layout.setContentsMargins(22, 20, 22, 20)
        technician_layout.setSpacing(10)

        technician_title = QLabel("Teknisi Aktif")
        technician_title.setObjectName("cardTitle")
        technician_layout.addWidget(technician_title)

        technician_desc = QLabel(
            "Nama ini dipakai untuk mencatat siapa yang melakukan tindakan "
            "di Activity Log (Audit Trail)."
        )
        technician_desc.setObjectName("muted")
        technician_desc.setWordWrap(True)
        technician_layout.addWidget(technician_desc)

        self.settings_technician = QComboBox()
        self.settings_technician.setEditable(True)
        technician_layout.addWidget(self.settings_technician)

        layout.addWidget(technician_card)

        # ------------------------------------------------------------
        # Backup - retensi otomatis
        # ------------------------------------------------------------
        backup_card = QFrame()
        backup_card.setObjectName("card")
        backup_layout = QVBoxLayout(backup_card)
        backup_layout.setContentsMargins(22, 20, 22, 20)
        backup_layout.setSpacing(10)

        backup_title = QLabel("Backup")
        backup_title.setObjectName("cardTitle")
        backup_layout.addWidget(backup_title)

        retention_label = QLabel("Hapus otomatis file backup lokal setelah (hari, 0 = jangan hapus)")
        retention_label.setObjectName("muted")
        retention_label.setWordWrap(True)
        self.settings_backup_retention = QLineEdit()
        backup_layout.addWidget(retention_label)
        backup_layout.addWidget(self.settings_backup_retention)

        cleanup_button = QPushButton("Bersihkan Backup Lama Sekarang")
        cleanup_button.setObjectName("action")
        cleanup_button.clicked.connect(self.run_backup_cleanup)
        backup_layout.addWidget(cleanup_button)

        layout.addWidget(backup_card)

        # ------------------------------------------------------------
        # Path ADB/Fastboot manual - dipakai kalau auto-detect gagal.
        # ------------------------------------------------------------
        tools_card = QFrame()
        tools_card.setObjectName("card")
        tools_layout = QVBoxLayout(tools_card)
        tools_layout.setContentsMargins(22, 20, 22, 20)
        tools_layout.setSpacing(10)

        tools_title = QLabel("Path ADB / Fastboot Manual")
        tools_title.setObjectName("cardTitle")
        tools_layout.addWidget(tools_title)

        tools_desc = QLabel(
            "Kosongkan kalau auto-detect sudah bekerja. Isi manual kalau "
            "aplikasi tidak bisa menemukan adb.exe/fastboot.exe secara otomatis."
        )
        tools_desc.setObjectName("muted")
        tools_desc.setWordWrap(True)
        tools_layout.addWidget(tools_desc)

        adb_row = QHBoxLayout()
        self.settings_adb_path = QLineEdit()
        self.settings_adb_path.setPlaceholderText("Path ke adb.exe...")
        adb_browse = QPushButton("Cari...")
        adb_browse.setObjectName("action")
        adb_browse.clicked.connect(lambda: self._browse_tool_path(self.settings_adb_path, "adb"))
        adb_row.addWidget(self.settings_adb_path, 1)
        adb_row.addWidget(adb_browse)
        tools_layout.addWidget(QLabel("ADB"))
        tools_layout.addLayout(adb_row)

        fastboot_row = QHBoxLayout()
        self.settings_fastboot_path = QLineEdit()
        self.settings_fastboot_path.setPlaceholderText("Path ke fastboot.exe...")
        fastboot_browse = QPushButton("Cari...")
        fastboot_browse.setObjectName("action")
        fastboot_browse.clicked.connect(
            lambda: self._browse_tool_path(self.settings_fastboot_path, "fastboot")
        )
        fastboot_row.addWidget(self.settings_fastboot_path, 1)
        fastboot_row.addWidget(fastboot_browse)
        tools_layout.addWidget(QLabel("Fastboot"))
        tools_layout.addLayout(fastboot_row)

        self.settings_tools_status = QLabel("")
        self.settings_tools_status.setObjectName("muted")
        self.settings_tools_status.setWordWrap(True)
        tools_layout.addWidget(self.settings_tools_status)

        check_tools_button = QPushButton("Cek Status ADB/Fastboot")
        check_tools_button.setObjectName("action")
        check_tools_button.clicked.connect(self.check_tool_paths)
        tools_layout.addWidget(check_tools_button)

        layout.addWidget(tools_card)

        self.settings_save_button = QPushButton("Simpan Settings")
        self.settings_save_button.setObjectName("actionPrimary")
        self.settings_save_button.clicked.connect(self.save_settings_form)
        layout.addWidget(self.settings_save_button)
        layout.addStretch()

        return page

    def _browse_tool_path(self, line_edit: QLineEdit, tool_name: str):
        filter_str = "Executable (*.exe);;All Files (*)" if sys.platform == "win32" else "All Files (*)"
        path, _ = QFileDialog.getOpenFileName(self, f"Pilih {tool_name}", "", filter_str)
        if path:
            line_edit.setText(path)

    def check_tool_paths(self):
        adb_path = _resolve_adb_path()
        fastboot_path = _resolve_fastboot_path()

        adb_ok = Path(adb_path).exists()
        fastboot_ok = Path(fastboot_path).exists()

        self.settings_tools_status.setText(
            f"ADB: {'✅ ' if adb_ok else '❌ tidak ditemukan - '}{adb_path}\n"
            f"Fastboot: {'✅ ' if fastboot_ok else '❌ tidak ditemukan - '}{fastboot_path}"
        )

    def run_backup_cleanup(self):
        days = self.settings.get("backup_retention_days", 30)
        try:
            days = int(days)
        except (TypeError, ValueError):
            days = 30

        if days <= 0:
            QMessageBox.information(
                self, "Retensi Nonaktif",
                "Retensi backup di-set 0 (jangan hapus otomatis) - tidak ada yang dihapus."
            )
            return

        removed = cleanup_old_backups(Path.home() / "NexaServiceBackups", days)
        # Juga bersihkan folder mana pun yang dipilih user lewat dialog,
        # karena backup_device() menyimpan ke folder pilihan user (bukan
        # selalu ~/NexaServiceBackups) - lihat run_backup().
        if getattr(self, "_last_backup_output_dir", None):
            removed += cleanup_old_backups(Path(self._last_backup_output_dir), days)

        QMessageBox.information(
            self, "Pembersihan Selesai", f"{removed} file backup lama (> {days} hari) dihapus."
        )

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

        known = self.settings.get("known_technicians", []) or []
        active = self.settings.get("active_technician", "") or ""
        self.settings_technician.clear()
        self.settings_technician.addItems(known)
        if active and active not in known:
            self.settings_technician.addItem(active)
        idx = self.settings_technician.findText(active)
        if idx >= 0:
            self.settings_technician.setCurrentIndex(idx)
        else:
            self.settings_technician.setCurrentText(active)

        self.settings_backup_retention.setText(str(self.settings.get("backup_retention_days", 30)))
        self.settings_adb_path.setText(self.settings.get("adb_path_override", "") or "")
        self.settings_fastboot_path.setText(self.settings.get("fastboot_path_override", "") or "")

    def save_settings_form(self):
        try:
            refresh_ms = int(self.settings_refresh_ms.text().strip())
            if refresh_ms < 250:
                raise ValueError("Auto-refresh minimal 250ms.")
        except ValueError as exc:
            QMessageBox.warning(self, "Nilai Tidak Valid", str(exc) or "Auto-refresh harus berupa angka.")
            return

        try:
            retention_days = int(self.settings_backup_retention.text().strip() or "0")
            if retention_days < 0:
                raise ValueError("Retensi backup tidak boleh negatif.")
        except ValueError as exc:
            QMessageBox.warning(self, "Nilai Tidak Valid", str(exc) or "Retensi backup harus berupa angka.")
            return

        technician_name = self.settings_technician.currentText().strip()
        known = list(self.settings.get("known_technicians", []) or [])
        if technician_name and technician_name not in known:
            known.append(technician_name)

        self.settings.update({
            "auto_refresh_ms": refresh_ms,
            "log_level": self.settings_log_level.currentText(),
            "confirm_dangerous_actions": self.settings_confirm_dangerous.isChecked(),
            "mask_sensitive_identifiers": self.settings_mask_identifiers.isChecked(),
            "active_technician": technician_name,
            "known_technicians": known,
            "backup_retention_days": retention_days,
            "adb_path_override": self.settings_adb_path.text().strip(),
            "fastboot_path_override": self.settings_fastboot_path.text().strip(),
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
        layout.setSpacing(16)

        layout.addLayout(self._page_header(
            "Automation",
            "Susun langkah-langkah (macro) dan jalankan berurutan pada device aktif. "
            "Berguna untuk pekerjaan servis yang berulang."
        ))

        builder_card, builder_layout = self._card_panel("Susun Macro")

        builder_row = QHBoxLayout()
        builder_row.setSpacing(8)

        self.automation_action_combo = QComboBox()
        self.automation_action_combo.setObjectName("deviceSelector")
        self.automation_action_combo.addItems(sorted(ACTIONS.keys()))

        self.automation_param_input = QLineEdit()
        self.automation_param_input.setPlaceholderText(
            "Parameter (contoh: package=com.whatsapp atau cmd=pm list packages)"
        )

        self.automation_add_step_button = QPushButton("➕ Tambah Step")
        self.automation_add_step_button.setObjectName("action")
        self.automation_add_step_button.clicked.connect(self.add_macro_step)

        builder_row.addWidget(self.automation_action_combo)
        builder_row.addWidget(self.automation_param_input, 1)
        builder_row.addWidget(self.automation_add_step_button)

        builder_layout.addLayout(builder_row)

        self.automation_steps_list = QListWidget()
        self.automation_steps_list.setMaximumHeight(150)
        builder_layout.addWidget(self.automation_steps_list)

        step_btn_row = QHBoxLayout()
        step_btn_row.setSpacing(8)

        self.automation_remove_step_button = QPushButton("🗑 Hapus Step Terpilih")
        self.automation_remove_step_button.setObjectName("action")
        self.automation_remove_step_button.clicked.connect(self.remove_macro_step)

        self.automation_clear_steps_button = QPushButton("🧹 Kosongkan")
        self.automation_clear_steps_button.setObjectName("action")
        self.automation_clear_steps_button.clicked.connect(self.clear_macro_steps)

        step_btn_row.addWidget(self.automation_remove_step_button)
        step_btn_row.addWidget(self.automation_clear_steps_button)
        step_btn_row.addStretch()

        builder_layout.addLayout(step_btn_row)

        self.automation_run_button = QPushButton("▶ Jalankan Macro pada Device Aktif")
        self.automation_run_button.setObjectName("actionPrimary")
        self.automation_run_button.clicked.connect(self.run_macro_now)
        builder_layout.addWidget(self.automation_run_button)

        layout.addWidget(builder_card)

        log_card, log_layout = self._card_panel("Output Log")
        self.automation_log = QPlainTextEdit()
        self.automation_log.setObjectName("logConsole")
        self.automation_log.setReadOnly(True)
        self.automation_log.setMinimumHeight(200)
        log_layout.addWidget(self.automation_log)
        layout.addWidget(log_card)

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
            device_list_error = None
        except ADBError as exc:
            devices = {}
            device_list_error = str(exc)
        except Exception as exc:  # noqa: BLE001
            # Sebelumnya cuma ADBError yang ditangkap di sini - kalau ada
            # exception lain (mis. bug parsing), refresh_device_list() bisa
            # gagal diam-diam di background tanpa jejak apapun, dan dropdown
            # "ACTIVE DEVICE" jadi kelihatan macet/kosong tanpa penjelasan.
            # Sekarang semua kegagalan tak terduga dicatat supaya kelihatan.
            devices = {}
            device_list_error = f"Unexpected error: {exc}"
            logger.exception("refresh_device_list() gagal tak terduga")

        # Log status ADB HANYA saat berubah (error -> ok atau sebaliknya),
        # bukan tiap 1.5 detik - supaya tidak spam tapi tetap kelihatan
        # kalau ADB genuinely bermasalah terus-menerus.
        if device_list_error != getattr(self, "_last_device_list_error", None):
            self._last_device_list_error = device_list_error
            if device_list_error:
                self._dash_log(f"⚠ ADB devices gagal: {device_list_error}")
            elif hasattr(self, "_device_list_ever_failed") and self._device_list_ever_failed:
                self._dash_log("✅ ADB devices kembali normal.")
        if device_list_error:
            self._device_list_ever_failed = True

        # Rebuild dropdown kalau datanya berubah, ATAU ini pemanggilan
        # pertama kali - sebelumnya kalau "devices" kebetulan == {} persis
        # sama dengan self.devices awal ({}), _rebuild_device_selector()
        # TIDAK PERNAH dipanggil sama sekali, jadi dropdown-nya diam total
        # kosong (bukan cuma nampilin placeholder "Tidak ada device") dan
        # baru kepanggil kalau nanti datanya berubah jadi non-empty. Kalau
        # device sempat gagal kebaca sesaat lalu balik lagi tapi isinya
        # identik dengan snapshot terakhir yang salah, dropdown bisa nyangkut.
        first_check = not getattr(self, "_device_list_checked_once", False)
        self._device_list_checked_once = True

        if devices != self.devices or first_check:
            self.devices = devices
            self._rebuild_device_selector()

        self._connected_device_count = sum(1 for state in devices.values() if state == "device")

        if self.current_serial and self.current_serial in devices:
            if devices[self.current_serial] == "device":
                # Hanya reload info lengkap (beberapa getprop via ADB) saat
                # device ini BARU terhubung / berganti - bukan di setiap tick
                # timer. Sebelumnya ini dipanggil ulang tiap 1.5 detik terus-
                # menerus, membanjiri ADB dengan command dan bentrok dengan
                # Screen Mirror yang polling tiap 900ms - itu penyebab utama
                # mirror lag dan current_device sempat ke-reset ke None saat
                # satu request kebetulan timeout (bikin Security Check dkk
                # terlihat "tidak bisa jalan" padahal device tetap konek).
                if self._info_loaded_for != self.current_serial:
                    self.load_current_device_info()
            else:
                self._info_loaded_for = None
                self._set_no_device(
                    f"Device {self.current_serial}: {devices[self.current_serial]}"
                )
        elif self.current_serial and self.current_serial not in devices:
            self.current_serial = None
            self.current_device = None
            self._info_loaded_for = None
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
            self._info_loaded_for = self.current_serial

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

            self.refresh_dashboard_details()
            self._update_case_device_hint()

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
        self._update_case_device_hint()

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
