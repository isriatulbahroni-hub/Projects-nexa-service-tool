from core.device_access_recovery import AccessProblem, diagnose_access_issue


def test_forgotten_credential_does_not_offer_bypass():
    report = diagnose_access_issue({"adb_state": "offline"})
    assert report.problem == AccessProblem.FORGOT_CREDENTIAL
    assert any("official" in f.action.lower() for f in report.findings)


def test_frp_requires_owner_verification():
    report = diagnose_access_issue({"frp_detected": True})
    assert report.problem == AccessProblem.FRP_LOCK
    assert report.requires_owner_verification
    assert any("bypass" in warning.lower() for warning in report.warnings)


def test_lockout_recommends_stopping_repeated_attempts():
    report = diagnose_access_issue({"lockout": True})
    assert report.problem == AccessProblem.LOCKOUT
    assert any("repeated" in f.detail.lower() for f in report.findings)


def test_bootloop_is_critical_and_warns_before_wipe():
    report = diagnose_access_issue({"bootloop": True, "data_present": True})
    assert report.problem == AccessProblem.BOOTLOOP
    assert any(f.severity == "critical" for f in report.findings)
    assert any("factory reset" in warning.lower() for warning in report.warnings)


def test_fastboot_is_diagnostic_not_an_automatic_flash_action():
    report = diagnose_access_issue({"fastboot": True})
    assert report.problem == AccessProblem.FASTBOOT_AVAILABLE
    assert any("model/build" in f.action.lower() for f in report.findings)
