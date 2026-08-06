from pathlib import Path


def test_app_contains_hardware_page():
    source = Path("app.py").read_text(encoding="utf-8")
    assert '("hardware", "Hardware Test")' in source
    assert "create_hardware_test_page" in source
    assert "run_hardware_test" in source


def test_app_contains_all_service_pages():
    source = Path("app.py").read_text(encoding="utf-8")
    expected = [
        "Dashboard",
        "Device",
        "Diagnostics",
        "Security Check",
        "App Manager",
        "File Explorer",
        "Screen Mirror",
        "Backup & Restore",
        "Network & IMEI",
        "Live Logs",
        "Service History",
        "Firmware & Flash",
        "Hardware Test",
    ]
    for page in expected:
        assert page in source
