"""Regression test - sebelum fix, semua package (termasuk app pihak
ketiga seperti NexaPay/Shopee/DANA) ditandai is_system=True saat
include_system=True, karena is_system dihitung dari flag query, bukan
dari data aktual per-package. Lihat komentar di core/packages.py.
"""

from unittest.mock import patch

from core.packages import list_packages


def test_include_system_true_correctly_distinguishes_third_party():
    def fake_run_adb(*args, **kwargs):
        if "-3" in args:
            return "package:com.nexapay.app\npackage:com.shopee.id\n"
        return (
            "package:com.android.systemui\n"
            "package:com.nexapay.app\n"
            "package:com.shopee.id\n"
        )

    with patch("core.packages.run_adb", side_effect=fake_run_adb):
        result = {p.package_name: p.is_system for p in list_packages("SERIAL1", include_system=True)}

    assert result["com.android.systemui"] is True
    assert result["com.nexapay.app"] is False
    assert result["com.shopee.id"] is False


def test_include_system_false_all_third_party():
    def fake_run_adb(*args, **kwargs):
        assert "-3" in args
        return "package:com.nexapay.app\n"

    with patch("core.packages.run_adb", side_effect=fake_run_adb):
        result = list_packages("SERIAL1", include_system=False)

    assert len(result) == 1
    assert result[0].is_system is False
