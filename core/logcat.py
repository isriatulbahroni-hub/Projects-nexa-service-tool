from PySide6.QtCore import QProcess, QObject, Signal

from .config import ADB_PATH


class LogcatStreamer(QObject):
    """
    Streaming logcat real-time menggunakan QProcess (non-blocking,
    terintegrasi dengan Qt event loop, jadi tidak membekukan GUI).
    """

    line_received = Signal(str)
    error_occurred = Signal(str)
    stopped = Signal()

    LEVEL_KEYWORDS = {
        "E": "ERROR",
        "F": "FATAL",
        "W": "WARN",
        "I": "INFO",
        "D": "DEBUG",
        "V": "VERBOSE",
    }

    def __init__(self, serial: str, parent=None):
        super().__init__(parent)
        self.serial = serial
        self.process: QProcess | None = None

    def start(self, filter_level: str = "*:V"):
        if self.process is not None:
            return

        if not ADB_PATH.exists():
            self.error_occurred.emit(f"ADB tidak ditemukan: {ADB_PATH}")
            return

        self.process = QProcess(self)
        self.process.setProgram(str(ADB_PATH))
        self.process.setArguments(
            ["-s", self.serial, "logcat", "-v", "time", filter_level]
        )
        self.process.readyReadStandardOutput.connect(self._on_stdout)
        self.process.readyReadStandardError.connect(self._on_stderr)
        self.process.finished.connect(self._on_finished)
        self.process.start()

    def stop(self):
        if self.process is not None:
            self.process.kill()
            self.process.waitForFinished(2000)
            self.process = None
            self.stopped.emit()

    def is_running(self) -> bool:
        return self.process is not None and self.process.state() == QProcess.Running

    def _on_stdout(self):
        if not self.process:
            return

        data = bytes(self.process.readAllStandardOutput()).decode(
            "utf-8", errors="replace"
        )

        for line in data.splitlines():
            if line.strip():
                self.line_received.emit(line)

    def _on_stderr(self):
        if not self.process:
            return

        data = bytes(self.process.readAllStandardError()).decode(
            "utf-8", errors="replace"
        )

        for line in data.splitlines():
            if line.strip():
                self.error_occurred.emit(line)

    def _on_finished(self):
        self.process = None
        self.stopped.emit()
