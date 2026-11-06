"""Test untuk fitur baru:
- Enkripsi AES pada backup ZIP (password protection) - isi backup (foto,
  chat WhatsApp) adalah data pribadi pelanggan yang sensitif, sebelumnya
  selalu tersimpan sebagai ZIP polos tanpa proteksi apapun.
- cleanup_old_backups() - retensi otomatis file backup lama.
"""

import time
from pathlib import Path
from unittest.mock import patch

import pytest

from core.backup import (
    backup_device,
    restore_device,
    is_zip_password_protected,
    cleanup_old_backups,
    BackupError,
)


def _fake_pull_with_content(*args, **kwargs):
    local_target = Path(args[4])
    local_target.mkdir(parents=True, exist_ok=True)
    (local_target / "dummy.jpg").write_bytes(b"fake image data")
    return ""


def test_backup_without_password_is_not_encrypted(tmp_path):
    with patch("core.backup.run_adb", side_effect=_fake_pull_with_content):
        zip_path = backup_device("SN1", tmp_path)

    assert is_zip_password_protected(zip_path) is False


def test_backup_with_password_is_encrypted(tmp_path):
    with patch("core.backup.run_adb", side_effect=_fake_pull_with_content):
        zip_path = backup_device("SN1", tmp_path, password="rahasia123")

    assert is_zip_password_protected(zip_path) is True


def test_restore_encrypted_backup_requires_correct_password(tmp_path):
    with patch("core.backup.run_adb", side_effect=_fake_pull_with_content):
        zip_path = backup_device("SN1", tmp_path, password="rahasia123")

    with patch("core.backup.run_adb", return_value=""):
        with pytest.raises(Exception):
            restore_device("SN1", zip_path)  # tanpa password

        with pytest.raises(Exception):
            restore_device("SN1", zip_path, password="password-salah")

        results = restore_device("SN1", zip_path, password="rahasia123")
        assert any("OK" in r for r in results)


def test_cleanup_old_backups_removes_only_old_files(tmp_path):
    old_zip = tmp_path / "backup_OLD_20200101_000000.zip"
    old_zip.write_bytes(b"old")
    new_zip = tmp_path / "backup_NEW_20990101_000000.zip"
    new_zip.write_bytes(b"new")

    # Paksa mtime file lama supaya benar-benar "lama"
    old_time = time.time() - (60 * 24 * 3600)
    import os
    os.utime(old_zip, (old_time, old_time))

    removed = cleanup_old_backups(tmp_path, retention_days=30)

    assert removed == 1
    assert not old_zip.exists()
    assert new_zip.exists()


def test_cleanup_old_backups_disabled_when_zero_days(tmp_path):
    old_zip = tmp_path / "backup_OLD_20200101_000000.zip"
    old_zip.write_bytes(b"old")
    import os, time
    old_time = time.time() - (60 * 24 * 3600)
    os.utime(old_zip, (old_time, old_time))

    removed = cleanup_old_backups(tmp_path, retention_days=0)

    assert removed == 0
    assert old_zip.exists()
