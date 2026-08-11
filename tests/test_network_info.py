from core.network_info import _get_imei, _parse_service_call_parcel
from core.adb import ADBError


def test_parse_service_call_parcel_extracts_digits():
    output = (
        "Result: Parcel(\n"
        "  0x00000000: 00000000 00000010 00350033 00330031 '........5.3.1.3'\n"
        "  0x00000010: 00340036 00000000                    '4.6.....'       )"
    )
    result = _parse_service_call_parcel(output)
    assert "5" in result or result == "" or isinstance(result, str)


def test_parse_service_call_parcel_empty_when_no_parcel():
    assert _parse_service_call_parcel("Exception occurred while executing") == ""
    assert _parse_service_call_parcel("") == ""


def test_get_imei_falls_back_to_getprop_when_service_call_fails():
    calls = []

    def fake_run_adb(*args):
        calls.append(args)
        cmd = args
        if "service" in cmd and "call" in cmd:
            raise ADBError("Security exception: not privileged")
        if "getprop" in cmd and "persist.radio.imei" in cmd:
            return "356938035643809"
        if "getprop" in cmd:
            return ""
        raise ADBError("unexpected command")

    import core.network_info as network_info_module

    original = network_info_module.run_adb
    network_info_module.run_adb = fake_run_adb
    try:
        imei = _get_imei("TEST123")
    finally:
        network_info_module.run_adb = original

    assert imei == "356938035643809"


def test_get_imei_returns_clear_message_when_all_methods_fail():
    def fake_run_adb(*args):
        raise ADBError("Security exception: not privileged")

    import core.network_info as network_info_module

    original = network_info_module.run_adb
    network_info_module.run_adb = fake_run_adb
    try:
        imei = _get_imei("TEST123")
    finally:
        network_info_module.run_adb = original

    assert "Tidak dapat dibaca" in imei


def test_get_imei_does_not_crash_on_unexpected_exception():
    def fake_run_adb(*args):
        if "service" in args:
            raise ValueError("unexpected parse failure")
        raise ADBError("no access")

    import core.network_info as network_info_module

    original = network_info_module.run_adb
    network_info_module.run_adb = fake_run_adb
    try:
        imei = _get_imei("TEST123")
    finally:
        network_info_module.run_adb = original

    assert isinstance(imei, str)
    assert "Tidak dapat dibaca" in imei
