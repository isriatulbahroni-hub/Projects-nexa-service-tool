"""
Klien scrcpy-server (protokol v5.0.1) murni Python.

Alur:
  1. push scrcpy-server ke HP, `adb forward` ke socket abstrak server
  2. jalankan server lewat `adb shell app_process`
  3. koneksi video (H.264) + koneksi kontrol (sentuh/tombol/teks)
  4. decode H.264 dengan PyAV, kirim frame RGB lewat callback

Modul ini TIDAK bergantung pada Qt supaya mudah diuji. Pembungkus Qt ada di
core/realtime_mirror.py.
"""
from __future__ import annotations

import hashlib
import os
import secrets
import shutil
import select
import socket
import struct
import subprocess
import sys
import threading
import time
import urllib.request
from collections import deque
from pathlib import Path
from typing import Callable

SCRCPY_VERSION = "5.0.1"
SERVER_SHA256 = "764eb6f79811d5211fe9df341120882ba9994c7a61b897d7bf3fb662e53bc536"
SERVER_URL = (
    f"https://github.com/Genymobile/scrcpy/releases/download/"
    f"v{SCRCPY_VERSION}/scrcpy-server-v{SCRCPY_VERSION}"
)
REMOTE_JAR = "/data/local/tmp/nexa-scrcpy-server.jar"


def _default_vendor_dir() -> Path:
    """Lokasi cache scrcpy-server.

    Saat jalan dari source: folder `vendor/` di samping proyek. Saat dibungkus
    PyInstaller (--onefile), folder program adalah direktori temp yang dihapus
    tiap aplikasi ditutup - server 70 KB akan diunduh ulang setiap kali Mulai
    (lambat, dan gagal total kalau PC offline). Karena itu pakai folder data
    pengguna yang permanen.
    """
    if getattr(sys, "frozen", False):
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME") \
            or str(Path.home() / ".local" / "share")
        return Path(base) / "NexaServiceTool" / "vendor"
    return Path(__file__).resolve().parent.parent / "vendor"


VENDOR_DIR = _default_vendor_dir()

CODEC_H264 = 0x68323634  # "h264"
PACKET_FLAG_CONFIG = 1 << 62
PACKET_FLAG_KEY_FRAME = 1 << 61

# --- tipe pesan kontrol (ControlMessage.java) ---
TYPE_INJECT_KEYCODE = 0
TYPE_INJECT_TEXT = 1
TYPE_INJECT_TOUCH_EVENT = 2
TYPE_INJECT_SCROLL_EVENT = 3
TYPE_BACK_OR_SCREEN_ON = 4
TYPE_EXPAND_NOTIFICATION_PANEL = 5
TYPE_COLLAPSE_PANELS = 7
TYPE_SET_DISPLAY_POWER = 10
TYPE_ROTATE_DEVICE = 11

ACTION_DOWN, ACTION_UP, ACTION_MOVE = 0, 1, 2
KEY_DOWN, KEY_UP = 0, 1
POINTER_ID_GENERIC_FINGER = -2  # jari biasa (bukan mouse)
INJECT_TEXT_MAX_LENGTH = 300

# keycode Android yang sering dipakai
KEYCODE_HOME = 3
KEYCODE_BACK = 4
KEYCODE_DPAD_UP, KEYCODE_DPAD_DOWN, KEYCODE_DPAD_LEFT, KEYCODE_DPAD_RIGHT = 19, 20, 21, 22
KEYCODE_VOLUME_UP, KEYCODE_VOLUME_DOWN = 24, 25
KEYCODE_POWER = 26
KEYCODE_ENTER = 66
KEYCODE_DEL = 67
KEYCODE_APP_SWITCH = 187


class ScrcpyError(RuntimeError):
    pass


# ----------------------------------------------------------------------------
# Server jar
# ----------------------------------------------------------------------------
def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_server_jar(dest_dir: Path = VENDOR_DIR, url: str = SERVER_URL,
                      sha256: str = SERVER_SHA256) -> Path:
    """Pastikan scrcpy-server ada di vendor/ (unduh sekali, verifikasi SHA-256)."""
    path = dest_dir / f"scrcpy-server-v{SCRCPY_VERSION}"
    if path.exists() and _sha256(path) == sha256:
        return path

    dest_dir.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    try:
        with urllib.request.urlopen(url, timeout=30) as resp, open(tmp, "wb") as out:
            shutil.copyfileobj(resp, out)
    except OSError as exc:
        raise ScrcpyError(
            f"Gagal mengunduh scrcpy-server: {exc}. Unduh manual dari {url} "
            f"lalu letakkan di {dest_dir}"
        ) from exc

    if _sha256(tmp) != sha256:
        tmp.unlink(missing_ok=True)
        raise ScrcpyError("Checksum scrcpy-server tidak cocok; file ditolak.")
    tmp.replace(path)
    return path


