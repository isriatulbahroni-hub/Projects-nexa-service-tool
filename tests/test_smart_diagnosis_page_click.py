"""Regression test untuk bug: klik 'RUN SMART SCAN' selalu crash.

Root cause: PySide/PyQt signal `clicked` otomatis mengirim parameter
`checked` (bool) ke slot yang disambungkan kalau slot itu menerima
parameter. `run_scan(self, facts=None)` menerima parameter -> setiap
klik tombol, Qt mengisi `facts=False`, lalu kode langsung mencoba
`False.get(...)` di core/smart_diagnosis.py::diagnose() dan crash
dengan AttributeError. Ini sebabnya Smart Diagnosis "tidak bisa
dijalankan" - bukan soal lambat, tapi crash di setiap klik.
"""

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from ui.smart_diagnosis_page import SmartDiagnosisPage


def test_run_button_click_does_not_crash_with_bool_checked_arg():
    app = QApplication.instance() or QApplication([])

    page = SmartDiagnosisPage(facts_provider=lambda: {"connection_state": "device"})
    page.show()

    # Simulasikan persis apa yang Qt lakukan saat sinyal `clicked` emit:
    # kirim positional bool `checked`, seperti tombol asli diklik user.
    page.run_button.click()
    app.processEvents()

    # Tidak boleh ada exception yang lolos sampai sini. Karena facts_provider
    # jalan di background thread (AsyncWorker), tunggu sebentar hasilnya
    # sampai. Kalau tidak selesai dalam waktu wajar, worker dianggap gagal
    # start / macet - juga kegagalan yang harus terdeteksi test ini.
    worker = getattr(page, "_scan_worker", None)
    assert worker is not None, "run_scan seharusnya membuat AsyncWorker saat diklik tombol"
    worker.wait(2000)
    app.processEvents()

    assert page.last_report is not None
    page.close()


def test_run_scan_called_directly_with_no_facts_uses_provider():
    app = QApplication.instance() or QApplication([])

    calls = []

    def provider():
        calls.append(1)
        return {"connection_state": "device"}

    page = SmartDiagnosisPage(facts_provider=provider)
    page.run_scan()

    worker = page._scan_worker
    worker.wait(2000)
    app.processEvents()

    assert calls, "facts_provider harus terpanggil"
    assert page.last_report is not None
    page.close()
