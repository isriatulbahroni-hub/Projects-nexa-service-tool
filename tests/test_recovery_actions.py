from core.recovery_actions import factory_reset_guidance, list_recovery_actions


def test_recovery_actions_are_explicit_and_non_destructive():
    actions = list_recovery_actions()
    assert {action.action_id for action in actions} == {
        "reboot_system",
        "reboot_recovery",
        "reboot_bootloader",
    }
    assert all(not action.destructive for action in actions)


def test_factory_reset_is_guidance_only():
    guidance = factory_reset_guidance()
    assert "menghapus data pengguna" in guidance
    assert "FRP" in guidance
    assert "tidak melakukan bypass" in guidance
