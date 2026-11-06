"""Regression tests - severity code numerik (mStatus) dan flag low_ram
sebelumnya dihitung tapi TIDAK PERNAH dipakai di check_thermal()/
check_memory(), sehingga device yang sebenarnya bermasalah bisa lolos
sebagai PASS. Lihat komentar di core/hardware_test.py untuk detail.
"""

from unittest.mock import patch

from core.hardware_test import check_thermal, check_memory


def _mock_shell(output: str):
    return patch("core.hardware_test._shell", return_value=output)


def test_thermal_numeric_severe_code_without_text_keyword():
    # Output cuma berisi kode numerik SEVERE (3), TANPA kata "severe"/
    # "critical" sama sekali - sebelum fix ini akan lolos sebagai PASS.
    raw = "CachedTemperature{mValue=42.0, mType=0}\nStatus{mStatus=3}"
    with _mock_shell(raw):
        result = check_thermal("SERIAL1")
    assert result.status == "WARN"


def test_thermal_numeric_shutdown_code_without_text_keyword():
    raw = "Status{mStatus=6}"
    with _mock_shell(raw):
        result = check_thermal("SERIAL1")
    assert result.status == "FAIL"


def test_thermal_normal_code_stays_pass():
    raw = "Status{mStatus=0}"
    with _mock_shell(raw):
        result = check_thermal("SERIAL1")
    assert result.status == "PASS"


def test_memory_low_ram_flag_forces_warn_even_with_high_percent_free():
    # percent_free dihitung 10% (di atas ambang 5%), TAPI Android
    # eksplisit melaporkan status low-memory - sebelum fix ini lolos PASS.
    raw = "Total RAM: 4,000,000K\nFree RAM: 400,000K (low ram)\n"
    with _mock_shell(raw):
        result = check_memory("SERIAL1")
    assert result.status == "WARN"


def test_memory_normal_stays_pass():
    raw = "Total RAM: 4,000,000K\nFree RAM: 2,000,000K\n"
    with _mock_shell(raw):
        result = check_memory("SERIAL1")
    assert result.status == "PASS"
