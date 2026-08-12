"""Regression tests:
- core/adb.py run_adb() sebelumnya pakai subprocess.run(text=True) tanpa
  encoding eksplisit - di Windows ini decode pakai codepage lokal
  (cp1252), bukan UTF-8, dan crash (UnicodeDecodeError) kalau output ADB
  ada byte yang bukan cp1252.
- core/firmware.py flash_partition() sebelumnya tidak memblokir
  CRITICAL_PARTITIONS sama sekali di level fungsi.
"""

from unittest.mock import patch, MagicMock

from core.adb import run_adb
from core.firmware import flash_partition, FastbootError, CRITICAL_PARTITIONS


def test_run_adb_uses_utf8_not_locale_encoding():
    with patch("core.adb._resolve_adb_path", return_value="/fake/adb"), \
         patch("core.adb.Path") as mock_path, \
         patch("core.adb.subprocess.run") as mock_run:
        mock_path.return_value.exists.return_value = True
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")

        run_adb("shell", "echo", "hi")

        _, kwargs = mock_run.call_args
        assert kwargs.get("encoding") == "utf-8"
        assert kwargs.get("errors") == "replace"
        # text=True tanpa encoding eksplisit adalah root cause bug-nya -
        # pastikan tidak balik lagi ke pola itu.
        assert "text" not in kwargs or kwargs.get("encoding") is not None


def test_flash_partition_blocks_critical_partitions_by_default():
    for partition in CRITICAL_PARTITIONS:
        try:
            flash_partition(partition, "/tmp/fake.img", serial="ABC")
            assert False, f"{partition} seharusnya diblokir"
        except FastbootError:
            pass


def test_flash_partition_allows_common_partition():
    with patch("core.firmware.run_fastboot", return_value="OKAY") as mock_fb:
        result = flash_partition("boot", "/tmp/fake.img", serial="ABC")
        assert result == "OKAY"
        mock_fb.assert_called_once()


def test_flash_partition_allows_critical_when_explicitly_allowed():
    with patch("core.firmware.run_fastboot", return_value="OKAY") as mock_fb:
        result = flash_partition(
            "bootloader", "/tmp/fake.img", serial="ABC", allow_critical=True
        )
        assert result == "OKAY"
        mock_fb.assert_called_once()
