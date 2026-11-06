import socket
import struct
import sys
import threading
import time
from fractions import Fraction
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

av = pytest.importorskip("av")
np = pytest.importorskip("numpy")

from core import scrcpy_client as sc  # noqa: E402


# --------------------------------------------------------------------------
# Pengemasan pesan kontrol (ukuran harus persis sama dengan ControlMessageReader)
# --------------------------------------------------------------------------
def test_pack_sizes():
    assert len(sc.pack_touch(sc.ACTION_DOWN, 10, 20, 1080, 2400)) == 32
    assert len(sc.pack_key(sc.KEY_DOWN, 4)) == 14
    assert len(sc.pack_scroll(1, 2, 1080, 2400, 0, 1)) == 21
    assert sc.pack_back_or_screen_on(0) == b"\x04\x00"
    assert sc.pack_text("hai") == b"\x01\x00\x00\x00\x03hai"


def test_pack_touch_fields():
    msg = sc.pack_touch(sc.ACTION_MOVE, 100, 200, 1080, 2400)
    t, action, pid, x, y, w, h, pressure, abtn, btns = struct.unpack(">BBqiiHHHii", msg)
    assert (t, action, pid, x, y, w, h) == (2, 2, -2, 100, 200, 1080, 2400)
    assert pressure == 0xFFFF and abtn == 0 and btns == 0
    up = struct.unpack(">BBqiiHHHii", sc.pack_touch(sc.ACTION_UP, 1, 1, 10, 10))
    assert up[7] == 0  # tekanan 0 saat angkat jari


def test_split_text_respects_byte_limit():
    text = "é" * 400  # 2 byte per karakter
    chunks = sc.split_text(text, 300)
    assert "".join(chunks) == text
    assert all(len(c.encode()) <= 300 for c in chunks)


# --------------------------------------------------------------------------
# Server palsu yang meniru urutan byte scrcpy-server v5.0.1
# --------------------------------------------------------------------------
def _split_nals(annexb: bytes):
    idx, i = [], 0
    while True:
        j = annexb.find(b"\x00\x00\x01", i)
        if j < 0:
            break
        idx.append(j - 1 if j > 0 and annexb[j - 1] == 0 else j)
        i = j + 3
    idx.append(len(annexb))
    nals = [annexb[idx[k]:idx[k + 1]] for k in range(len(idx) - 1)]
    return nals


def _nal_type(nal: bytes) -> int:
    off = 4 if nal.startswith(b"\x00\x00\x00\x01") else 3
    return nal[off] & 0x1F


def make_packets(width=320, height=240, count=12, color=(220, 30, 30)):
    ctx = av.CodecContext.create("libx264", "w")
    ctx.width, ctx.height, ctx.pix_fmt = width, height, "yuv420p"
    ctx.time_base = Fraction(1, 30)
    ctx.options = {"preset": "ultrafast", "tune": "zerolatency", "g": "6"}
    out = []
    arr = np.zeros((height, width, 3), dtype=np.uint8)
    arr[:, :] = color
    for n in range(count):
        frame = av.VideoFrame.from_ndarray(arr, format="rgb24")
        frame.pts = n
        out += [bytes(p) for p in ctx.encode(frame)]
    out += [bytes(p) for p in ctx.encode(None)]
    return out


class FakeScrcpyServer:
    def __init__(self, packets, width=320, height=240, name="Pixel Uji"):
        self.packets = packets
        self.width, self.height, self.name = width, height, name
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(2)
        self.port = self.listener.getsockname()[1]
        self.control_data = bytearray()
        self._threads = []
        t = threading.Thread(target=self._serve, daemon=True)
        t.start()
        self._threads.append(t)

    def _serve(self):
        try:
            video, _ = self.listener.accept()
            video.sendall(b"\x00")                      # dummy byte
            control, _ = self.listener.accept()         # koneksi kontrol
            threading.Thread(target=self._read_control, args=(control,), daemon=True).start()

            video.sendall(self.name.encode().ljust(64, b"\0"))
            video.sendall(struct.pack(">I", sc.CODEC_H264))
            video.sendall(struct.pack(">III", 0x80000000, self.width, self.height))  # paket sesi

            sent_config = False
            for pkt in self.packets:
                nals = _split_nals(pkt)
                cfg = b"".join(n for n in nals if _nal_type(n) in (7, 8))
                media = b"".join(n for n in nals if _nal_type(n) not in (7, 8))
                if cfg and not sent_config:
                    video.sendall(struct.pack(">QI", sc.PACKET_FLAG_CONFIG, len(cfg)) + cfg)
                    sent_config = True
                if media:
                    video.sendall(struct.pack(">QI", 0, len(media)) + media)
                time.sleep(0.005)
            time.sleep(0.5)
            video.close()
        except OSError:
            pass

    def _read_control(self, conn):
        try:
            while True:
                d = conn.recv(4096)
                if not d:
                    return
                self.control_data += d
        except OSError:
            return

    def close(self):
        try:
            self.listener.close()
        except OSError:
            pass


