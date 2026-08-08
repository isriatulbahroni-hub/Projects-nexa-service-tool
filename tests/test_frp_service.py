from dataclasses import dataclass

from core.frp_service import (
    FRPServiceError,
    FRPServiceState,
    _build_recovery_guidance,
    _infer_brand_group,
    collect_fastboot_variables,
    detect_frp_service_state,
    execute_bootloader_reboot,
    execute_recovery_reboot,
    verify_frp_result,
)
from core.frp_verification import FRPVerification


class FakeFRPVerification(FRPVerification):
    pass


@dataclass
class FakeState:
    authorized: bool
    owner_auth_required: bool
    adb_state: str = "device"
    fastboot_connected: bool = False
    frp_status: str = "SETUP COMPLETE"
    message: str = "Ready"
    supported_operations: tuple[str, ...] = ()
    fastboot_vars: dict[str, str] | None = None
    frp_verification: FRPVerification | None = None
    brand_group: str = "Unknown"
    device_properties: dict[str, str] | None = None
    workflow_guidance: tuple[str, ...] = ()


def test_infer_brand_group_detects_known_families():
    assert _infer_brand_group({"manufacturer": "samsung"}) == "Samsung"
    assert _infer_brand_group({"brand": "Redmi"}) == "Xiaomi / Redmi / POCO"
    assert _infer_brand_group({"product": "realme"}) == "OPPO / realme"
    assert _infer_brand_group({"device": "vivo"}) == "vivo / iQOO"
    assert _infer_brand_group({"model": "infinix"}) == "Infinix / TECNO"
    assert _infer_brand_group({"brand": "Motorola"}) == "Motorola"
    assert _infer_brand_group({"manufacturer": "HMD Global"}) == "Nokia / HMD"
    assert _infer_brand_group({"brand": "OnePlus"}) == "OnePlus"
    assert _infer_brand_group({"manufacturer": "testmaker"}) == "Testmaker"


def test_build_recovery_guidance_includes_owner_auth_message():
    guidance = _build_recovery_guidance(
        brand_group="Samsung",
        authorized=True,
        owner_auth_required=True,
        fastboot_connected=False,
    )

    assert any("owner" in item.lower() for item in guidance)
    assert any("recovery" in item.lower() for item in guidance)

    guidance_no_auth = _build_recovery_guidance(
        brand_group="Samsung",
        authorized=True,
        owner_auth_required=False,
        fastboot_connected=True,
    )

    assert any("Owner authorization cleared" in item for item in guidance_no_auth)
    assert any("Fastboot mode is available" in item for item in guidance_no_auth)


def test_detect_frp_service_state_authorized_with_fastboot(monkeypatch):
    serial = "TEST123"

    def fake_devices():
        return {serial: "device"}

    def fake_fastboot_devices():
        return [serial]

    def fake_frp_verification(serial_arg):
        assert serial_arg == serial
        return FakeFRPVerification(
            serial=serial,
            manufacturer="Xiaomi",
            model="Mi 14",
            android_version="14",
            build_id="TEST",
            setup_complete=True,
            device_provisioned=True,
            frp_provisioned="0",
            bootloader_locked="Locked",
            verified_boot_state="green",
            frp_status="SETUP COMPLETE",
            owner_verification_required=False,
            message="Ready",
        )

    def fake_run_fastboot(*args, **kwargs):
        assert args[0] == "-s"
        assert args[1] == serial
        assert args[2] == "getvar"
        assert args[3] == "all"
        return "brand: xiaomi\nproduct: lmi\nmodel: Mi 14\n"

    def fake_adb_prop(serial_arg, prop):
        assert serial_arg == serial
        return {
            "ro.product.manufacturer": "Xiaomi",
            "ro.product.brand": "xiaomi",
            "ro.product.model": "Mi 14",
            "ro.product.name": "lmi",
            "ro.product.device": "lmi",
            "ro.build.fingerprint": "Xiaomi/lmi/",
        }[prop]

    monkeypatch.setattr("core.frp_service.run_fastboot", fake_run_fastboot)
    monkeypatch.setattr("core.frp_service._adb_prop", fake_adb_prop)

    state = detect_frp_service_state(
        serial,
        devices_fn=fake_devices,
        fastboot_fn=fake_fastboot_devices,
        frp_fn=fake_frp_verification,
    )

    assert state.authorized is True
    assert state.fastboot_connected is True
    assert "reboot_recovery" in state.supported_operations
    assert state.brand_group == "Xiaomi / Redmi / POCO"
    assert state.fastboot_vars["brand"] == "xiaomi"
    assert state.device_properties["model"] == "Mi 14"
    assert state.workflow_guidance


