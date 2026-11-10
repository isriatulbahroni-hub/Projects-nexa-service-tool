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
from core.backup import (
    backup_device,
    restore_device,
    DEFAULT_BACKUP_TARGETS,
    errors_file_for,
    read_backup_warnings,
)


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
        zip_path = backup_device("SERIAL1", tmp_path)

    # Peringatan disimpan di samping ZIP (dibaca UI) dan ikut masuk ke dalam ZIP.
    content = errors_file_for(zip_path).read_text()
    assert "PERINGATAN" in content
    assert "TIDAK LENGKAP" in content
    assert any("TIDAK LENGKAP" in line for line in read_backup_warnings(zip_path))
    assert "TIDAK_LENGKAP" in zip_path.name
    with zipfile.ZipFile(zip_path) as zf:
        assert "TIDAK LENGKAP" in zf.read("backup_errors.txt").decode()


def test_backup_removes_plaintext_staging_folder(tmp_path):
    def fake_pull(*args, **kwargs):
        local = Path(args[4])
        local.mkdir(parents=True, exist_ok=True)
        (local / "foto.jpg").write_bytes(b"data pribadi")
        return ""

    with patch("core.backup.run_adb", side_effect=fake_pull):
        zip_path = backup_device("SERIAL1", tmp_path, password="rahasia")

    assert zip_path.exists()
    assert [p for p in tmp_path.iterdir() if p.is_dir()] == []


def test_backup_partial_failure_is_reported_even_if_device_connected(tmp_path):
    def flaky(*args, **kwargs):
        if "pull" in args and args[4].endswith("Download") is False and "DCIM" in args[3]:
            raise ADBError("ADB timeout.")
        if "pull" in args:
            Path(args[4]).mkdir(parents=True, exist_ok=True)
        return ""

    with patch("core.backup.run_adb", side_effect=flaky), \
         patch("core.adb.get_devices_with_state", return_value={"SERIAL1": "device"}):
        zip_path = backup_device("SERIAL1", tmp_path)

    assert "TIDAK_LENGKAP" in zip_path.name
    warnings = read_backup_warnings(zip_path)
    assert any("DCIM" in w for w in warnings)
    assert any("TIDAK LENGKAP" in w for w in warnings)


def test_backup_wifi_serial_is_filesystem_safe(tmp_path):
    with patch("core.backup.run_adb", return_value=""):
        zip_path = backup_device("192.168.1.5:5555", tmp_path)

    assert ":" not in zip_path.name
    assert zip_path.exists()
    assert "TIDAK_LENGKAP" not in zip_path.name  # backup sukses tidak ditandai


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


def test_restore_zip_slip_guard_rejects_sibling_prefix_dir(tmp_path):
    from core.backup import _validate_zip_members

    root = tmp_path / "abc"
    root.mkdir()
    with pytest.raises(ValueError):
        _validate_zip_members(["../abc_evil/payload.txt"], root)
    _validate_zip_members(["DCIM/foto.jpg"], root)  # aman, tidak raise


def test_restore_pushes_folder_contents_not_folder_itself(tmp_path):
    src_zip = tmp_path / "backup.zip"
    with zipfile.ZipFile(src_zip, "w") as zf:
        zf.writestr("DCIM/photo.jpg", "fake image data")

    pushes = []

    def fake_run_adb(*args, **kwargs):
        if "push" in args:
            pushes.append(args)
        return ""

    with patch("core.backup.run_adb", side_effect=fake_run_adb):
        restore_device("SERIAL1", src_zip)

    assert len(pushes) == 1
    source, remote = pushes[0][-2], pushes[0][-1]
    assert source.replace("\\", "/").endswith("/DCIM/.")
    assert remote == "/sdcard/DCIM"