def _run_client(server, wait_frames=3, timeout=10):
    events = {"frames": [], "started": None, "error": None, "stopped": threading.Event()}
    client = sc.ScrcpyClient("FAKE", "adb", launcher=lambda: (server.port, lambda: None))
    client.on_frame = lambda w, h, stride, data: events["frames"].append((w, h, stride, data))
    client.on_started = lambda n, w, h: events.__setitem__("started", (n, w, h))
    client.on_error = lambda m: events.__setitem__("error", m)
    client.on_stopped = events["stopped"].set
    client.start()
    deadline = time.time() + timeout
    while time.time() < deadline and len(events["frames"]) < wait_frames and not events["stopped"].is_set():
        time.sleep(0.05)
    return client, events


def test_client_decodes_stream_and_reports_meta():
    server = FakeScrcpyServer(make_packets())
    client, ev = _run_client(server)
    try:
        assert ev["error"] is None, ev["error"]
        assert ev["started"] == ("Pixel Uji", 320, 240)
        assert len(ev["frames"]) >= 3
        w, h, stride, data = ev["frames"][0]
        assert (w, h) == (320, 240)
        assert len(data) >= stride * h
        # piksel tengah harus merah (warna sumber 220,30,30) setelah decode
        off = (h // 2) * stride + (w // 2) * 3
        r, g, b = data[off], data[off + 1], data[off + 2]
        assert r > 180 and g < 80 and b < 80, (r, g, b)
    finally:
        client.stop()
        server.close()


def test_client_sends_control_messages():
    server = FakeScrcpyServer(make_packets(count=60))
    client, ev = _run_client(server, wait_frames=1)
    try:
        assert ev["error"] is None, ev["error"]
        client.touch(sc.ACTION_DOWN, 100, 120)
        client.touch(sc.ACTION_UP, 100, 120)
        client.key(sc.KEYCODE_HOME)
        client.text("halo")
        client.back_or_screen_on()
        time.sleep(0.4)
        expected = (
            sc.pack_touch(sc.ACTION_DOWN, 100, 120, 320, 240)
            + sc.pack_touch(sc.ACTION_UP, 100, 120, 320, 240)
            + sc.pack_key(sc.KEY_DOWN, sc.KEYCODE_HOME) + sc.pack_key(sc.KEY_UP, sc.KEYCODE_HOME)
            + sc.pack_text("halo")
            + sc.pack_back_or_screen_on(0) + sc.pack_back_or_screen_on(1)
        )
        assert bytes(server.control_data) == expected
    finally:
        client.stop()
        server.close()


def test_touch_is_clamped_to_screen():
    server = FakeScrcpyServer(make_packets(count=60))
    client, ev = _run_client(server, wait_frames=1)
    try:
        client.touch(sc.ACTION_DOWN, 99999, -5)
        time.sleep(0.3)
        assert bytes(server.control_data) == sc.pack_touch(sc.ACTION_DOWN, 319, 0, 320, 240)
    finally:
        client.stop()
        server.close()


def test_wrong_codec_reports_error():
    class BadServer(FakeScrcpyServer):
        def _serve(self):
            video, _ = self.listener.accept()
            video.sendall(b"\x00")
            control, _ = self.listener.accept()
            video.sendall(b"X".ljust(64, b"\0") + struct.pack(">I", 1))  # kode 1 = error konfigurasi
            time.sleep(0.5)

    server = BadServer([])
    client, ev = _run_client(server, wait_frames=1, timeout=5)
    try:
        assert ev["stopped"].wait(3)
        assert ev["error"] and "Codec" in ev["error"]
    finally:
        client.stop()
        server.close()


def test_stop_unblocks_client_quickly():
    server = FakeScrcpyServer(make_packets(count=200))
    client, ev = _run_client(server, wait_frames=1)
    t0 = time.time()
    client.stop()
    assert time.time() - t0 < 3
    assert ev["stopped"].wait(2)
    server.close()
