from core.locked_device_recovery import plan_locked_device


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
