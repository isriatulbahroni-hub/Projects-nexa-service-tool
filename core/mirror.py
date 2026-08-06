from PySide6.QtCore import QObject, QProcess, QTimer, Signal


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

    def start(self, interval_ms: int = 800):
        self.timer.start(interval_ms)
        self._capture_frame()

    def stop(self):
        self.timer.stop()

        if self._process is not None:
            self._process.kill()
            self._process = None

    def is_running(self) -> bool:
        return self.timer.isActive()

    def _capture_frame(self):
        if self._process is not None and self._process.state() == QProcess.Running:
            return

        process = QProcess(self)
        process.setProgram(self.adb_path)
        process.setArguments(["-s", self.serial, "exec-out", "screencap", "-p"])
        process.finished.connect(lambda *_: self._on_finished(process))
        self._process = process
        process.start()

    def _on_finished(self, process: QProcess):
        data = bytes(process.readAllStandardOutput())
        err = bytes(process.readAllStandardError()).decode("utf-8", errors="replace")

        if data:
            self.frame_ready.emit(data)
        elif err.strip():
            self.error_occurred.emit(err.strip())

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
