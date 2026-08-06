import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.adb import get_devices
from core.device import get_device_info


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Nexa Service Tool")
        self.resize(1050, 680)

        self.current_device = None

        self.setStyleSheet("""
            QMainWindow {
                background: #111318;
            }

            QLabel {
                color: #e8eaed;
            }

            #sidebar {
                background: #181b21;
                border-right: 1px solid #2b2f36;
            }

            #brand {
                font-size: 22px;
                font-weight: 700;
            }

            #subtitle, #muted {
                color: #8b929e;
                font-size: 12px;
            }

            QPushButton {
                background: transparent;
                color: #c9ced6;
                border: none;
                text-align: left;
                padding: 11px 14px;
                border-radius: 7px;
                font-size: 14px;
            }

            QPushButton:hover {
                background: #242932;
                color: white;
            }

            QPushButton:disabled {
                color: #555b65;
            }

            #contentTitle {
                font-size: 26px;
                font-weight: 700;
            }

            #card {
                background: #191c22;
                border: 1px solid #2b2f36;
                border-radius: 12px;
            }

            #cardTitle {
                font-size: 16px;
                font-weight: 600;
            }

            #status {
                font-size: 15px;
                font-weight: 600;
            }

            #value {
                color: white;
                font-size: 14px;
            }

            #action {
                background: #242932;
                color: white;
                border: 1px solid #353b45;
                text-align: center;
                padding: 10px 16px;
            }

            #action:hover {
                background: #303640;
            }
        """)

        self.build_ui()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_device)
        self.timer.start(1000)

        self.refresh_device()

    def build_ui(self):
        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(220)

        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(18, 24, 18, 18)
        side_layout.setSpacing(7)

        brand = QLabel("Nexa Service Tool")
        brand.setObjectName("brand")

        subtitle = QLabel("Professional Service Center")
        subtitle.setObjectName("subtitle")

        side_layout.addWidget(brand)
        side_layout.addWidget(subtitle)
        side_layout.addSpacing(25)

        dashboard_btn = QPushButton("Dashboard")
        device_btn = QPushButton("Device")
        diagnostics_btn = QPushButton("Diagnostics")
        firmware_btn = QPushButton("Firmware")
        service_btn = QPushButton("Service")
        logs_btn = QPushButton("Logs")

        side_layout.addWidget(dashboard_btn)
        side_layout.addWidget(device_btn)
        side_layout.addWidget(diagnostics_btn)
        side_layout.addWidget(firmware_btn)
        side_layout.addWidget(service_btn)
        side_layout.addWidget(logs_btn)
        side_layout.addStretch()

        version = QLabel("Nexa Service Tool v0.1")
        version.setObjectName("subtitle")
        side_layout.addWidget(version)

        self.pages = QStackedWidget()

        self.dashboard_page = self.create_dashboard_page()
        self.device_page = self.create_device_page()

        self.pages.addWidget(self.dashboard_page)
        self.pages.addWidget(self.device_page)

        dashboard_btn.clicked.connect(
            lambda: self.pages.setCurrentWidget(self.dashboard_page)
        )
        device_btn.clicked.connect(
            lambda: self.pages.setCurrentWidget(self.device_page)
        )

        root_layout.addWidget(sidebar)
        root_layout.addWidget(self.pages)

        self.setCentralWidget(root)

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

        card = QFrame()
        card.setObjectName("card")

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(22, 20, 22, 20)

        card_title = QLabel("Connected Device")
        card_title.setObjectName("cardTitle")

        self.dashboard_status = QLabel("Checking...")
        self.dashboard_status.setObjectName("status")

        self.dashboard_info = QLabel("")

        card_layout.addWidget(card_title)
        card_layout.addWidget(self.dashboard_status)
        card_layout.addWidget(self.dashboard_info)

        layout.addWidget(card)
        layout.addStretch()

        return page

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
        self.bootloader_button.setObjectName("action")
        self.bootloader_button.setEnabled(False)

        actions_layout.addWidget(actions_title)
        actions_layout.addWidget(self.refresh_button)
        actions_layout.addWidget(self.reboot_button)
        actions_layout.addWidget(self.recovery_button)
        actions_layout.addWidget(self.bootloader_button)

        layout.addWidget(actions)
        layout.addStretch()

        self.refresh_button.clicked.connect(self.refresh_device)

        return page

    def refresh_device(self):
        try:
            devices = get_devices()

            if not devices:
                self.current_device = None

                self.dashboard_status.setText("? No device connected")
                self.dashboard_info.setText(
                    "Connect an Android device via USB\n"
                    "and enable USB debugging."
                )

                self.device_status.setText("? No device connected")
                self.device_info.setText(
                    "No Android device detected."
                )

                self.reboot_button.setEnabled(False)
                self.recovery_button.setEnabled(False)
                self.bootloader_button.setEnabled(False)
                return

            device = get_device_info(devices[0])
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

        except Exception as exc:
            self.current_device = None

            self.dashboard_status.setText("? Detection error")
            self.dashboard_info.setText(str(exc))

            self.device_status.setText("? Detection error")
            self.device_info.setText(str(exc))

            self.reboot_button.setEnabled(False)
            self.recovery_button.setEnabled(False)
            self.bootloader_button.setEnabled(False)


if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())
