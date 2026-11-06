"""Test untuk audit trail (core/database.py action_log) - fitur baru
yang mencatat tindakan berisiko (backup, restore, uninstall, install,
flash, verifikasi FRP, dll) supaya ada jejak untuk akuntabilitas.

Juga regression test untuk bug urutan: created_at cuma presisi sampai
detik, jadi dua entry yang tersimpan dalam detik yang sama bisa salah
urutan kalau di-sort dari teksnya - harus urut by id.
"""

import importlib
import sqlite3

import pytest


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    import core.database as database

    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test_nexa.db")
    importlib.reload(database)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test_nexa.db")
    return database


def test_log_action_and_get_action_log_roundtrip(temp_db):
    temp_db.log_action("Backup", detail="backup.zip", status="OK", serial="SN1")
    temp_db.log_action("Uninstall App", detail="com.test", status="GAGAL", serial="SN1")

    entries = temp_db.get_action_log(serial="SN1")
    assert len(entries) == 2
    assert {e.action for e in entries} == {"Backup", "Uninstall App"}


def test_action_log_order_is_stable_within_same_second(temp_db, monkeypatch):
    # Paksa created_at identik untuk mensimulasikan dua aksi dalam detik
    # yang sama (skenario realistis kalau technician klik cepat).
    class FixedDatetime:
        @staticmethod
        def now():
            import datetime as real_datetime
            return real_datetime.datetime(2026, 1, 1, 12, 0, 0)

    monkeypatch.setattr(temp_db, "datetime", FixedDatetime)

    temp_db.log_action("Backup", status="OK", serial="SN1")
    temp_db.log_action("Restore", status="OK", serial="SN1")
    temp_db.log_action("Flash Partition", status="OK", serial="SN1")

    entries = temp_db.get_action_log(serial="SN1")
    assert [e.action for e in entries] == ["Flash Partition", "Restore", "Backup"]


def test_action_log_filters_by_serial(temp_db):
    temp_db.log_action("Backup", serial="SN1", status="OK")
    temp_db.log_action("Backup", serial="SN2", status="OK")

    assert len(temp_db.get_action_log(serial="SN1")) == 1
    assert len(temp_db.get_action_log(serial="SN2")) == 1
    assert len(temp_db.get_action_log()) == 2


def test_action_log_default_technician_is_generic(temp_db):
    # Kalau technician tidak diisi eksplisit, harus fallback ke default
    # generik "Technician" (bukan string kosong) - konsisten dengan
    # perilaku sebelum fitur identitas teknisi ditambahkan.
    temp_db.log_action("Backup", serial="SN1", status="OK")
    entries = temp_db.get_action_log(serial="SN1")
    assert entries[0].technician == "Technician"


def test_action_log_records_specific_technician(temp_db):
    temp_db.log_action("Flash Partition", serial="SN1", status="OK", technician="Budi")
    entries = temp_db.get_action_log(serial="SN1")
    assert entries[0].technician == "Budi"
