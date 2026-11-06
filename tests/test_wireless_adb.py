import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import wireless_adb as wa  # noqa: E402

MDNS_OUT = (
    "List of discovered mdns services\n"
    "NEXA-abc123\t_adb-tls-pairing._tcp\t192.168.1.20:41233\n"
    "adb-R58M123-xYz\t_adb-tls-connect._tcp\t192.168.1.20:37123\n"
    "adb-OTHER-qqq\t_adb-tls-connect._tcp\t192.168.1.99:40000\n"
)


class FakeAdb:
    """Mencatat perintah dan mengembalikan output sesuai skenario."""

    def __init__(self, responses=None):
        self.calls = []
        self.responses = responses or {}

    def __call__(self, *args, timeout=15):
        self.calls.append(args)
        for key, val in self.responses.items():
            if args[: len(key)] == key:
                if isinstance(val, Exception):
                    raise val
                return val(args) if callable(val) else val
        return ""


def test_parse_mdns():
    s = wa.parse_mdns(MDNS_OUT)
    assert len(s) == 3
    assert s[0] == wa.MdnsService("NEXA-abc123", wa.PAIRING_TYPE, "192.168.1.20:41233")


@pytest.mark.parametrize("bad", ["", "192.168.1.20", "abc:xyz", "1.2.3.4:1", "1.2.3.4:99999x"])
def test_validate_address_rejects(bad):
    with pytest.raises(wa.WirelessError):
        wa.validate_address(bad)


def test_validate_address_ok():
    assert wa.validate_address(" 192.168.1.20:37123 ") == "192.168.1.20:37123"
    assert wa.validate_address("[fe80::1]:5555") == "[fe80::1]:5555"


def test_connect_success_and_failure_text():
    ok = FakeAdb({("connect",): "connected to 192.168.1.20:5555"})
    assert wa.connect("192.168.1.20:5555", ok) == "192.168.1.20:5555"
    again = FakeAdb({("connect",): "already connected to 192.168.1.20:5555"})
    assert wa.connect("192.168.1.20:5555", again)
    # adb connect keluar dengan kode 0 walau gagal -> harus dibaca dari teks
    bad = FakeAdb({("connect",): "failed to connect to '192.168.1.20:5555': Connection refused"})
    with pytest.raises(wa.WirelessError):
        wa.connect("192.168.1.20:5555", bad)


def test_pair_requires_success_text():
    ok = FakeAdb({("pair",): "Successfully paired to 192.168.1.20:41233 [guid=adb-xx]"})
    assert "Successfully paired" in wa.pair("192.168.1.20:41233", "123456", ok)
    assert ok.calls[0] == ("pair", "192.168.1.20:41233", "123456")
    bad = FakeAdb({("pair",): "Failed: Wrong password or connection was dropped."})
    with pytest.raises(wa.WirelessError):
        wa.pair("192.168.1.20:41233", "000000", bad)
    with pytest.raises(wa.WirelessError):
        wa.pair("192.168.1.20:41233", "  ", ok)


def test_usb_to_wifi_flow():
    adb = FakeAdb({
        ("-s", "SER", "shell", "ip"): "3: wlan0    inet 192.168.1.20/24 brd 192.168.1.255 scope global wlan0",
        ("-s", "SER", "tcpip"): "restarting in TCP mode port: 5555",
        ("connect",): "connected to 192.168.1.20:5555",
    })
    assert wa.usb_to_wifi("SER", run=adb, sleep=lambda _: None) == "192.168.1.20:5555"
    assert ("-s", "SER", "tcpip", "5555") in adb.calls


def test_usb_to_wifi_no_wifi():
    adb = FakeAdb({("-s", "SER", "shell", "ip"): ""})
    with pytest.raises(wa.WirelessError):
        wa.usb_to_wifi("SER", run=adb, sleep=lambda _: None)


def test_qr_payload_and_credentials_unique():
    a, b = wa.new_qr_credentials(), wa.new_qr_credentials()
    assert a.name != b.name and a.password != b.password
    assert a.payload == f"WIFI:T:ADB;S:{a.name};P:{a.password};;"


def test_qr_pair_full_flow():
    creds = wa.QrCredentials("NEXA-abc123", "secret123456")
    state = {"scans": 0}

    def mdns(_args):
        state["scans"] += 1
        if state["scans"] < 3:
            return "List of discovered mdns services\n"      # QR belum dipindai
        if state["scans"] < 5:
            return MDNS_OUT.split("adb-R58")[0]               # baru ada layanan pairing
        return MDNS_OUT                                        # connect service muncul

    adb = FakeAdb({
        ("mdns", "services"): mdns,
        ("pair",): "Successfully paired to 192.168.1.20:41233",
        ("connect",): "connected to 192.168.1.20:37123",
    })
    msgs = []
    addr = wa.qr_pair(creds, run=adb, on_status=msgs.append, sleep=lambda _: None, timeout=30)
    assert addr == "192.168.1.20:37123"          # bukan perangkat 192.168.1.99
    assert ("pair", "192.168.1.20:41233", "secret123456") in adb.calls
    assert any("QR" in m for m in msgs)


def test_qr_pair_cancel():
    cancel = threading.Event()
    cancel.set()
    adb = FakeAdb({("mdns", "services"): ""})
    with pytest.raises(wa.WirelessError, match="Dibatalkan"):
        wa.qr_pair(wa.new_qr_credentials(), run=adb, cancel=cancel, sleep=lambda _: None)


def test_qr_pair_timeout():
    adb = FakeAdb({("mdns", "services"): ""})
    with pytest.raises(wa.WirelessError, match="Waktu habis"):
        wa.qr_pair(wa.new_qr_credentials(), run=adb, timeout=0.0, sleep=lambda _: None)
