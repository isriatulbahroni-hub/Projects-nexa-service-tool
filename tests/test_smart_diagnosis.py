from core.smart_diagnosis import diagnose


def test_healthy_device_has_full_score():
    report = diagnose({"connection_state": "device", "imei": "123456789012345", "baseband": "1.0"})
    assert report.score == 100
    assert report.severity == "healthy"
    assert report.findings == ()


def test_low_battery_and_missing_imei_are_high_severity():
    report = diagnose({"battery_percent": 10, "imei": "unknown"})
    codes = {item.code for item in report.findings}
    assert "LOW_BATTERY" in codes
    assert "IMEI_MISSING" in codes
    assert report.score < 100
    assert report.severity == "critical"


def test_fastboot_and_network_failure_are_explained():
    report = diagnose({
        "boot_state": "fastboot",
        "network_state": "no_service",
        "imei": "123456789012345",
        "baseband": "1.2.3",
    })
    codes = {item.code for item in report.findings}
    assert {"FASTBOOT_MODE", "NETWORK_UNAVAILABLE"}.issubset(codes)
    assert report.recommendations


def test_hardware_failures_are_reported():
    report = diagnose({"hardware_failures": ["Battery", "Camera"]})
    assert any(item.code == "HARDWARE_FAILURE" for item in report.findings)
