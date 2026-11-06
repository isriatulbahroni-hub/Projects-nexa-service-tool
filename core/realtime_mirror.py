"""
Pembungkus Qt untuk ScrcpyClient. API sengaja mirip ScreenMirror (start/stop/is_running)
tetapi frame dikirim sebagai QImage dan jauh lebih cepat (stream H.264, bukan screencap).
"""
from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QImage

from . import scrcpy_client as sc
from .scrcpy_client import ScrcpyClient


class RealtimeMirror(QObject):
    frame_ready = Signal(QImage)
    started = Signal(str, int, int)   # nama perangkat, lebar, tinggi layar
    resized = Signal(int, int)
    error_occurred = Signal(str)
    stopped = Signal()
    _notify = Signal()

    def __init__(self, serial: str, adb_path: str, parent=None, **client_opts):
        super().__init__(parent)
        self._client = ScrcpyClient(serial, adb_path, **client_opts)
        self._client.on_frame = self._on_frame
        self._client.on_started = self.started.emit
        self._client.on_resized = self.resized.emit
        self._client.on_error = self.error_occurred.emit
        self._client.on_stopped = self.stopped.emit

        self._lock = threading.Lock()
        self._latest: QImage | None = None
        self._pending = False
        self._notify.connect(self._deliver, Qt.ConnectionType.QueuedConnection)

    # -- frame: hanya frame terbaru yang dikirim ke GUI (tanpa antrean latensi) ----
    def _on_frame(self, w: int, h: int, stride: int, data: bytes):
        img = QImage(data, w, h, stride, QImage.Format.Format_RGB888).copy()
        with self._lock:
            self._latest = img
            if self._pending:
                return
            self._pending = True
        self._notify.emit()

    def _deliver(self):
        with self._lock:
            img, self._latest, self._pending = self._latest, None, False
        if img is not None:
            self.frame_ready.emit(img)

    # -- siklus hidup ------------------------------------------------------------
    def start(self):
        self._client.start()

    def stop(self):
        self._client.stop()

    def is_running(self) -> bool:
        return self._client.is_running()

    @property
    def screen_size(self) -> tuple[int, int]:
        return self._client.screen_size

    # -- kontrol -----------------------------------------------------------------
    def touch_down(self, x: int, y: int):
        self._client.touch(sc.ACTION_DOWN, x, y)

    def touch_move(self, x: int, y: int):
        self._client.touch(sc.ACTION_MOVE, x, y)

    def touch_up(self, x: int, y: int):
        self._client.touch(sc.ACTION_UP, x, y)

    def scroll(self, x: int, y: int, h: float, v: float):
        self._client.scroll(x, y, h, v)

    def key(self, keycode: int):
        self._client.key(keycode)

    def text(self, text: str):
        self._client.text(text)

    def back(self):
        self._client.back_or_screen_on()

    def home(self):
        self._client.key(sc.KEYCODE_HOME)

    def recents(self):
        self._client.key(sc.KEYCODE_APP_SWITCH)

    def power(self):
        self._client.key(sc.KEYCODE_POWER)

    def volume_up(self):
        self._client.key(sc.KEYCODE_VOLUME_UP)

    def volume_down(self):
        self._client.key(sc.KEYCODE_VOLUME_DOWN)

    def notifications(self):
        self._client.expand_notifications()

    def rotate(self):
        self._client.rotate_device()