# ----------------------------------------------------------------------------
# Pengemasan pesan kontrol (big-endian, sesuai ControlMessageReader.java)
# ----------------------------------------------------------------------------
def pack_touch(action: int, x: int, y: int, screen_w: int, screen_h: int,
               pointer_id: int = POINTER_ID_GENERIC_FINGER, pressure: float | None = None) -> bytes:
    if pressure is None:
        pressure = 0.0 if action == ACTION_UP else 1.0
    p = max(0, min(0xFFFF, int(pressure * 0xFFFF)))
    return struct.pack(">BBqiiHHHii", TYPE_INJECT_TOUCH_EVENT, action, pointer_id,
                       x, y, screen_w, screen_h, p, 0, 0)


def pack_key(action: int, keycode: int, repeat: int = 0, meta: int = 0) -> bytes:
    return struct.pack(">BBiii", TYPE_INJECT_KEYCODE, action, keycode, repeat, meta)


def pack_text(text: str) -> bytes:
    data = text.encode("utf-8")
    return struct.pack(">BI", TYPE_INJECT_TEXT, len(data)) + data


def pack_scroll(x: int, y: int, screen_w: int, screen_h: int, hscroll: float, vscroll: float) -> bytes:
    def fixed(v: float) -> int:  # rentang efektif [-16, 16] -> int16
        return max(-32768, min(32767, int(v / 16.0 * 32767)))
    return struct.pack(">BiiHHhhi", TYPE_INJECT_SCROLL_EVENT, x, y, screen_w, screen_h,
                       fixed(hscroll), fixed(vscroll), 0)


def pack_back_or_screen_on(action: int) -> bytes:
    return struct.pack(">BB", TYPE_BACK_OR_SCREEN_ON, action)


def pack_simple(msg_type: int) -> bytes:
    return struct.pack(">B", msg_type)


def pack_display_power(on: bool) -> bytes:
    return struct.pack(">BB", TYPE_SET_DISPLAY_POWER, 1 if on else 0)


def split_text(text: str, limit: int = INJECT_TEXT_MAX_LENGTH) -> list[str]:
    """Pecah teks agar tiap potongan <= limit byte UTF-8."""
    chunks, cur, size = [], [], 0
    for ch in text:
        n = len(ch.encode("utf-8"))
        if size + n > limit:
            chunks.append("".join(cur))
            cur, size = [], 0
        cur.append(ch)
        size += n
    if cur:
        chunks.append("".join(cur))
    return chunks


# ----------------------------------------------------------------------------
# Klien
# ----------------------------------------------------------------------------
def _recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Koneksi ke HP terputus.")
        buf += chunk
    return bytes(buf)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _has_pending_data(sock: socket.socket | None) -> bool:
    if sock is None:
        return False
    try:
        readable, _, _ = select.select([sock], [], [], 0)
    except (OSError, ValueError):
        return False
    return bool(readable)


def _configure_low_latency(decoder) -> None:
    """Matikan buffering internal decoder H.264 (frame-threading menahan beberapa
    frame sebelum keluar = delay tambahan yang terasa sebagai 'lambat').
    Dibungkus try karena nama opsi bisa beda antar versi PyAV/FFmpeg."""
    try:
        decoder.thread_type = "SLICE"
    except Exception:  # noqa: BLE001
        pass
    try:
        decoder.options = {"flags": "low_delay", "flags2": "fast"}
    except Exception:  # noqa: BLE001
        pass


