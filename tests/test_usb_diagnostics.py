from core.usb_diagnostics import (
    UsbDiagnosticsReport,
    _parse_pnp_line,
)


def test_parse_pnp_line_extracts_usb_vid_pid():
    device = _parse_pnp_line(
        "OK\tUSB\tSamsung Android USB Device\tUSB\\VID_04E8&PID_6860\\ABC123"
    )
    assert device is not None
    assert device.vendor_id == "04E8"
    assert device.product_id == "6860"
    assert device.friendly_name == "Samsung Android USB Device"


def test_parse_pnp_line_rejects_incomplete_input():
    assert _parse_pnp_line("OK\tUSB") is None


def test_report_to_dict_is_serializable_shape():
    report = UsbDiagnosticsReport(
        platform="nt",
        pnp_available=True,
        usb_devices=[],
        serial_ports=[],
        adb_available=True,
        adb_devices=[{"serial": "ABC", "state": "device"}],
        pyusb_backend="unavailable",
        samsung_usb_detected=False,
    )
    data = report.to_dict()
    assert data["platform"] == "nt"
    assert data["adb_devices"][0]["state"] == "device"
    assert data["samsung_usb_detected"] is False
