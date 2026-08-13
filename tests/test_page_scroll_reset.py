"""Regression test - seluruh halaman (QStackedWidget) dibungkus SATU
QScrollArea yang sama (self.content_scroll). Sebelumnya switch_page()
tidak reset posisi scroll, jadi kalau user scroll ke bawah di halaman
panjang (mis. Dashboard) lalu pindah ke halaman pendek (mis. Security
Check, Screen Mirror, Firmware Flash), bagian atas halaman baru
tersembunyi di luar viewport - terlihat seperti 'ruang kosong besar'.
Ditemukan dari video rekaman testing user.
"""
import sys

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QMessageBox


@pytest.fixture()
def main_window(monkeypatch):
    app = QApplication.instance() or QApplication(sys.argv)
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))

    from app import MainWindow

    window = MainWindow()
    window.show()
    window.resize(1200, 800)
    yield window, app


def test_scroll_resets_when_switching_to_different_page(main_window):
    window, app = main_window

    window.switch_page("dashboard")
    app.processEvents()
    window.content_scroll.verticalScrollBar().setValue(400)
    assert window.content_scroll.verticalScrollBar().value() == 400

    window.switch_page("security")
    app.processEvents()

    assert window.content_scroll.verticalScrollBar().value() == 0


def test_scroll_resets_across_all_pages(main_window):
    window, app = main_window

    keys = [
        "dashboard", "device", "diagnostics", "security", "apps", "files",
        "mirror", "backup", "network", "logs", "history", "firmware",
        "hardware", "smart", "cases", "recovery", "reset", "automation",
        "settings",
    ]

    for key in keys:
        window.switch_page(key)
        app.processEvents()
        window.content_scroll.verticalScrollBar().setValue(300)
        window.switch_page(key)
        app.processEvents()
        assert window.content_scroll.verticalScrollBar().value() == 0, (
            f"Scroll tidak reset di halaman '{key}'"
        )
