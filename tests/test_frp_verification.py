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
[ro.setupwizard.user_setup_complete]: [1]
[sys.device_provisioned]: [1]
"""

    props = _parse_getprop(output)

    assert props["ro.product.manufacturer"] == "Infinix"
    assert props["ro.product.model"] == "X6833B"
    assert props["ro.build.version.release"] == "14"


def test_setup_complete():
    def fake_runner(serial, command):
        assert serial == "TEST123"

        return """
[ro.product.manufacturer]: [Infinix]
[ro.product.model]: [X6833B]
[ro.build.version.release]: [14]
[ro.build.id]: [TEST]
[ro.setupwizard.user_setup_complete]: [1]
[sys.device_provisioned]: [1]
"""

    result = collect_frp_verification(
        "TEST123",
        runner=fake_runner,
    )

    assert result.manufacturer == "Infinix"
    assert result.model == "X6833B"
    assert result.android_version == "14"
    assert result.setup_complete is True
    assert result.device_provisioned is True
    assert result.frp_status == "SETUP COMPLETE"
    assert result.owner_verification_required is False


def test_unknown_requires_owner_verification():
    def fake_runner(serial, command):
        return """
[ro.product.manufacturer]: [Infinix]
[ro.product.model]: [X6833B]
[ro.build.version.release]: [14]
[ro.build.id]: [TEST]
"""

    result = collect_frp_verification(
        "TEST123",
        runner=fake_runner,
    )

    assert result.frp_status == "UNKNOWN"
    assert result.owner_verification_required is True


def test_incomplete_setup_requires_owner_verification():
    def fake_runner(serial, command):
        return """
[ro.product.manufacturer]: [Infinix]
[ro.product.model]: [X6833B]
[ro.build.version.release]: [14]
[ro.build.id]: [TEST]
[ro.setupwizard.user_setup_complete]: [0]
[sys.device_provisioned]: [0]
"""

    result = collect_frp_verification(
        "TEST123",
        runner=fake_runner,
    )

    assert result.frp_status == "OWNER VERIFICATION REQUIRED"
    assert result.owner_verification_required is True
