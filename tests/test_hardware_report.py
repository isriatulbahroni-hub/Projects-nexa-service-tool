from core.hardware_report import compare_snapshots, snapshot_report
from core.hardware_test import HardwareTestReport, HardwareTestResult


def make_report(serial: str, battery: str, status: str = "PASS") -> HardwareTestReport:
    return HardwareTestReport(
        serial=serial,
        results=[
            HardwareTestResult("battery", "Battery", status, battery),
            HardwareTestResult("usb", "USB", "PASS", "mtp"),
        ],
    )


def test_snapshot_is_immutable_and_contains_summary():
    snapshot = snapshot_report(make_report("ABC", "80%"))

    assert snapshot.serial == "ABC"
    assert snapshot.score == 100
    assert snapshot.passed == 2
    assert snapshot.warnings == 0
    assert snapshot.failed == 0
    assert snapshot.results[0] == ("battery", "Battery", "PASS", "80%")


def test_compare_snapshots_returns_changed_components_only():
    before = snapshot_report(make_report("ABC", "20%", "WARN"))
    after = snapshot_report(make_report("ABC", "85%", "PASS"))

    changes = compare_snapshots(before, after)

    assert len(changes) == 1
    assert changes[0]["name"] == "Battery"
    assert "WARN - 20%" == changes[0]["before"]
    assert "PASS - 85%" == changes[0]["after"]


def test_compare_snapshots_empty_when_identical():
    before = snapshot_report(make_report("ABC", "80%"))
    after = snapshot_report(make_report("ABC", "80%"))

    assert compare_snapshots(before, after) == []
