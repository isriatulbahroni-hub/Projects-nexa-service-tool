"""Konfigurasi pytest bersama untuk seluruh test suite.

Kenapa ini perlu: beberapa test membuat instance MainWindow asli (app.py),
yang mendaftarkan QTimer.singleShot() tertunda (mis. pengecekan first-run
ADB/Fastboot di _check_first_run_tools()). Kalau test lain berjalan
sesudahnya dalam SESI PYTEST YANG SAMA (QApplication di-reuse via
QApplication.instance()), timer tertunda dari MainWindow test sebelumnya
bisa ikut nyala di tengah test lain dan memanggil QMessageBox.warning()
ASLI - yang di headless/offscreen environment akan HANG selamanya
menunggu interaksi user yang tidak akan pernah datang, bikin seluruh
test suite macet tanpa pesan error yang jelas.

Mem-patch QMessageBox di level session (bukan per-test) memastikan tidak
ada dialog modal asli yang bisa muncul dari MainWindow manapun, kapan pun
timer-nya kebetulan menyala selama sesi pytest berjalan.
"""

import pytest


@pytest.fixture(autouse=True, scope="session")
def _prevent_blocking_qt_dialogs():
    try:
        from PySide6.QtWidgets import QMessageBox
    except ImportError:
        yield
        return

    originals = {
        "warning": QMessageBox.warning,
        "information": QMessageBox.information,
        "critical": QMessageBox.critical,
        "question": QMessageBox.question,
    }

    QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.NoButton)
    QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.NoButton)
    QMessageBox.critical = staticmethod(lambda *a, **k: QMessageBox.NoButton)
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)

    yield

    for name, fn in originals.items():
        setattr(QMessageBox, name, fn)
