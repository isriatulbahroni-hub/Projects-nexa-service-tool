from core.locked_device_recovery import (
    AccessProblem,
    LockedDeviceRecoveryState,
    detect_locked_device_recovery_state,
    plan_locked_device,
)
from core.frp_verification import FRPVerification


class FakeFRPVerification(FRPVerification):
    pass


def test_unauthorized_never_offers_bypass():
    plan = plan_locked_device(adb_state="unauthorized")
    assert plan.state == "unauthorized"
    # Actions may legitimately mention "bypass" as part of a prohibition
    # (e.g. "Do not attempt a lock bypass"). What must never happen is an
    # action that *instructs* performing one -- so we only fail if "bypass"
    # appears without an accompanying negation/refusal phrase.
    negations = ("do not", "don't", "never", "no ")
    for action in plan.actions:
        lowered = action.lower()
        if "bypass" in lowered:
            assert any(neg in lowered for neg in negations), (
                f"Action mentions bypass without a clear prohibition: {action!r}"
            )


def test_recovery_warns_about_data_loss_and_account():
    plan = plan_locked_device(recovery_available=True, owner_account_known=False)
    assert plan.destructive is True
    text = " ".join(plan.actions).lower()
    assert "erases local data" in text
    assert "recover the owner's account" in text


def test_detect_locked_device_recovery_state_authorized_reboots_allowed(monkeypatch):
    serial = "TEST123"

    def fake_devices():
        return {serial: "device"}

    def fake_fastboot_devices():
        return []

    def fake_run_adb(*args, **kwargs):
        assert args[:3] == ("-s", serial, "shell")
        if args[3:] == ("getprop", "ro.bootmode"):
            return ""
        return ""

    def fake_frp_fn(serial_arg):
        assert serial_arg == serial
        return FakeFRPVerification(
            serial=serial,
            manufacturer="Samsung",
            model="Galaxy S22",
            android_version="13",
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

    state = detect_locked_device_recovery_state(
        serial,
        devices_fn=fake_devices,
        fastboot_fn=fake_fastboot_devices,
        run_adb_fn=fake_run_adb,
        frp_fn=fake_frp_fn,
    )

    assert state.authorized is True
    assert state.device_mode == "Normal Android (ADB authorized)"
    assert "reboot_recovery" in state.supported_actions
    assert "reboot_bootloader" in state.supported_actions
    assert "verify_result" in state.supported_actions
    assert state.confirmation_required is True


def test_detect_locked_device_recovery_state_owner_verification_limits_reboot(monkeypatch):
    serial = "TEST123"

    def fake_devices():
        return {serial: "device"}

    def fake_fastboot_devices():
        return []

    def fake_run_adb(*args, **kwargs):
        return ""

    def fake_frp_fn(serial_arg):
        return FakeFRPVerification(
            serial=serial,
            manufacturer="Google",
            model="Pixel 6",
            android_version="14",
            build_id="TEST",
            setup_complete=True,
            device_provisioned=True,
            frp_provisioned="1",
            bootloader_locked="Locked",
            verified_boot_state="green",
            frp_status="FRP PROVISIONED",
            owner_verification_required=True,
            message="Owner verification required",
        )

    state = detect_locked_device_recovery_state(
        serial,
        devices_fn=fake_devices,
        fastboot_fn=fake_fastboot_devices,
        run_adb_fn=fake_run_adb,
        frp_fn=fake_frp_fn,
    )

    assert state.authorized is True
    assert state.owner_verification_required is True
    assert state.supported_actions == ("verify_result",)
    assert state.confirmation_required is False
