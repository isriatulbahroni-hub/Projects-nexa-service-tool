from pathlib import Path

from PySide6.QtCore import QProcess, QObject, QTimer, Signal

from .config import ADB_PATH
from .tool_router import ToolRouter


_router = ToolRouter()

# Batasi seberapa sering GUI di-update dari stream logcat. Tanpa batching,
# device yang ngeluarin ratusan baris/detik (mis. verbose log dari banyak
# aplikasi latar belakang) bikin event loop Qt kebanjiran sinyal per baris,
# sehingga UI (termasuk tombol Stop) terasa tidak responsif meski secara
# teknis tidak benar-benar freeze.
_FLUSH_INTERVAL_MS = 150
# Jaga-jaga kalau device benar-benar spam log: batasi baris per flush biar
# QPlainTextEdit tidak ikut kewalahan render ribuan baris sekaligus.
_MAX_LINES_PER_FLUSH = 500


class LogcatStreamer(QObject):
    """
    Streaming logcat real-time menggunakan QProcess (non-blocking,
    terintegrasi dengan Qt event loop, jadi tidak membekukan GUI).

    Baris log di-buffer dan di-flush berkala (bukan per baris) supaya GUI
    tidak kebanjiran update saat device mengeluarkan log dalam volume besar.
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
        self._line_buffer: list[str] = []
        self._flush_timer = QTimer(self)
        self._flush_timer.setInterval(_FLUSH_INTERVAL_MS)
        self._flush_timer.timeout.connect(self._flush_buffer)

    def start(self, filter_level: str = "*:V"):
        if self.process is not None:
            return

        adb_path = _router.get_tool_path("adb")
        if adb_path is None:
            adb_path = ADB_PATH

        if not Path(adb_path).exists():
            self.error_occurred.emit(f"ADB tidak ditemukan: {adb_path}")
            return

        self.process = QProcess(self)
        self.process.setProgram(str(adb_path))
        self.process.setArguments(
            ["-s", self.serial, "logcat", "-v", "time", filter_level]
        )
        self.process.readyReadStandardOutput.connect(self._on_stdout)
        self.process.readyReadStandardError.connect(self._on_stderr)
        self.process.finished.connect(self._on_finished)
        self.process.start()
        self._flush_timer.start()

    def stop(self):
        if self.process is not None:
            self._flush_timer.stop()
            self._flush_buffer()
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
                self._line_buffer.append(line)

        # Kalau buffer sudah kepanjangan sebelum timer sempat flush (device
        # lagi spam log), flush lebih awal supaya memori tidak menumpuk.
        if len(self._line_buffer) >= _MAX_LINES_PER_FLUSH:
            self._flush_buffer()

    def _flush_buffer(self):
        if not self._line_buffer:
            return

        batch = self._line_buffer
        self._line_buffer = []
        self.line_received.emit("\n".join(batch))

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
