from core.locked_device_recovery import plan_locked_device


def test_unauthorized_never_offers_bypass():
    plan = plan_locked_device(adb_state="unauthorized")
    assert plan.state == "unauthorized"
    assert all("bypass" not in action.lower() for action in plan.actions)


def test_recovery_warns_about_data_loss_and_account():
    plan = plan_locked_device(recovery_available=True, owner_account_known=False)
    assert plan.destructive is True
    text = " ".join(plan.actions).lower()
    assert "erases local data" in text
    assert "recover the owner's account" in text
