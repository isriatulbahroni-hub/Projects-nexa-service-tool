"""Reusable Qt background task helper.

Long-running ADB/Fastboot work should not block the PySide6 event loop.
"""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QObject, QThread, Signal


class TaskWorker(QObject):
    """Execute a callable on a QThread and expose success/error signals."""

    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable[..., Any], *args: Any, **kwargs: Any):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs

    def run(self) -> None:
        try:
            self.finished.emit(self.fn(*self.args, **self.kwargs))
        except Exception as exc:  # noqa: BLE001 - surfaced to the UI
            self.failed.emit(f"{type(exc).__name__}: {exc}")


def run_in_thread(
    parent: QObject,
    fn: Callable[..., Any],
    *args: Any,
    **kwargs: Any,
) -> tuple[QThread, TaskWorker]:
    """Start a worker thread; caller owns references until completion."""
    thread = QThread(parent)
    worker = TaskWorker(fn, *args, **kwargs)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)
    worker.failed.connect(thread.quit)
    worker.finished.connect(worker.deleteLater)
    worker.failed.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.start()
    return thread, worker
