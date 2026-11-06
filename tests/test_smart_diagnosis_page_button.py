"""Regression test untuk SmartDiagnosisPage (ui/smart_diagnosis_page.py) -
ini adalah page yang BENERAN dipakai app.py (beda dari SmartDiagnosisPanel
di smart_diagnosis_panel.py yang cuma kode contoh/tidak dipakai).

Bug yang ditemukan dari laporan user "smart scan tidak bisa diklik":
QPushButton.clicked selalu mengirim parameter `checked` (bool) ke slot
yang terhubung. run_scan(self, facts=None) menerima 1 parameter opsional,
jadi kalau di-connect langsung, `checked=False` diterima sebagai `facts`,
lalu diagnose(False) crash dengan AttributeError SETIAP kali tombol
diklik. Selain itu, run_scan() sebelumnya juga memanggil facts_provider()
(beberapa ADB call blocking) langsung di main thread saat dipanggil dari
tombol, tanpa indikator loading - berpotensi bikin app freeze.
"""
import sys
import time

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from ui.smart_diagnosis_page import SmartDiagnosisPage


@pytest.fixture()
def app():
    return QApplication.instance() or QApplication(sys.argv)


def test_clicking_run_button_does_not_crash(app):
    # facts_provider TIDAK dipanggil sampai tombol diklik - representasi
    # realistis dari app.py yang baru mengumpulkan facts saat scan diminta.
    page = SmartDiagnosisPage(facts_provider=lambda: {"connection_state": "device"})

    # Ini yang dulu crash: emit sinyal clicked() persis seperti Qt beneran,
    # yang selalu membawa parameter bool `checked`.
    page.run_button.click()

    for _ in range(50):
        app.processEvents()
        time.sleep(0.02)
        if "SCANNING" not in page.run_button.text():
            break

    assert page.run_button.isEnabled()
    assert "SCANNING" not in page.run_button.text()
    assert page.last_report is not None


def test_run_scan_with_explicit_facts_still_works_synchronously(app):
    page = SmartDiagnosisPage()
    report = page.run_scan(facts={"connection_state": "device", "battery_percent": 80})

    assert report is not None
    assert page.last_report is report


def test_run_button_shows_loading_state_while_scanning(app):
    """facts_provider yang lambat tidak boleh membuat tombol diam tanpa
    indikator - harus berubah ke 'SCANNING...' dan disabled selama proses."""
    def slow_provider():
        time.sleep(0.2)
        return {"connection_state": "device"}

    page = SmartDiagnosisPage(facts_provider=slow_provider)
    page.run_button.click()

    assert "SCANNING" in page.run_button.text()
    assert not page.run_button.isEnabled()

    for _ in range(50):
        app.processEvents()
        time.sleep(0.02)
        if "SCANNING" not in page.run_button.text():
            break

    assert page.run_button.isEnabled()


def test_repeated_clicks_do_not_crash(app):
    page = SmartDiagnosisPage(facts_provider=lambda: {"connection_state": "device"})

    for _ in range(5):
        page.run_button.click()
        for _ in range(50):
            app.processEvents()
            time.sleep(0.02)
            if "SCANNING" not in page.run_button.text():
                break

    assert page.run_button.isEnabled()
