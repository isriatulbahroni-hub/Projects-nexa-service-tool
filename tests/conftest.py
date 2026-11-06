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

Selain itu: di akhir sesi, semua MainWindow/thread/proses/timer Qt yang
masih hidup dibereskan secara eksplisit. Tanpa ini, CI kadang selesai
"136 passed" lalu proses pytest crash saat interpreter shutdown
(Bus error / core dumped, exit code 135) karena objek Qt (QThread,
QProcess, QTimer) dihancurkan dalam urutan yang salah.
"""

import gc
import os

import pytest


def _shutdown_qt() -> None:
    """Bereskan semua objek Qt yang masih hidup sebelum interpreter exit."""
    try:
        from PySide6.QtCore import QCoreApplication, QEvent, QProcess, QThread, QTimer
        from PySide6.QtWidgets import QApplication
    except ImportError:
        return

    app = QApplication.instance()
    if app is None:
        return

    for widget in list(app.topLevelWidgets()):
        try:
            for timer in widget.findChildren(QTimer):
                timer.stop()
            for process in widget.findChildren(QProcess):
                process.kill()
                process.waitForFinished(1000)
            for thread in widget.findChildren(QThread):
                thread.quit()
                thread.wait(2000)
            widget.close()
            widget.deleteLater()
        except RuntimeError:
            # Objek C++ sudah dihancurkan - tidak ada yang perlu dibereskan.
            continue

    app.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    gc.collect()


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

    _shutdown_qt()

    for name, fn in originals.items():
        setattr(QMessageBox, name, fn)


def pytest_sessionfinish(session, exitstatus):
    session.config._nexa_exitstatus = int(exitstatus)


@pytest.hookimpl(trylast=True)
def pytest_unconfigure(config):
    # Hanya di CI (GitHub Actions menyetel CI=true): keluar langsung setelah
    # semua laporan pytest selesai ditulis, supaya crash native PySide6 saat
    # interpreter shutdown tidak mengubah hasil test yang sebenarnya lulus.
    # Lokal tidak terpengaruh.
    if os.environ.get("CI") and hasattr(config, "_nexa_exitstatus"):
        import sys

        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(config._nexa_exitstatus)
