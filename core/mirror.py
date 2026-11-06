from PySide6.QtCore import QObject, QProcess, QTimer, Signal

# Tanda awal ("magic bytes") dan akhir file PNG. Dipakai untuk memvalidasi
# frame sebelum di-decode, supaya frame yang terpotong (mis. proses di-kill
# di tengah capture, atau device lambat merespons) tidak dilempar ke
# QPixmap.loadFromData() - itu penyebab spam "libpng error: Read Error" di
# console dan bikin tampilan mirror sempat kosong/glitch.
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_PNG_IEND = b"IEND\xaeB`\x82"

# Kalau satu capture ambil waktu lebih dari ini, anggap macet dan paksa
# selesai supaya tidak menumpuk dan bikin mirror terasa makin lelet seiring
# waktu berjalan.
_CAPTURE_TIMEOUT_MS = 4000


def _looks_like_complete_png(data: bytes) -> bool:
    return (
        len(data) > len(_PNG_SIGNATURE) + len(_PNG_IEND)
        and data.startswith(_PNG_SIGNATURE)
        and data.endswith(_PNG_IEND)
    )


class ScreenMirror(QObject):
    """
    Screen mirroring ringan berbasis 'adb exec-out screencap -p', di-refresh
    berkala. Ini bukan video streaming real-time seperti scrcpy, tapi cukup
    untuk keperluan remote-check tanpa dependency tambahan di luar ADB.
    """

    frame_ready = Signal(bytes)
    error_occurred = Signal(str)

    def __init__(self, serial: str, adb_path: str, parent=None):
        super().__init__(parent)
        self.serial = serial
        self.adb_path = adb_path
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._capture_frame)
        self._process: QProcess | None = None
        self._watchdog = QTimer(self)
        self._watchdog.setSingleShot(True)
        self._watchdog.timeout.connect(self._on_capture_timeout)

    def start(self, interval_ms: int = 800):
        self.timer.start(interval_ms)
        self._capture_frame()

    def stop(self):
        self.timer.stop()
        self._watchdog.stop()

        if self._process is not None:
            self._process.kill()
            self._process = None

    def is_running(self) -> bool:
        return self.timer.isActive()

    def _capture_frame(self):
        if self._process is not None and self._process.state() == QProcess.Running:
            # Capture sebelumnya belum selesai - lewati tick ini daripada
            # menumpuk proses ADB paralel (itu penyebab lag makin parah).
            return

        process = QProcess(self)
        process.setProgram(self.adb_path)
        process.setArguments(["-s", self.serial, "exec-out", "screencap", "-p"])
        process.finished.connect(lambda *_: self._on_finished(process))
        self._process = process
        process.start()
        self._watchdog.start(_CAPTURE_TIMEOUT_MS)

    def _on_capture_timeout(self):
        if self._process is not None:
            self._process.kill()
            self._process = None
            self.error_occurred.emit("Capture timeout - device lambat merespons.")

    def _on_finished(self, process: QProcess):
        self._watchdog.stop()
        data = bytes(process.readAllStandardOutput())
        err = bytes(process.readAllStandardError()).decode("utf-8", errors="replace")

        if data and _looks_like_complete_png(data):
            self.frame_ready.emit(data)
        elif err.strip():
            self.error_occurred.emit(err.strip())
        # Frame yang tidak lolos validasi PNG (terpotong/kosong) sengaja
        # dilewati diam-diam - lebih baik skip satu frame daripada crash
        # decoder atau menampilkan gambar korup.

        if self._process is process:
            self._process = None

        process.deleteLater()


def send_tap(run_adb_fn, serial: str, x: int, y: int) -> str:
    return run_adb_fn("-s", serial, "shell", "input", "tap", str(x), str(y))


def send_swipe(run_adb_fn, serial: str, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> str:
    return run_adb_fn(
        "-s", serial, "shell", "input", "swipe",
        str(x1), str(y1), str(x2), str(y2), str(duration_ms),
    )


def send_key(run_adb_fn, serial: str, keycode: str) -> str:
    return run_adb_fn("-s", serial, "shell", "input", "keyevent", keycode)


def send_text(run_adb_fn, serial: str, text: str) -> str:
    escaped = text.replace(" ", "%s")
    return run_adb_fn("-s", serial, "shell", "input", "text", escaped)
