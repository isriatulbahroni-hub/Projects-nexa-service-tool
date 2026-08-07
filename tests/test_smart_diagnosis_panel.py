import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from ui.smart_diagnosis_panel import SmartDiagnosisPanel


def test_panel_renders_locked_device_diagnosis():
    app = QApplication.instance() or QApplication([])

    panel = SmartDiagnosisPanel(
        lambda problem: {
            "connection_state": "unauthorized",
            "access_issue": "locked",
            "imei": "123456789012345",
            "baseband": "M123",
        }
    )

    panel.show()
    report = panel.run_scan()

    assert report is not None
    assert report.score < 100
    assert report.severity in {"attention", "critical"}
    assert panel.report_dict()["findings"]

    panel.close()
    app.processEvents()
