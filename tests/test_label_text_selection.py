"""Test untuk fitur: semua label yang menampilkan info device/diagnostics
/status (objectName "value"/"status"/"muted") harus bisa di-select dan
di-copy oleh user, dengan cursor berubah jadi I-beam saat hover -
sebelumnya QLabel default tidak bisa di-select sama sekali.
"""
import sys

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QLabel, QMessageBox
from PySide6.QtCore import Qt


@pytest.fixture()
def main_window():
    app = QApplication.instance() or QApplication(sys.argv)
    from app import MainWindow

    window = MainWindow()
    window.show()
    return window, app


def test_all_info_labels_are_selectable_with_correct_cursor(main_window):
    window, app = main_window

    target_names = {"value", "status", "muted"}
    labels = [l for l in window.findChildren(QLabel) if l.objectName() in target_names]

    assert len(labels) > 0, "Tidak ada label target ditemukan - cek objectName di app.py"

    for label in labels:
        flags = label.textInteractionFlags()
        assert flags & Qt.TextSelectableByMouse, (
            f"Label '{label.text()[:30]}' (objectName={label.objectName()}) belum selectable"
        )
        assert label.cursor().shape() == Qt.IBeamCursor, (
            f"Label '{label.text()[:30]}' cursor bukan I-beam"
        )


def test_dashboard_stat_card_labels_are_selectable(main_window):
    """Label di dashboard (FRP Status, Bootloader, dll) dibuat dinamis
    lewat closure make_stat_card() - pastikan tetap kena juga."""
    window, app = main_window
    window.switch_page("dashboard")

    assert window.dash_frp_value.textInteractionFlags() & Qt.TextSelectableByMouse
    assert window.dashboard_info.textInteractionFlags() & Qt.TextSelectableByMouse
