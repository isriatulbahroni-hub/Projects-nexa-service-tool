from dataclasses import dataclass

from core.device_diagnostics import (
    CheckStatus,
    DiagnosticItem,
    DiagnosticReport,
    _parse_key_value,
    run_device_diagnostics,
)


class FakeDeviceInfo:
    def __init__(self, serial: str):
        self.serial = serial
        self.manufacturer = "TestCo"
        self.model = "TestModel"
        self.product = "testproduct"
        self.device = "testdevice"
        self.android_version = "14"
        self.build_id = "TEST123"


@dataclass
class FakeSecurityResult:
    bootloader_state: str = "Locked"
    verified_boot_state: str = "green"


def test_parse_key_value_extracts_value():
    text = "level: 58\nstatus: 2\nhealth: 2\n"
    assert _parse_key_value(text, "level:") == "58"
    assert _parse_key_value(text, "status:") == "2"
    assert _parse_key_value(text, "health:") == "2"


def test_run_device_diagnostics_returns_report_with_expected_counts(monkeypatch):
    serial = "TEST123"

    monkeypatch.setattr("core.device_diagnostics.get_device_info", lambda s: FakeDeviceInfo(s))
    monkeypatch.setattr("core.device_diagnostics.get_devices_with_state", lambda: {serial: "device"})
    monkeypatch.setattr("core.device_diagnostics.list_fastboot_devices", lambda: [])
    monkeypatch.setattr("core.device_diagnostics.get_network_info", lambda s: type("N", (), {
        "wifi_state": "Enabled",
        "mobile_data_state": "Disabled",
        "ip_address": "192.168.1.10",
        "network_operator": "TestNet",
        "sim_state": "READY",
        "phone_type": "GSM",
        "imei": "Unknown",
    })())
    monkeypatch.setattr("core.device_diagnostics.run_security_check", lambda s: FakeSecurityResult())

    def fake_run_adb(*args, **kwargs):
        command = " ".join(str(x) for x in args)
        if "dumpsys battery" in command:
            return "level: 50\nstatus: 2\nhealth: 2\ntemperature: 300\nvoltage: 3800\ncurrent now: 1000\n"
        if "df -h /data" in command:
            return "Filesystem Size Used Avail Use% Mounted on\n/dev/block/dm-0 64G 24G 40G 38% /data\n"
        if "cat /proc/mounts" in command:
            return "/dev/block/dm-0 /data ext4 rw,seclabel 0 0\n"
        if "getprop ro.build.id" in command:
            return "TEST123"
        if "getprop ro.build.fingerprint" in command:
            return "test/fingerprint"
        if "getprop ro.build.version.security_patch" in command:
            return "2024-01-01"
        if "getprop ro.build.version.release" in command:
            return "14"
        if "pm list packages" in command:
            return "package:com.example.app\n"
        if "logcat -d" in command:
            return ""
        if "getprop ro.bootmode" in command:
            return ""
        if "getprop sys.boot_completed" in command:
            return "1"
        if "settings get secure user_setup_complete" in command:
            return "1"
        if "settings get global adb_enabled" in command:
            return "1"
        if "cat /proc/meminfo" in command:
            return "MemTotal:       2048000 kB\nMemFree:        512000 kB\n"
        if "getprop ro.boot.flash.locked" in command:
            return "1"
        if "getprop ro.boot.verifiedbootstate" in command:
            return "green"
        return ""

    monkeypatch.setattr("core.device_diagnostics.run_adb", fake_run_adb)

    report = run_device_diagnostics(serial)

    assert report.serial == serial
    assert report.device_info["Manufacturer"] == "TestCo"
    assert report.counts[CheckStatus.PASS.value] >= 1
    assert report.counts[CheckStatus.FAIL.value] == 0
    assert report.counts[CheckStatus.NA.value] >= 0
    assert "Battery Level" in [item.name for item in report.items]
    assert "Fastboot Communication" in [item.name for item in report.items]
    assert report.summary.startswith("PASS")
