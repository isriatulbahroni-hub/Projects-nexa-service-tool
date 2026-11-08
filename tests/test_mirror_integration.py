"""Halaman Screen Mirror harus memakai RealtimeMirrorPanel (scrcpy), bukan
polling screencap PNG ~900 ms yang bikin mirror lambat."""
import sys

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QMessageBox


@pytest.fixture()
def window(monkeypatch):
    app = QApplication.instance() or QApplication(sys.argv)
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))

    from app import MainWindow
    from ui.mirror_integration import install_realtime_mirror

    install_realtime_mirror(MainWindow)
    w = MainWindow()
    w.show()
    w.resize(1200, 800)
    yield w, app
    w.close()


def test_mirror_page_uses_realtime_panel(window):
    from ui.realtime_mirror_page import RealtimeMirrorPanel

    w, app = window
    assert isinstance(w.realtime_mirror_panel, RealtimeMirrorPanel)
    assert w.mirror_page.isAncestorOf(w.realtime_mirror_panel)
    assert w.screen_mirror is None  # jalur screencap lama tidak dipakai lagi


def test_install_is_idempotent():
    from app import MainWindow
    from ui.mirror_integration import install_realtime_mirror

    install_realtime_mirror(MainWindow)
    switch = MainWindow.switch_page
    install_realtime_mirror(MainWindow)
    assert MainWindow.switch_page is switch


def test_leaving_mirror_page_stops_stream(window):
    w, app = window
    calls = []
    panel = w.realtime_mirror_panel
    panel.is_mirroring = lambda: True
    panel.stop_mirror = lambda: calls.append("stop")

    w.switch_page("mirror")
    assert calls == []
    w.switch_page("dashboard")
    assert calls == ["stop"]


def test_stream_profile_is_lighter_over_wifi():
    from ui.realtime_mirror_page import RealtimeMirrorPanel

    usb = RealtimeMirrorPanel.stream_profile("R58M123ABC")
    wifi = RealtimeMirrorPanel.stream_profile("192.168.1.20:37123")
    assert wifi["bit_rate"] < usb["bit_rate"]
    assert wifi["max_fps"] < usb["max_fps"]
    assert wifi["max_size"] <= usb["max_size"]
