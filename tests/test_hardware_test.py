from core.hardware_test import HardwareTestReport, HardwareTestResult


def test_report_counts_and_score():
    report = HardwareTestReport(
        serial="TEST123",
        results=[
            HardwareTestResult("a", "A", "PASS", "ok"),
            HardwareTestResult("b", "B", "INFO", "info"),
            HardwareTestResult("c", "C", "WARN", "warn"),
            HardwareTestResult("d", "D", "FAIL", "fail"),
        ],
    )

    assert report.passed == 1
    assert report.warnings == 1
    assert report.failed == 1
    assert report.score == 57


def test_empty_report_score_is_zero():
    report = HardwareTestReport(serial="TEST123", results=[])
    assert report.score == 0