def test_detect_frp_service_state_unauthorized_requires_verification(monkeypatch):
    serial = "TEST123"

    def fake_devices():
        return {serial: "unauthorized"}

    def fake_fastboot_devices():
        return []

    state = detect_frp_service_state(
        serial,
        devices_fn=fake_devices,
        fastboot_fn=fake_fastboot_devices,
        frp_fn=lambda serial_arg: (_ for _ in ()).throw(RuntimeError("Should not be called")),
    )

    assert state.authorized is False
    assert state.owner_auth_required is True
    assert "refresh_status" not in state.supported_operations
    assert state.message.startswith("Perangkat memerlukan otorisasi")


def test_execute_recovery_and_bootloader_reboot_require_owner_authorization(monkeypatch):
    serial = "TEST123"

    fake_state = FRPServiceState(
        serial=serial,
        adb_state="device",
        authorized=True,
        fastboot_connected=False,
        owner_auth_required=True,
        frp_status="OWNER VERIFICATION REQUIRED",
        message="Owner auth required",
        supported_operations=(),
        fastboot_vars=None,
        frp_verification=None,
        brand_group="Unknown",
        device_properties={"model": "Test"},
        workflow_guidance=(),
    )

    def fake_detect(serial_arg):
        assert serial_arg == serial
        return fake_state

    result_error = None
    try:
        execute_recovery_reboot(serial, detect_fn=fake_detect)
        assert False, "Expected FRPServiceError"
    except FRPServiceError as exc:
        result_error = exc

    assert result_error is not None
    assert "REQUIRES OWNER/OEM AUTHORIZATION" in str(result_error)

    result_error = None
    try:
        execute_bootloader_reboot(serial, detect_fn=fake_detect)
        assert False, "Expected FRPServiceError"
    except FRPServiceError as exc:
        result_error = exc

    assert result_error is not None
    assert "REQUIRES OWNER/OEM AUTHORIZATION" in str(result_error)


def test_execute_recovery_and_bootloader_reboot_calls_adb(monkeypatch):
    serial = "TEST123"

    fake_state = FRPServiceState(
        serial=serial,
        adb_state="device",
        authorized=True,
        fastboot_connected=False,
        owner_auth_required=False,
        frp_status="SETUP COMPLETE",
        message="Ready",
        supported_operations=(),
        fastboot_vars=None,
        frp_verification=None,
        brand_group="Unknown",
        device_properties={"model": "Test"},
        workflow_guidance=(),
    )

    def fake_detect(serial_arg):
        assert serial_arg == serial
        return fake_state

    def fake_reboot(serial_arg, mode="system"):
        assert serial_arg == serial
        return f"rebooted:{mode}"

    result_recovery = execute_recovery_reboot(
        serial,
        detect_fn=fake_detect,
        reboot_fn=fake_reboot,
    )
    assert result_recovery == "rebooted:recovery"

    result_bootloader = execute_bootloader_reboot(
        serial,
        detect_fn=fake_detect,
        reboot_fn=fake_reboot,
    )
    assert result_bootloader == "rebooted:bootloader"


def test_collect_fastboot_variables_parses_output(monkeypatch):
    serial = "TEST123"

    def fake_run_fastboot(*args, **kwargs):
        assert args[:3] == ("-s", serial, "getvar")
        return "brand: google\nproduct: pixel\nmodel: Pixel 8\n"

    values = collect_fastboot_variables(
        serial,
        fastboot_fn=lambda: [serial],
        run_fastboot_fn=fake_run_fastboot,
    )
    assert values["brand"] == "google"
    assert values["product"] == "pixel"
    assert values["model"] == "Pixel 8"


def test_verify_frp_result_returns_verification(monkeypatch):
    serial = "TEST123"

    def fake_frp_verification(serial_arg):
        return FakeFRPVerification(
            serial=serial,
            manufacturer="Google",
            model="Pixel 8",
            android_version="14",
            build_id="TEST",
            setup_complete=True,
            device_provisioned=True,
            frp_provisioned="0",
            bootloader_locked="Locked",
            verified_boot_state="green",
            frp_status="SETUP COMPLETE",
            owner_verification_required=False,
            message="Ready",
        )

    result = verify_frp_result(
        serial,
        frp_fn=fake_frp_verification,
    )
    assert result.manufacturer == "Google"
    assert result.owner_verification_required is False