class ScrcpyClient:
    """
    Callback (dipanggil dari thread pekerja, bukan thread GUI):
      on_started(device_name, width, height)
      on_resized(width, height)            # mis. layar diputar
      on_frame(width, height, stride, rgb_bytes)
      on_error(message)
      on_stopped()

    `launcher` (opsional, untuk pengujian) adalah callable tanpa argumen yang
    mengembalikan (port_lokal, fungsi_cleanup).
    """

    def __init__(self, serial: str, adb_path: str, *, run_adb: Callable[..., str] | None = None,
                 max_size: int = 1280, max_fps: int = 60, bit_rate: int = 8_000_000,
                 launcher: Callable[[], tuple[int, Callable[[], None]]] | None = None):
        self.serial = serial
        self.adb_path = adb_path
        self._run_adb = run_adb
        self.max_size = max_size
        self.max_fps = max_fps
        self.bit_rate = bit_rate
        self._launcher = launcher

        self.on_started: Callable[[str, int, int], None] | None = None
        self.on_resized: Callable[[int, int], None] | None = None
        self.on_frame: Callable[[int, int, int, bytes], None] | None = None
        self.on_error: Callable[[str], None] | None = None
        self.on_stopped: Callable[[], None] | None = None

        self.device_name = ""
        self.screen_size = (0, 0)

        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._vsock: socket.socket | None = None
        self._csock: socket.socket | None = None
        self._ctl_lock = threading.Lock()
        self._cleanup: Callable[[], None] | None = None
        self._server_log: deque[str] = deque(maxlen=20)
        self._server_proc: subprocess.Popen | None = None

    # -- siklus hidup ---------------------------------------------------------
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self):
        if self.is_running():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="scrcpy-client", daemon=True)
        self._thread.start()

    def stop(self, join_timeout: float = 3.0):
        self._stop.set()
        self._close_sockets()
        t = self._thread
        if t is not None and t is not threading.current_thread():
            t.join(join_timeout)

    def _close_sockets(self):
        for s in (self._vsock, self._csock):
            if s is not None:
                try:
                    s.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                try:
                    s.close()
                except OSError:
                    pass

    # -- peluncuran server lewat ADB -------------------------------------------
    def _adb(self, *args: str, timeout: int = 20) -> str:
        if self._run_adb is None:
            from .adb import run_adb  # impor lambat: modul ini tetap bisa diuji tanpa ADB
            self._run_adb = run_adb
        return self._run_adb(*args, timeout=timeout)

    def _adb_launch(self) -> tuple[int, Callable[[], None]]:
        jar = ensure_server_jar()
        self._adb("-s", self.serial, "push", str(jar), REMOTE_JAR, timeout=60)

        scid = secrets.randbits(31)
        port = _free_port()
        self._adb("-s", self.serial, "forward", f"tcp:{port}", f"localabstract:scrcpy_{scid:08x}")

        args = [
            self.adb_path, "-s", self.serial, "shell",
            f"CLASSPATH={REMOTE_JAR}", "app_process", "/", "com.genymobile.scrcpy.Server",
            SCRCPY_VERSION,
            f"scid={scid:08x}", "log_level=info",
            "video=true", "audio=false", "control=true",
            "video_codec=h264",
            f"max_size={self.max_size}", f"max_fps={self.max_fps}",
            f"video_bit_rate={self.bit_rate}",
            "tunnel_forward=true", "clipboard_autosync=false",
        ]
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, errors="replace", creationflags=flags)
        self._server_proc = proc

        def pump():
            for line in proc.stdout:  # type: ignore[union-attr]
                self._server_log.append(line.rstrip())
        threading.Thread(target=pump, name="scrcpy-server-log", daemon=True).start()

        def cleanup():
            try:
                if proc.poll() is None:
                    proc.kill()
            except OSError:
                pass
            try:
                self._adb("-s", self.serial, "forward", "--remove", f"tcp:{port}", timeout=5)
            except Exception:
                pass

        return port, cleanup

    # -- koneksi ---------------------------------------------------------------
    def _server_died(self) -> bool:
        return self._server_proc is not None and self._server_proc.poll() is not None

    def _connect_video(self, port: int, timeout: float = 10.0) -> socket.socket:
        """Forward ADB menerima TCP lebih dulu; server siap jika dummy byte terbaca."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and not self._stop.is_set():
            if self._server_died():
                raise ScrcpyError("Server di HP berhenti: " + " | ".join(self._server_log))
            s = None
            try:
                s = socket.create_connection(("127.0.0.1", port), timeout=2)
                s.settimeout(2)
                if s.recv(1):
                    s.settimeout(None)
                    return s
            except OSError:
                pass
            if s is not None:
                try:
                    s.close()
                except OSError:
                    pass
            time.sleep(0.1)
        if self._stop.is_set():
            raise ConnectionAbortedError("dibatalkan")
        raise ScrcpyError("Server di HP tidak merespons. " + " | ".join(self._server_log))

    # -- loop utama ------------------------------------------------------------
    def _run(self):
        try:
            port, self._cleanup = (self._launcher or self._adb_launch)()
            self._vsock = self._connect_video(port)
            self._csock = socket.create_connection(("127.0.0.1", port), timeout=5)
            self._csock.settimeout(None)
            self._csock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            threading.Thread(target=self._drain_control, name="scrcpy-ctl-drain", daemon=True).start()

            self.device_name = _recv_exact(self._vsock, 64).split(b"\0", 1)[0].decode("utf-8", "replace")
            codec_id = struct.unpack(">I", _recv_exact(self._vsock, 4))[0]
            if codec_id != CODEC_H264:
                raise ScrcpyError(f"Codec tidak didukung/stream dinonaktifkan oleh server (kode {codec_id:#x}).")

            self._decode_loop()
        except Exception as exc:  # noqa: BLE001
            if not self._stop.is_set() and self.on_error:
                self.on_error(str(exc) or exc.__class__.__name__)
        finally:
            self._stop.set()
            self._close_sockets()
            if self._cleanup:
                try:
                    self._cleanup()
                except Exception:  # noqa: BLE001
                    pass
            if self.on_stopped:
                self.on_stopped()

    def _decode_loop(self):
        try:
            import av
        except ImportError as exc:
            raise ScrcpyError("Library 'av' (PyAV) belum terpasang. Jalankan: pip install av") from exc

        decoder = av.CodecContext.create("h264", "r")
        _configure_low_latency(decoder)
        config: bytes | None = None
        started = False
        skipped = 0  # berapa frame beruntun yang konversi RGB-nya dilewati

        while not self._stop.is_set():
            header = _recv_exact(self._vsock, 12)

            if header[0] & 0x80:  # paket sesi: ukuran layar (awal / rotasi)
                w, h = struct.unpack(">II", header[4:12])
                self.screen_size = (w, h)
                if not started:
                    started = True
                    if self.on_started:
                        self.on_started(self.device_name, w, h)
                elif self.on_resized:
                    self.on_resized(w, h)
                continue

            pts_flags, size = struct.unpack(">QI", header)
            payload = _recv_exact(self._vsock, size)

            if pts_flags & PACKET_FLAG_CONFIG:
                config = payload  # SPS/PPS digabung dengan paket media berikutnya
                continue
            if config is not None:
                payload = config + payload
                config = None

            last = None
            for frame in decoder.decode(av.Packet(payload)):
                last = frame
            if last is None:
                continue

            # Kalau masih ada paket menunggu di socket, berarti PC tertinggal dari
            # HP. Frame ini pasti akan segera tertimpa, jadi lewati konversi RGB
            # (bagian paling mahal) agar decoder mengejar - dibatasi 4 frame
            # beruntun supaya layar tetap bergerak.
            if skipped < 4 and _has_pending_data(self._vsock):
                skipped += 1
                continue
            skipped = 0

            rgb = last.reformat(format="rgb24")
            plane = rgb.planes[0]
            if self.on_frame:
                self.on_frame(rgb.width, rgb.height, plane.line_size, bytes(plane))

    def _drain_control(self):
        """Pesan dari HP (mis. clipboard) dibuang agar buffer tidak penuh."""
        s = self._csock
        try:
            while s is not None and not self._stop.is_set():
                if not s.recv(4096):
                    return
        except OSError:
            return

    # -- kontrol ---------------------------------------------------------------
    def _send(self, data: bytes) -> bool:
        s = self._csock
        if s is None or self._stop.is_set():
            return False
        try:
            with self._ctl_lock:
                s.sendall(data)
            return True
        except OSError:
            return False

    def touch(self, action: int, x: int, y: int) -> bool:
        w, h = self.screen_size
        if not w or not h:
            return False
        x = max(0, min(w - 1, int(x)))
        y = max(0, min(h - 1, int(y)))
        return self._send(pack_touch(action, x, y, w, h))

    def tap(self, x: int, y: int):
        self.touch(ACTION_DOWN, x, y)
        self.touch(ACTION_UP, x, y)

    def key(self, keycode: int):
        self._send(pack_key(KEY_DOWN, keycode) + pack_key(KEY_UP, keycode))

    def text(self, text: str):
        for chunk in split_text(text):
            self._send(pack_text(chunk))

    def scroll(self, x: int, y: int, hscroll: float, vscroll: float):
        w, h = self.screen_size
        if w and h:
            self._send(pack_scroll(x, y, w, h, hscroll, vscroll))

    def back_or_screen_on(self):
        self._send(pack_back_or_screen_on(KEY_DOWN) + pack_back_or_screen_on(KEY_UP))

    def expand_notifications(self):
        self._send(pack_simple(TYPE_EXPAND_NOTIFICATION_PANEL))

    def collapse_panels(self):
        self._send(pack_simple(TYPE_COLLAPSE_PANELS))

    def rotate_device(self):
        self._send(pack_simple(TYPE_ROTATE_DEVICE))

    def set_display_power(self, on: bool):
        self._send(pack_display_power(on))
