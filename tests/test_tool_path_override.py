"""Test untuk fitur baru: path adb/fastboot manual dari Settings
(adb_path_override / fastboot_path_override) - dipakai kalau auto-detect
gagal menemukan instalasi ADB/Fastboot di komputer teknisi.
"""

from unittest.mock import patch

from core.adb import _resolve_adb_path
from core.firmware import _resolve_fastboot_path


def test_adb_path_override_takes_priority(tmp_path):
    fake_adb = tmp_path / "adb.exe"
    fake_adb.write_text("fake")

    with patch("core.adb._get_path_override", return_value=str(fake_adb)):
        result = _resolve_adb_path()

    assert result == str(fake_adb)


def test_adb_path_override_ignored_if_file_missing():
    with patch("core.adb._get_path_override", return_value="/nonexistent/adb.exe"):
        result = _resolve_adb_path()

    assert result != "/nonexistent/adb.exe"


def test_fastboot_path_override_takes_priority(tmp_path):
    fake_fastboot = tmp_path / "fastboot.exe"
    fake_fastboot.write_text("fake")

    with patch("core.firmware._get_path_override", return_value=str(fake_fastboot)):
        result = _resolve_fastboot_path()

    assert result == str(fake_fastboot)
