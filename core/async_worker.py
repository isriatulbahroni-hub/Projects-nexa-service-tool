from PySide6.QtCore import QThread, Signal


class AsyncWorker(QThread):
    """
    Worker generik: jalankan fungsi apapun (biasanya operasi ADB yang blocking)
    di background thread, supaya UI (klik sidebar, dsb) tidak pernah freeze.

    Usage:
        worker = AsyncWorker(lambda: get_diagnostics(serial))
        worker.succeeded.connect(on_result)
        worker.failed.connect(on_error)
        worker.start()
    """

    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self):
        try:
            result = self._fn()
            self.succeeded.emit(result)
        except Exception as exc:  # noqa: BLE001 - diteruskan ke UI sebagai pesan
            self.failed.emit(str(exc))
