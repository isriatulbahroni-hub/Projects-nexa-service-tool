"""
Memasang RealtimeMirrorPanel (scrcpy, stream H.264) ke halaman "Screen Mirror"
MainWindow, menggantikan versi lama yang memanggil `adb exec-out screencap -p`
tiap ~900 ms (PNG utuh per frame -> 1 fps dan lag).

Dipanggil sekali dari main.py:

    from ui.mirror_integration import install_realtime_mirror
    install_realtime_mirror(MainWindow)

Sengaja berupa patch kecil pada kelas (bukan edit app.py yang 250 KB) supaya
mudah ditinjau dan dibatalkan. `core/mirror.py` (screencap) tetap ada sebagai
cadangan dan tidak diubah.
"""
from __future__ import annotations

from ui.realtime_mirror_page import RealtimeMirrorPanel


def install_realtime_mirror(window_cls) -> None:
    if getattr(window_cls, "_realtime_mirror_installed", False):
        return

    orig_switch_page = window_cls.switch_page
    orig_close_event = window_cls.closeEvent

    def create_mirror_page(self):
        from PySide6.QtWidgets import QVBoxLayout, QWidget

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)
        layout.addLayout(self._page_header(
            "Screen Mirror",
            "Mirror real-time (stream H.264 via scrcpy) - klik/geser untuk sentuh, "
            "klik kanan = Back, roda = scroll, ketik langsung. Bisa lewat USB atau Wi-Fi.",
        ))
        card, card_layout = self._card_panel("Live Preview")
        self.realtime_mirror_panel = RealtimeMirrorPanel(self)
        card_layout.addWidget(self.realtime_mirror_panel)
        layout.addWidget(card, 1)
        return page

    def stop_mirror(self):
        panel = getattr(self, "realtime_mirror_panel", None)
        if panel is not None:
            panel.stop_mirror()

    def start_mirror(self):
        panel = getattr(self, "realtime_mirror_panel", None)
        if panel is not None:
            panel.start_mirror()

    def switch_page(self, key: str):
        panel = getattr(self, "realtime_mirror_panel", None)
        # Hentikan stream saat pindah halaman: decoder H.264 + soket tidak boleh
        # terus jalan di belakang layar.
        if key != "mirror" and panel is not None and panel.is_mirroring():
            panel.stop_mirror()
        orig_switch_page(self, key)
        if key == "mirror" and panel is not None:
            panel.select_serial(getattr(self, "current_serial", None))

    def closeEvent(self, event):
        stop_mirror(self)
        orig_close_event(self, event)

    window_cls.create_mirror_page = create_mirror_page
    window_cls.stop_mirror = stop_mirror
    window_cls.start_mirror = start_mirror
    window_cls.switch_page = switch_page
    window_cls.closeEvent = closeEvent
    window_cls._realtime_mirror_installed = True
