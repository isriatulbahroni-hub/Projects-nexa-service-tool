import pytest

from core.factory_reset_assistant import FactoryResetPlan, ResetStage


def test_reset_plan_requires_all_safety_confirmations():
    plan = FactoryResetPlan(model="Test Phone").build()
    assert plan.stage == ResetStage.PRECHECK
    assert plan.checklist.ready_for_recovery is False
    with pytest.raises(ValueError):
        plan.authorize_recovery_guidance()


def test_reset_plan_requires_customer_authorization_and_acknowledgements():
    plan = FactoryResetPlan(model="Test Phone").build()
    plan.checklist.backup_confirmed = True
    plan.checklist.customer_authorized = True
    plan.checklist.data_loss_acknowledged = True
    plan.checklist.frp_warning_acknowledged = True
    assert plan.authorize_recovery_guidance() is True
    assert plan.stage == ResetStage.RECOVERY


def test_post_reset_checklist_is_non_destructive():
    plan = FactoryResetPlan(model="Test Phone").build()
    steps = plan.post_reset_checklist()
    assert plan.stage == ResetStage.POST_RESET
    assert any("hardware diagnostics" in step.lower() for step in steps)
    assert any("service case" in step.lower() for step in steps)
