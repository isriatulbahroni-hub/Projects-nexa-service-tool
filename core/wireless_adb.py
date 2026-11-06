"""
Koneksi ADB tanpa kabel (Android 11+ Wireless Debugging, plus mode klasik tcpip).

Semua fungsi menerima `run` (default: core.adb.run_adb) supaya mudah diuji.
"""
from __future__ import annotations

import re
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Callable

PAIRING_TYPE = "_adb-tls-pairing._tcp"
CONNECT_TYPE = "_adb-tls-connect._tcp"

_ADDR_RE = re.compile(r"^(\[[0-9a-fA-F:.]+\]|[\w.\-]+):(\d{2,5})$")
_IPV4_RE = re.compile(r"inet (\d+\.\d+\.\d+\.\d+)/")


class WirelessError(RuntimeError):
    pass


@dataclass(frozen=True)
class MdnsService:
    name: str
    service_type: str
    address: str  # host:port


def _default_run(*args: str, timeout: int = 15) -> str:
    from .adb import run_adb  # impor lambat
    return run_adb(*args, timeout=timeout)


def validate_address(address: str) -> str:
    address = address.strip()
    if not _ADDR_RE.match(address):
        raise WirelessError("Format alamat salah. Contoh: 192.168.1.20:37123")
    return address


# -- connect / disconnect / pair ----------------------------------------------
def connect(address: str, run: Callable[..., str] = _default_run) -> str:
    address = validate_address(address)
    out = run("connect", address, timeout=15)
    low = out.lower()
    # `adb connect` mengembalikan exit code 0 walau gagal, jadi baca teksnya
    if ("connected to" in low or "already connected" in low) and "failed" not in low and "cannot" not in low:
        return address
    raise WirelessError(out or f"Gagal terhubung ke {address}")


def disconnect(address: str | None = None, run: Callable[..., str] = _default_run) -> str:
    return run("disconnect", *( [validate_address(address)] if address else [] ), timeout=10)


def pair(address: str, code: str, run: Callable[..., str] = _default_run) -> str:
    address = validate_address(address)
    code = code.strip()
    if not code:
        raise WirelessError("Kode pairing kosong.")
    out = run("pair", address, code, timeout=30)
    if "successfully paired" not in out.lower():
        raise WirelessError(out or "Pairing gagal. Cek kode dan alamat (port pairing berbeda dari port connect).")
    return out


# -- mDNS --------------------------------------------------------------------
def mdns_supported(run: Callable[..., str] = _default_run) -> bool:
    try:
        out = run("mdns", "check", timeout=8).lower()
    except RuntimeError:
        return False
    return "mdns daemon" in out and "unavailable" not in out


def parse_mdns(output: str) -> list[MdnsService]:
    services = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[1].startswith("_adb"):
            services.append(MdnsService(parts[0], parts[1], parts[2]))
    return services


def list_mdns(run: Callable[..., str] = _default_run) -> list[MdnsService]:
    return parse_mdns(run("mdns", "services", timeout=10))


# -- USB -> Wi-Fi (mode klasik tcpip) ------------------------------------------
def get_device_wifi_ip(serial: str, run: Callable[..., str] = _default_run) -> str:
    for iface in ("wlan0", "wlan1"):
        try:
            out = run("-s", serial, "shell", "ip", "-f", "inet", "addr", "show", iface, timeout=10)
        except RuntimeError:
            continue
        m = _IPV4_RE.search(out)
        if m:
            return m.group(1)
    raise WirelessError("HP tidak terhubung ke Wi-Fi (IP tidak ditemukan).")


def usb_to_wifi(serial: str, port: int = 5555, run: Callable[..., str] = _default_run,
                sleep: Callable[[float], None] = time.sleep) -> str:
    """Dengan HP masih tersambung USB: buka mode TCP lalu sambung lewat Wi-Fi. Mengembalikan ip:port."""
    ip = get_device_wifi_ip(serial, run)
    run("-s", serial, "tcpip", str(port), timeout=10)
    sleep(1.5)  # adbd restart
    return connect(f"{ip}:{port}", run)


# -- Pairing lewat QR (seperti Android Studio) ----------------------------------
@dataclass(frozen=True)
class QrCredentials:
    name: str
    password: str

    @property
    def payload(self) -> str:
        # format yang dipindai HP: Pengembang > Debugging nirkabel > Pasangkan dengan kode QR
        return f"WIFI:T:ADB;S:{self.name};P:{self.password};;"


def new_qr_credentials() -> QrCredentials:
    return QrCredentials(name="NEXA-" + secrets.token_hex(3), password=secrets.token_hex(6))


def qr_pair(creds: QrCredentials, *, run: Callable[..., str] = _default_run,
            cancel: threading.Event | None = None, timeout: float = 120.0, poll: float = 1.0,
            on_status: Callable[[str], None] | None = None,
            sleep: Callable[[float], None] = time.sleep) -> str:
    """
    Tunggu HP memindai QR -> pair otomatis -> connect. Mengembalikan alamat ip:port.
    Memerlukan mDNS (satu jaringan Wi-Fi yang sama).
    """
    def status(msg: str):
        if on_status:
            on_status(msg)

    def cancelled() -> bool:
        return cancel is not None and cancel.is_set()

    deadline = time.monotonic() + timeout
    status("Menunggu HP memindai kode QR…")
    pairing: MdnsService | None = None
    while pairing is None:
        if cancelled():
            raise WirelessError("Dibatalkan.")
        if time.monotonic() > deadline:
            raise WirelessError("Waktu habis: QR belum dipindai (atau mDNS diblokir jaringan).")
        for svc in list_mdns(run):
            if svc.service_type == PAIRING_TYPE and svc.name == creds.name:
                pairing = svc
                break
        else:
            sleep(poll)

    status("QR terdeteksi, melakukan pairing…")
    pair(pairing.address, creds.password, run)

    host = pairing.address.rsplit(":", 1)[0]
    status("Pairing berhasil, menyambungkan…")
    while True:
        if cancelled():
            raise WirelessError("Dibatalkan.")
        if time.monotonic() > deadline + 30:
            raise WirelessError("Pairing berhasil, tetapi layanan connect HP tidak ditemukan. Sambungkan manual lewat IP:port.")
        for svc in list_mdns(run):
            if svc.service_type == CONNECT_TYPE and svc.address.rsplit(":", 1)[0] == host:
                return connect(svc.address, run)
        sleep(poll)
