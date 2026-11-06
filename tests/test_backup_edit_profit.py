"""Test untuk fitur baru: backup database aplikasi, edit data case,
biaya sparepart terpakai, dan breakdown laporan per teknisi.
"""
import time
from pathlib import Path

import pytest

from core.db_backup import (
    backup_app_database,
    get_last_backup_time,
    should_auto_backup,
    cleanup_old_app_backups,
    restore_app_database,
)


# ------------------------------------------------------------------
# Backup Database Aplikasi
# ------------------------------------------------------------------
@pytest.fixture()
def fake_app_db(tmp_path, monkeypatch):
    import core.db_backup as dbb

    fake_db = tmp_path / "nexa_service.db"
    fake_settings = tmp_path / "settings.json"
    fake_db.write_text("fake db content")
    fake_settings.write_text('{"test": true}')

    monkeypatch.setattr(dbb, "APP_DB_PATH", fake_db)
    monkeypatch.setattr(dbb, "APP_SETTINGS_PATH", fake_settings)

    return dbb, tmp_path


def test_backup_creates_zip_with_db_and_settings(fake_app_db):
    dbb, tmp_path = fake_app_db
    backup_dir = tmp_path / "backups"

    zip_path = dbb.backup_app_database(backup_dir)
    assert zip_path is not None
    assert zip_path.exists()


def test_backup_returns_none_when_no_database(tmp_path, monkeypatch):
    import core.db_backup as dbb
    monkeypatch.setattr(dbb, "APP_DB_PATH", tmp_path / "does_not_exist.db")

    result = dbb.backup_app_database(tmp_path / "backups")
    assert result is None


def test_should_auto_backup_true_when_never_backed_up(fake_app_db):
    dbb, tmp_path = fake_app_db
    backup_dir = tmp_path / "backups"
    assert dbb.should_auto_backup(backup_dir) is True


def test_should_auto_backup_false_right_after_backup(fake_app_db):
    dbb, tmp_path = fake_app_db
    backup_dir = tmp_path / "backups"
    dbb.backup_app_database(backup_dir)
    assert dbb.should_auto_backup(backup_dir, interval_hours=24) is False


def test_restore_creates_safety_backup_first(fake_app_db):
    dbb, tmp_path = fake_app_db
    backup_dir = tmp_path / "backups"
    zip_path = dbb.backup_app_database(backup_dir)

    restore_target = tmp_path / "restored"
    restore_target.mkdir()
    results = dbb.restore_app_database(zip_path, restore_target)

    assert (restore_target / "nexa_service.db").exists()
    assert (restore_target / "settings.json").exists()
    assert any("pengaman" in r for r in results)


def test_restore_rejects_zip_slip(tmp_path):
    import zipfile
    import core.db_backup as dbb

    malicious_zip = tmp_path / "evil.zip"
    with zipfile.ZipFile(malicious_zip, "w") as zf:
        zf.writestr("../../etc/evil.db", "malicious")

    restore_target = tmp_path / "restored"
    restore_target.mkdir()

    with pytest.raises(ValueError):
        dbb.restore_app_database(malicious_zip, restore_target)


def test_cleanup_old_backups_respects_retention(fake_app_db):
    import os
    dbb, tmp_path = fake_app_db
    backup_dir = tmp_path / "backups"
    zip_path = dbb.backup_app_database(backup_dir)

    old_time = time.time() - (60 * 24 * 3600)
    os.utime(zip_path, (old_time, old_time))

    removed = dbb.cleanup_old_app_backups(backup_dir, retention_days=30)
    assert removed == 1
    assert not zip_path.exists()


# ------------------------------------------------------------------
# Edit Data Case
# ------------------------------------------------------------------
@pytest.fixture()
def db(tmp_path, monkeypatch):
    import core.service_cases as sc
    monkeypatch.setattr(sc, "DB_PATH", tmp_path / "test_cases.db")
    return sc


def test_update_case_info_changes_fields(db):
    case = db.create_case(customer_name="Budi", complaint="Layar retak", customer_phone="08111")
    updated = db.update_case_info(case.id, customer_name="Budi Edited", customer_phone="08999")

    assert updated.customer_name == "Budi Edited"
    assert updated.customer_phone == "08999"
    assert updated.complaint == "Layar retak"  # tidak diubah


