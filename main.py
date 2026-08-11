"""Entry point for Nexa Service Tool.

Kept separate from app.py so the GUI module can also be imported (e.g. by
tests or tools/) without side effects like launching a QApplication.

Startup sequence sebelum MainWindow muncul:
1. Cek lisensi aktif (core.licensing.is_licensed) - kalau belum, minta
   license key lewat LicenseActivationDialog.
2. Cek ada akun teknisi (core.licensing.has_any_technician) - kalau
   belum ada sama sekali, buat akun admin pertama lewat
   TechnicianSetupDialog. Kalau sudah ada, minta login lewat LoginDialog.

Kalau user membatalkan di langkah manapun, aplikasi keluar tanpa
menampilkan MainWindow sama sekali.
"""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from app import MainWindow, STYLESHEET, configure_logging, logger
from core import licensing
from ui.auth_dialogs import LicenseActivationDialog, LoginDialog, TechnicianSetupDialog


def _run_startup_gate() -> licensing.Technician | None:
    """Jalankan alur lisensi + login. Return Technician yang berhasil
    login, atau None kalau user membatalkan/gagal di langkah manapun
    (pemanggil harus keluar dari aplikasi)."""
    if not licensing.is_licensed():
        license_dialog = LicenseActivationDialog()
        if license_dialog.exec() != LicenseActivationDialog.DialogCode.Accepted:
            return None

    if not licensing.has_any_technician():
        setup_dialog = TechnicianSetupDialog()
        if setup_dialog.exec() != TechnicianSetupDialog.DialogCode.Accepted:
            return None
        return setup_dialog.technician

    login_dialog = LoginDialog()
    if login_dialog.exec() != LoginDialog.DialogCode.Accepted:
        return None
    return login_dialog.technician


def main() -> int:
    configure_logging()
    logger.info("Launching Nexa Service Tool via main.py")

    app = QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)

    technician = _run_startup_gate()
    if technician is None:
        logger.info("Startup dibatalkan di layar lisensi/login.")
        return 0

    logger.info(f"Teknisi login: {technician.username} ({technician.role})")

    window = MainWindow()
    window.set_technician(technician)
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
