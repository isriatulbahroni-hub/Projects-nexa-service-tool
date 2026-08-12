"""Entry point for Nexa Service Tool.

Kept separate from app.py so the GUI module can also be imported (e.g. by
tests or tools/) without side effects like launching a QApplication.

Catatan: gate lisensi/login (core/licensing.py + ui/auth_dialogs.py)
sudah dibuat tapi SENGAJA belum diaktifkan di sini supaya development
dan ujicoba tidak terganggu. Untuk mengaktifkan lagi nanti (mis. waktu
siap dijual), tinggal panggil _run_startup_gate() di main() sebelum
MainWindow dibuat - lihat riwayat git branch fix/ui-click-responsiveness
untuk contoh implementasinya.
"""
from app import QApplication, MainWindow, STYLESHEET, configure_logging, logger
import sys


def main() -> int:
    configure_logging()
    logger.info("Launching Nexa Service Tool via main.py")

    app = QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
