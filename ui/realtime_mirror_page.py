"""
Panel Mirror Real-time (scrcpy) + koneksi ADB Wi-Fi.

Pemakaian di app.py (satu panel mandiri, punya daftar perangkat sendiri):

    from ui.realtime_mirror_page import RealtimeMirrorPanel
    panel = RealtimeMirrorPanel()
"""
from __future__ import annotations

import threading
import time

from PySide6.QtCore import QPoint, QRect, Qt, QThread, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QComboBox, QDialog, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSizePolicy, QVBoxLayout, QWidget,
)

from core import scrcpy_client as sc
from core import wireless_adb as wa
from core.realtime_mirror import RealtimeMirror


# ----------------------------------------------------------------------------
class _Worker(QThread):
    """Jalankan fungsi blocking (ADB) di luar thread GUI."""
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self):
        try:
            self.done.emit(self._fn())
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc) or exc.__class__.__name__)


# ----------------------------------------------------------------------------
class VideoView(QWidget):
    touch_down = Signal(int, int)
    touch_move = Signal(int, int)
    touch_up = Signal(int, int)
    scrolled = Signal(int, int, float, float)
    back_requested = Signal()
    typed = Signal(str)
    key_pressed = Signal(int)

    _KEYMAP = {
        Qt.Key.Key_Backspace: sc.KEYCODE_DEL,
        Qt.Key.Key_Return: sc.KEYCODE_ENTER,
        Qt.Key.Key_Enter: sc.KEYCODE_ENTER,
        Qt.Key.Key_Up: sc.KEYCODE_DPAD_UP,
        Qt.Key.Key_Down: sc.KEYCODE_DPAD_DOWN,
        Qt.Key.Key_Left: sc.KEYCODE_DPAD_LEFT,
        Qt.Key.Key_Right: sc.KEYCODE_DPAD_RIGHT,
        Qt.Key.Key_Escape: sc.KEYCODE_BACK,
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._img: QImage | None = None
        self._dev = (0, 0)
        self._down = False
        self._last_move = 0.0
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(240, 420)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_image(self, img: QImage | None):
        self._img = img
        self.update()

    def set_device_size(self, w: int, h: int):
        self._dev = (w, h)

    def image_rect(self) -> QRect:
        if self._img is None or self._img.isNull():
            return QRect()
        iw, ih = self._img.width(), self._img.height()
        scale = min(self.width() / iw, self.height() / ih)
        w, h = int(iw * scale), int(ih * scale)
        return QRect((self.width() - w) // 2, (self.height() - h) // 2, w, h)

    def _to_device(self, pos: QPoint) -> tuple[int, int] | None:
        r = self.image_rect()
        dw, dh = self._dev
        if r.isNull() or not dw or not dh or not r.contains(pos):
            return None
        x = (pos.x() - r.x()) * dw // max(1, r.width())
        y = (pos.y() - r.y()) * dh // max(1, r.height())
        return x, y

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#0b0b0b"))
        r = self.image_rect()
        if r.isNull():
            p.setPen(QColor("#777"))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Belum ada tampilan.\nPilih perangkat lalu tekan Mulai.")
        else:
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            p.drawImage(r, self._img)

    def mousePressEvent(self, e):
        self.setFocus()
        pt = self._to_device(e.position().toPoint())
        if e.button() == Qt.MouseButton.RightButton:
            self.back_requested.emit()
        elif e.button() == Qt.MouseButton.LeftButton and pt:
            self._down = True
            self.touch_down.emit(*pt)

    def mouseMoveEvent(self, e):
        if not self._down:
            return
        now = time.monotonic()
        if now - self._last_move < 0.008:  # ~120 Hz maksimum
            return
        pt = self._to_device(e.position().toPoint())
        if pt:
            self._last_move = now
            self.touch_move.emit(*pt)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._down:
            self._down = False
            pt = self._to_device(e.position().toPoint()) or (0, 0)
            self.touch_up.emit(*pt)

    def wheelEvent(self, e):
        pt = self._to_device(e.position().toPoint())
        if pt:
            self.scrolled.emit(pt[0], pt[1], 0.0, e.angleDelta().y() / 120.0)

    def keyPressEvent(self, e):
        if e.key() in self._KEYMAP:
            self.key_pressed.emit(self._KEYMAP[e.key()])
        elif e.text() and e.text().isprintable() and not (e.modifiers() & Qt.KeyboardModifier.ControlModifier):
            self.typed.emit(e.text())
        else:
            super().keyPressEvent(e)


# ----------------------------------------------------------------------------
def _qr_pixmap(payload: str, size: int = 280) -> QPixmap:
    import qrcode
    img = qrcode.make(payload, border=2).convert("RGB").resize((size, size))
    qimg = QImage(img.tobytes(), size, size, size * 3, QImage.Format.Format_RGB888).copy()
    return QPixmap.fromImage(qimg)


class QrPairDialog(QDialog):
    paired = Signal(str)
    _status_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pair HP lewat QR")
        self._cancel = threading.Event()
        self._creds = wa.new_qr_credentials()

        lay = QVBoxLayout(self)
        info = QLabel("Di HP: Opsi pengembang → Debugging nirkabel → Pasangkan perangkat dengan kode QR, "
                      "lalu pindai kode ini. HP dan PC harus di Wi-Fi yang sama.")
        info.setWordWrap(True)
        lay.addWidget(info)
        qr = QLabel()
        qr.setPixmap(_qr_pixmap(self._creds.payload))
        qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(qr)
        self.status = QLabel("Menyiapkan…")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        btn = QPushButton("Batal")
        btn.clicked.connect(self.reject)
        lay.addWidget(btn)

        self._status_changed.connect(self.status.setText)
        self._worker = _Worker(self._run, self)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _run(self):
        return wa.qr_pair(self._creds, cancel=self._cancel,
                          on_status=self._status_changed.emit)

    def _on_failed(self, msg: str):
        self.status.setText(f"Gagal: {msg}")

    def _on_done(self, address):
        self.paired.emit(str(address))
        self.accept()

    def reject(self):
        self._cancel.set()
        self._worker.wait(3000)
        super().reject()


# ----------------------------------------------------------------------------
class RealtimeMirrorPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._mirror: RealtimeMirror | None = None
        self._workers: set[_Worker] = set()
        self._preferred_serial: str | None = None

        root = QVBoxLayout(self)

        # --- baris perangkat ---
        row = QHBoxLayout()
        self.devices = QComboBox()
        self.devices.setMinimumWidth(240)
        self.btn_refresh = QPushButton("Muat ulang")
        self.btn_start = QPushButton("Mulai")
        self.btn_stop = QPushButton("Berhenti")
        self.btn_stop.setEnabled(False)
        for w in (self.devices, self.btn_refresh, self.btn_start, self.btn_stop):
            row.addWidget(w)
        row.addStretch(1)
        root.addLayout(row)

        # --- koneksi Wi-Fi ---
        box = QGroupBox("Sambungan Wi-Fi (tanpa kabel)")
        g = QVBoxLayout(box)
        r1 = QHBoxLayout()
        self.ed_addr = QLineEdit(); self.ed_addr.setPlaceholderText("IP:port  (mis. 192.168.1.20:37123)")
        self.btn_connect = QPushButton("Sambung")
        self.btn_disconnect = QPushButton("Putus")
        for w in (self.ed_addr, self.btn_connect, self.btn_disconnect):
            r1.addWidget(w)
        r2 = QHBoxLayout()
        self.ed_pair_addr = QLineEdit(); self.ed_pair_addr.setPlaceholderText("IP:port pairing")
        self.ed_code = QLineEdit(); self.ed_code.setPlaceholderText("Kode 6 digit"); self.ed_code.setMaximumWidth(120)
        self.btn_pair = QPushButton("Pair")
        for w in (self.ed_pair_addr, self.ed_code, self.btn_pair):
            r2.addWidget(w)
        r3 = QHBoxLayout()
        self.btn_qr = QPushButton("Pair via QR…")
        self.btn_usb2wifi = QPushButton("USB → Wi-Fi (perangkat terpilih)")
        r3.addWidget(self.btn_qr); r3.addWidget(self.btn_usb2wifi); r3.addStretch(1)
        for r in (r1, r2, r3):
            g.addLayout(r)
        root.addWidget(box)

        # --- video ---
        self.view = VideoView()
        root.addWidget(self.view, 1)

        # --- tombol navigasi ---
        nav = QHBoxLayout()
        self._nav = {
            "◀ Back": lambda: self._m("back"), "● Home": lambda: self._m("home"),
            "▣ Recent": lambda: self._m("recents"), "🔔 Notif": lambda: self._m("notifications"),
            "⟳ Putar": lambda: self._m("rotate"), "⏻ Power": lambda: self._m("power"),
            "Vol −": lambda: self._m("volume_down"), "Vol +": lambda: self._m("volume_up"),
        }
        for label, fn in self._nav.items():
            b = QPushButton(label)
            b.clicked.connect(fn)
            nav.addWidget(b)
        root.addLayout(nav)

        self.status = QLabel("Siap.")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        # --- sinyal ---
        self.btn_refresh.clicked.connect(self.refresh_devices)
        self.btn_start.clicked.connect(self.start_mirror)
        self.btn_stop.clicked.connect(self.stop_mirror)
        self.btn_connect.clicked.connect(self._do_connect)
        self.btn_disconnect.clicked.connect(self._do_disconnect)
        self.btn_pair.clicked.connect(self._do_pair)
        self.btn_qr.clicked.connect(self._do_qr)
        self.btn_usb2wifi.clicked.connect(self._do_usb2wifi)
        self.view.touch_down.connect(lambda x, y: self._mirror and self._mirror.touch_down(x, y))
        self.view.touch_move.connect(lambda x, y: self._mirror and self._mirror.touch_move(x, y))
        self.view.touch_up.connect(lambda x, y: self._mirror and self._mirror.touch_up(x, y))
        self.view.scrolled.connect(lambda x, y, h, v: self._mirror and self._mirror.scroll(x, y, h, v))
        self.view.back_requested.connect(lambda: self._m("back"))
        self.view.typed.connect(lambda t: self._mirror and self._mirror.text(t))
        self.view.key_pressed.connect(lambda k: self._mirror and self._mirror.key(k))

        self.refresh_devices()

    # -- util ---------------------------------------------------------------------
    def _m(self, name: str):
        if self._mirror:
            getattr(self._mirror, name)()

    def _bg(self, fn, on_ok=None):
        w = _Worker(fn, self)
        self._workers.add(w)
        w.done.connect(lambda r: (on_ok(r) if on_ok else None))
        w.failed.connect(lambda m: self.status.setText(f"Gagal: {m}"))
        w.finished.connect(lambda: self._workers.discard(w))
        w.start()

    # -- perangkat ------------------------------------------------------------------
    def refresh_devices(self):
        from core.adb import get_devices_with_state

        def done(devs: dict):
            current = self._preferred_serial or self.devices.currentData()
            self.devices.clear()
            for serial, state in devs.items():
                self.devices.addItem(f"{serial}  [{state}]", serial)
            idx = self.devices.findData(current)
            if idx >= 0:
                self.devices.setCurrentIndex(idx)
            self.status.setText(f"{len(devs)} perangkat terdeteksi." if devs else "Tidak ada perangkat. Sambungkan lewat USB atau Wi-Fi.")

        self._bg(get_devices_with_state, done)

    def select_serial(self, serial: str | None):
        """Pilih perangkat tertentu (mis. yang sedang aktif di bagian lain app)."""
        self._preferred_serial = serial or None
        idx = self.devices.findData(serial) if serial else -1
        if idx >= 0:
            self.devices.setCurrentIndex(idx)
        else:
            self.refresh_devices()

    @staticmethod
    def stream_profile(serial: str) -> dict:
        """Profil stream. Lewat Wi-Fi (serial berbentuk IP:port) bandwidth dan
        latensinya jauh lebih buruk dari USB: 8 Mbps/60 fps di Wi-Fi bikin
        paket menumpuk dan gambar terasa tertinggal beberapa detik."""
        if ":" in serial:
            return {"max_size": 960, "max_fps": 30, "bit_rate": 3_000_000}
        return {"max_size": 1280, "max_fps": 60, "bit_rate": 8_000_000}

    # -- mirror ---------------------------------------------------------------------
    def start_mirror(self):
        serial = self.devices.currentData()
        if not serial:
            self.status.setText("Pilih perangkat dulu.")
            return
        self.stop_mirror()
        from core.adb import _resolve_adb_path

        self._mirror = RealtimeMirror(serial, _resolve_adb_path(), self,
                                      **self.stream_profile(serial))
        self._mirror.frame_ready.connect(self.view.set_image)
        self._mirror.started.connect(self._on_started)
        self._mirror.resized.connect(self.view.set_device_size)
        self._mirror.error_occurred.connect(lambda m: self.status.setText(f"Error: {m}"))
        self._mirror.stopped.connect(self._on_stopped)
        self.status.setText("Menjalankan server di HP…")
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self._mirror.start()

    def stop_mirror(self):
        if self._mirror:
            m, self._mirror = self._mirror, None
            m.stop()
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)

    def _on_started(self, name: str, w: int, h: int):
        self.view.set_device_size(w, h)
        self.status.setText(f"Terhubung: {name} ({w}×{h}). Klik kiri = sentuh, klik kanan = Back, roda = scroll, ketik langsung.")
        self.view.setFocus()

    def _on_stopped(self):
        if self.sender() is not None and self.sender() is not self._mirror:
            return  # sinyal dari sesi lama yang sudah diganti
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)

    def is_mirroring(self) -> bool:
        return self._mirror is not None and self._mirror.is_running()

    # -- Wi-Fi ----------------------------------------------------------------------
    def _do_connect(self):
        addr = self.ed_addr.text()
        self.status.setText(f"Menyambung ke {addr}…")
        self._bg(lambda: wa.connect(addr), lambda a: (self.status.setText(f"Tersambung: {a}"), self.refresh_devices()))

    def _do_disconnect(self):
        addr = self.ed_addr.text().strip() or None
        self._bg(lambda: wa.disconnect(addr), lambda r: (self.status.setText(str(r) or "Diputus."), self.refresh_devices()))

    def _do_pair(self):
        addr, code = self.ed_pair_addr.text(), self.ed_code.text()
        self.status.setText("Pairing…")
        self._bg(lambda: wa.pair(addr, code), lambda _: self.status.setText("Pairing berhasil. Sekarang isi IP:port (bukan port pairing) lalu Sambung."))

    def _do_qr(self):
        dlg = QrPairDialog(self)
        dlg.paired.connect(lambda a: (self.status.setText(f"Tersambung lewat QR: {a}"), self.ed_addr.setText(a), self.refresh_devices()))
        dlg.exec()

    def _do_usb2wifi(self):
        serial = self.devices.currentData()
        if not serial or ":" in serial:
            self.status.setText("Pilih perangkat yang tersambung lewat USB.")
            return
        self.status.setText("Mengalihkan ke Wi-Fi… (jangan cabut kabel dulu)")
        self._bg(lambda: wa.usb_to_wifi(serial), lambda a: (self.status.setText(f"Tersambung Wi-Fi: {a}. Kabel boleh dicabut."), self.ed_addr.setText(a), self.refresh_devices()))

    def closeEvent(self, e):
        self.stop_mirror()
        super().closeEvent(e)
