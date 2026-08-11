"""Dialog-dialog otentikasi & lisensi, ditampilkan sebelum MainWindow
muncul (gate startup). Dipisah dari app.py supaya file itu tidak makin
membengkak dan logic-nya gampang dites terpisah.

Urutan alur (lihat main.py):
1. LicenseActivationDialog - kalau belum ada lisensi aktif di device ini.
2. TechnicianSetupDialog - kalau lisensi sudah aktif tapi belum ada
   akun teknisi sama sekali (first run).
3. LoginDialog - kalau lisensi aktif dan sudah ada akun teknisi.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from core import licensing


class LicenseActivationDialog(QDialog):
    """Ditampilkan saat belum ada lisensi aktif di device ini."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Aktivasi Lisensi - Nexa Service Tool")
        self.setModal(True)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)

        title = QLabel("Aktivasi Lisensi")
        title.setStyleSheet("font-size:18px; font-weight:700;")
        layout.addWidget(title)

        desc = QLabel(
            "Masukkan license key yang kamu terima setelah pembelian.\n"
            "Format: NEXA-xxxxxxxx-xxxxxxxxxxxx"
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("NEXA-...")
        layout.addWidget(self.key_input)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color:#ff6b6b;")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        button_row = QHBoxLayout()
        self.exit_button = QPushButton("Keluar")
        self.exit_button.clicked.connect(self.reject)
        self.activate_button = QPushButton("Aktifkan")
        self.activate_button.setDefault(True)
        self.activate_button.clicked.connect(self._on_activate)
        button_row.addWidget(self.exit_button)
        button_row.addStretch()
        button_row.addWidget(self.activate_button)
        layout.addLayout(button_row)

        self.key_input.returnPressed.connect(self._on_activate)

    def _on_activate(self):
        key = self.key_input.text().strip()
        if not key:
            self.error_label.setText("License key tidak boleh kosong.")
            return
        try:
            licensing.activate_license(key)
        except licensing.LicenseError as exc:
            self.error_label.setText(str(exc))
            return
        self.accept()


class TechnicianSetupDialog(QDialog):
    """First-run: belum ada teknisi terdaftar sama sekali di device ini,
    jadi buat akun admin pertama."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Setup Akun Admin Pertama - Nexa Service Tool")
        self.setModal(True)
        self.setMinimumWidth(420)

        self.technician: licensing.Technician | None = None

        layout = QVBoxLayout(self)

        title = QLabel("Buat Akun Admin Pertama")
        title.setStyleSheet("font-size:18px; font-weight:700;")
        layout.addWidget(title)

        desc = QLabel(
            "Belum ada akun teknisi di device ini. Buat akun admin "
            "pertama untuk mulai memakai Nexa Service Tool."
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        form = QFormLayout()
        self.username_input = QLineEdit()
        self.display_name_input = QLineEdit()
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_input = QLineEdit()
        self.confirm_input.setEchoMode(QLineEdit.EchoMode.Password)

        form.addRow("Username:", self.username_input)
        form.addRow("Nama Tampilan:", self.display_name_input)
        form.addRow("Password:", self.password_input)
        form.addRow("Konfirmasi Password:", self.confirm_input)
        layout.addLayout(form)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color:#ff6b6b;")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        button_row = QHBoxLayout()
        button_row.addStretch()
        self.create_button = QPushButton("Buat Akun")
        self.create_button.setDefault(True)
        self.create_button.clicked.connect(self._on_create)
        button_row.addWidget(self.create_button)
        layout.addLayout(button_row)

        self.confirm_input.returnPressed.connect(self._on_create)

    def _on_create(self):
        username = self.username_input.text().strip()
        display_name = self.display_name_input.text().strip() or username
        password = self.password_input.text()
        confirm = self.confirm_input.text()

        if not username:
            self.error_label.setText("Username tidak boleh kosong.")
            return
        if password != confirm:
            self.error_label.setText("Password dan konfirmasi tidak sama.")
            return

        try:
            self.technician = licensing.register_technician(
                username, password, display_name, role="admin"
            )
        except licensing.AuthError as exc:
            self.error_label.setText(str(exc))
            return

        self.accept()


class LoginDialog(QDialog):
    """Login teknisi normal (dipakai setelah setidaknya satu akun
    sudah terdaftar). Dibatasi jumlah percobaan gagal untuk mengurangi
    brute-force sederhana."""

    MAX_ATTEMPTS = 5

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Login Teknisi - Nexa Service Tool")
        self.setModal(True)
        self.setMinimumWidth(380)

        self.technician: licensing.Technician | None = None
        self._attempts = 0

        layout = QVBoxLayout(self)

        title = QLabel("Nexa Service Tool")
        title.setStyleSheet("font-size:18px; font-weight:700;")
        layout.addWidget(title)

        subtitle = QLabel("Login teknisi untuk melanjutkan.")
        layout.addWidget(subtitle)

        form = QFormLayout()
        self.username_input = QLineEdit()
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Username:", self.username_input)
        form.addRow("Password:", self.password_input)
        layout.addLayout(form)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color:#ff6b6b;")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        button_row = QHBoxLayout()
        button_row.addStretch()
        self.login_button = QPushButton("Login")
        self.login_button.setDefault(True)
        self.login_button.clicked.connect(self._on_login)
        button_row.addWidget(self.login_button)
        layout.addLayout(button_row)

        self.password_input.returnPressed.connect(self._on_login)

    def _on_login(self):
        username = self.username_input.text().strip()
        password = self.password_input.text()

        try:
            self.technician = licensing.login(username, password)
        except licensing.AuthError as exc:
            self._attempts += 1
            remaining = self.MAX_ATTEMPTS - self._attempts

            if remaining <= 0:
                self.error_label.setText(
                    "Terlalu banyak percobaan gagal. Aplikasi akan ditutup."
                )
                self.login_button.setEnabled(False)
                self.username_input.setEnabled(False)
                self.password_input.setEnabled(False)
                self.reject()
                return

            self.error_label.setText(f"{exc} ({remaining} percobaan tersisa)")
            self.password_input.clear()
            self.password_input.setFocus()
            return

        self.accept()
