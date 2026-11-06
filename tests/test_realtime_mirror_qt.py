import os
import sys
import threading
import time
import types
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

pytest.importorskip("PySide6")
pytest.importorskip("av")

from PySide6.QtCore import QPoint, QThread  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from test_scrcpy_client import FakeScrcpyServer, make_packets  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _spin(app, cond, timeout=8):
    end = time.time() + timeout
    while time.time() < end and not cond():
        app.processEvents()
        time.sleep(0.01)
    return cond()


def test_realtime_mirror_delivers_qimage_on_gui_thread(app):
    from core.realtime_mirror import RealtimeMirror

    server = FakeScrcpyServer(make_packets(count=30))
    m = RealtimeMirror("FAKE", "adb", launcher=lambda: (server.port, lambda: None))
    got, started, threads = [], [], []
    m.frame_ready.connect(lambda img: (got.append(img), threads.append(QThread.currentThread())))
    m.started.connect(lambda n, w, h: started.append((n, w, h)))
    m.start()
    try:
        assert _spin(app, lambda: len(got) >= 2), "tidak ada frame diterima"
        assert started == [("Pixel Uji", 320, 240)]
        assert isinstance(got[0], QImage) and (got[0].width(), got[0].height()) == (320, 240)
        c = got[0].pixelColor(160, 120)
        assert c.red() > 180 and c.green() < 80
        assert all(t is QApplication.instance().thread() for t in threads)  # sampai di thread GUI
        m.touch_down(10, 20)
        m.touch_up(10, 20)
        assert _spin(app, lambda: len(server.control_data) >= 64)
    finally:
        m.stop()
        server.close()


def _install_fake_core_adb(monkeypatch, devices):
    """Ganti core.adb selama satu tes saja (otomatis dipulihkan oleh monkeypatch)."""
    import core

    mod = types.ModuleType("core.adb")
    mod.get_devices_with_state = lambda: devices
    mod._resolve_adb_path = lambda: "adb"
    mod.run_adb = lambda *a, **k: ""
    monkeypatch.setitem(sys.modules, "core.adb", mod)
    monkeypatch.setattr(core, "adb", mod, raising=False)


def test_panel_lists_devices_and_background_callbacks_run_in_gui_thread(app, monkeypatch):
    _install_fake_core_adb(monkeypatch, {"R58M123": "device", "192.168.1.20:5555": "device"})
    from ui.realtime_mirror_page import RealtimeMirrorPanel

    panel = RealtimeMirrorPanel()
    assert _spin(app, lambda: panel.devices.count() == 2)
    assert panel.devices.itemData(0) == "R58M123"

    seen = []
    panel._bg(lambda: threading.current_thread().name,
              lambda r: seen.append(QThread.currentThread() is QApplication.instance().thread()))
    assert _spin(app, lambda: seen)
    assert seen == [True], "callback _bg harus jalan di thread GUI"
    panel.close()


def test_video_view_coordinate_mapping(app):
    from ui.realtime_mirror_page import VideoView

    v = VideoView()
    v.resize(500, 600)
    v.set_device_size(1080, 2400)
    img = QImage(540, 1200, QImage.Format.Format_RGB888)
    img.fill(0)
    v.set_image(img)
    r = v.image_rect()
    assert r.height() == 600 and r.width() == 270 and r.x() == 115  # letterbox di tengah
    assert v._to_device(QPoint(r.x() + r.width() // 2, r.y() + r.height() // 2)) == (540, 1200)
    assert v._to_device(QPoint(5, 5)) is None  # di luar area gambar -> diabaikan
