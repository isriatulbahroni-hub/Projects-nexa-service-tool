from core.frp_verification import (
    collect_frp_verification,
    _parse_getprop,
)


def test_parse_getprop():
    output = """
[ro.product.manufacturer]: [Infinix]
[ro.product.model]: [X6833B]
[ro.build.version.release]: [14]
[ro.build.id]: [UP1A.231005.007]
"""

    props = _parse_getprop(output)

    assert props["ro.product.manufacturer"] == "Infinix"
    assert props["ro.product.model"] == "X6833B"
    assert props["ro.build.version.release"] == "14"


_GETPROP_OUTPUT = """
[ro.product.manufacturer]: [Infinix]
[ro.product.model]: [X6833B]
[ro.build.version.release]: [14]
[ro.build.id]: [TEST]
"""


def _make_runner(setup_complete: str, device_provisioned: str):
    def fake_runner(serial, command):
        assert serial == "TEST123"
        if command == "getprop":
            return _GETPROP_OUTPUT
        if "user_setup_complete" in command:
            return setup_complete
        if "device_provisioned" in command:
            return device_provisioned
        raise AssertionError(f"Unexpected command: {command}")

    return fake_runner


def test_setup_complete():
    result = collect_frp_verification(
        "TEST123",
        runner=_make_runner("1", "1"),
    )

    assert result.manufacturer == "Infinix"
    assert result.model == "X6833B"
    assert result.android_version == "14"
    assert result.setup_complete is True
    assert result.device_provisioned is True
    assert result.frp_status == "SETUP COMPLETE"
    assert result.owner_verification_required is False


def test_unknown_requires_owner_verification():
    # `settings get` pada key yang tidak ada mengembalikan literal "null"
    # di Android sungguhan, bukan string kosong.
    result = collect_frp_verification(
        "TEST123",
        runner=_make_runner("null", "null"),
    )

    assert result.frp_status == "UNKNOWN"
    assert result.owner_verification_required is True


def test_incomplete_setup_requires_owner_verification():
    result = collect_frp_verification(
        "TEST123",
        runner=_make_runner("0", "0"),
    )

    assert result.frp_status == "OWNER VERIFICATION REQUIRED"
    assert result.owner_verification_required is True