def test_update_case_info_rejects_empty_name(db):
    case = db.create_case(customer_name="Budi", complaint="Test")
    with pytest.raises(ValueError):
        db.update_case_info(case.id, customer_name="")


def test_update_case_info_rejects_empty_complaint(db):
    case = db.create_case(customer_name="Budi", complaint="Test")
    with pytest.raises(ValueError):
        db.update_case_info(case.id, complaint="   ")


def test_update_case_info_records_timeline_event(db):
    case = db.create_case(customer_name="Budi", complaint="Test")
    db.update_case_info(case.id, customer_name="Budi Baru")

    timeline = db.get_timeline(case.id)
    edit_events = [e for e in timeline if e["event_type"] == "edit"]
    assert len(edit_events) == 1
    assert "Budi" in edit_events[0]["note"]


def test_update_case_info_no_event_when_nothing_changed(db):
    case = db.create_case(customer_name="Budi", complaint="Test")
    db.update_case_info(case.id, customer_name="Budi")  # sama persis

    timeline = db.get_timeline(case.id)
    edit_events = [e for e in timeline if e["event_type"] == "edit"]
    assert len(edit_events) == 0


# ------------------------------------------------------------------
# Profit & Technician Breakdown
# ------------------------------------------------------------------
@pytest.fixture()
def parts_db(tmp_path, monkeypatch):
    import core.parts as p
    monkeypatch.setattr(p, "DB_PATH", tmp_path / "test_cases.db")
    return p


def test_technician_breakdown_groups_correctly(db):
    c1 = db.create_case(customer_name="A", complaint="X", technician="Ani", estimated_cost=100000)
    db.update_payment(c1.id, "Lunas", 100000)
    db.update_status(c1.id, "Completed")

    c2 = db.create_case(customer_name="B", complaint="Y", technician="Ani", estimated_cost=50000)
    db.update_payment(c2.id, "DP", 20000)

    c3 = db.create_case(customer_name="C", complaint="Z", technician="Budi", estimated_cost=80000)
    db.update_payment(c3.id, "Lunas", 80000)
    db.update_status(c3.id, "Completed")

    today = db.datetime.now().strftime("%Y-%m-%d")
    summary = db.get_business_summary(today, today)

    assert summary.technician_breakdown["Ani"]["total_cases"] == 2
    assert summary.technician_breakdown["Ani"]["completed_cases"] == 1
    assert summary.technician_breakdown["Ani"]["revenue"] == 120000
    assert summary.technician_breakdown["Budi"]["completed_cases"] == 1


def test_technician_breakdown_handles_missing_technician(db):
    db.create_case(customer_name="A", complaint="X", estimated_cost=0)  # tanpa technician

    today = db.datetime.now().strftime("%Y-%m-%d")
    summary = db.get_business_summary(today, today)

    assert "(Belum diisi)" in summary.technician_breakdown


def test_get_total_usage_cost_sums_correctly(db, parts_db):
    part = parts_db.add_part("LCD", stock_qty=10, unit_price=100000)
    parts_db.use_part(part.id, 2)

    part2 = parts_db.add_part("Baterai", stock_qty=10, unit_price=50000)
    parts_db.use_part(part2.id, 1)

    today = db.datetime.now().strftime("%Y-%m-%d")
    cost = parts_db.get_total_usage_cost(today, today)

    assert cost == 250000  # (2*100000) + (1*50000)


def test_get_total_usage_cost_zero_when_no_usage(parts_db):
    cost = parts_db.get_total_usage_cost("2000-01-01", "2000-01-02")
    assert cost == 0.0


def test_net_profit_calculation(db, parts_db):
    case = db.create_case(customer_name="A", complaint="X", estimated_cost=300000)
    db.update_payment(case.id, "Lunas", 300000)

    part = parts_db.add_part("LCD", stock_qty=10, unit_price=120000)
    parts_db.use_part(part.id, 1, case_id=case.id)

    today = db.datetime.now().strftime("%Y-%m-%d")
    summary = db.get_business_summary(today, today)
    parts_cost = parts_db.get_total_usage_cost(today, today)
    net_profit = summary.total_revenue - parts_cost

    assert net_profit == 180000  # 300000 - 120000
