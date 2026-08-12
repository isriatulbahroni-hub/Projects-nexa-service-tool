"""Test fitur baru core/backup.py:
- progress_callback dipanggil per-target dengan (index, total, nama)
- deteksi device terputus di tengah proses -> target sisanya dilewati
  (bukan dicoba satu-satu sampai semua timeout) + peringatan jelas
- restore_device menolak ZIP dengan path traversal ("zip slip")
"""

import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from core.adb import ADBError
from core.backup import backup_device, restore_device, DEFAULT_BACKUP_TARGETS


def test_backup_progress_callback_called_for_each_target(tmp_path):
    calls = []

    with patch("core.backup.run_adb", return_value=""):
        backup_device(
            "SERIAL1",
            tmp_path,
            progress_callback=lambda i, t, name: calls.append((i, t, name)),
        )

    assert len(calls) == len(DEFAULT_BACKUP_TARGETS)
    assert calls[0] == (1, len(DEFAULT_BACKUP_TARGETS), DEFAULT_BACKUP_TARGETS[0])


def test_backup_stops_pulling_after_device_disconnects(tmp_path):
    call_log = []

    def fake_run_adb(*args, **kwargs):
        call_log.append(args)
        if "pull" in args:
            raise ADBError("device offline")
        return ""

    with patch("core.backup.run_adb", side_effect=fake_run_adb), \
         patch("core.adb.get_devices_with_state", return_value={}):
        zip_path = backup_device("SERIAL1", tmp_path)

    pull_calls = [c for c in call_log if "pull" in c]
    # Cuma target PERTAMA yang benar-benar dicoba pull; sisanya dilewati
    # begitu device terdeteksi terputus (bukan 4x percobaan yang semuanya
    # timeout).
    assert len(pull_calls) == 1
    assert zip_path.exists()


def test_backup_writes_warning_when_device_lost(tmp_path):
    with patch("core.backup.run_adb", side_effect=ADBError("offline")), \
         patch("core.adb.get_devices_with_state", return_value={}):
        backup_device("SERIAL1", tmp_path)

    staging_dirs = list(tmp_path.glob("backup_SERIAL1_*"))
    error_file = [p for p in staging_dirs if p.is_dir()][0] / "backup_errors.txt"
    content = error_file.read_text()
    assert "PERINGATAN" in content
    assert "TIDAK LENGKAP" in content


def test_restore_rejects_zip_slip(tmp_path):
    malicious_zip = tmp_path / "evil.zip"
    with zipfile.ZipFile(malicious_zip, "w") as zf:
        zf.writestr("../../etc/evil_payload", "malicious content")

    with pytest.raises(ValueError):
        restore_device("SERIAL1", malicious_zip)


def test_restore_progress_callback_called(tmp_path):
    src_zip = tmp_path / "backup.zip"
    with zipfile.ZipFile(src_zip, "w") as zf:
        zf.writestr("DCIM/photo.jpg", "fake image data")
        zf.writestr("Download/file.txt", "fake file")

    calls = []

    with patch("core.backup.run_adb", return_value=""):
        restore_device(
            "SERIAL1",
            src_zip,
            progress_callback=lambda i, t, name: calls.append((i, t, name)),
        )

    assert len(calls) == 2
