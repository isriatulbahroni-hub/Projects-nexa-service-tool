"""Tes untuk perbaikan hasil audit: FRP tanpa fastboot, backup DB aplikasi, kasus servis."""
import sqlite3
import zipfile

import pytest

from core.firmware import FastbootError


# --- FRP: fastboot tidak terpasang -------------------------------------------
def test_detect_frp_state_without_fastboot_does_not_raise():
    from core.frp_service import detect_frp_service_state

    def no_fastboot():
        raise FastbootError("Fastboot tidak ditemukan")

    state = detect_frp_service_state(
        "ABC",
        devices_fn=lambda: {"ABC": "unauthorized"},
        fastboot_fn=no_fastboot,
    )
    assert state.fastboot_connected is False
    assert state.owner_auth_required is True


# --- Backup DB aplikasi ------------------------------------------------------
@pytest.fixture()
def app_data(tmp_path, monkeypatch):
    import core.db_backup as dbb

    db = tmp_path / "nexa_service.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE t (v TEXT)")
    conn.execute("INSERT INTO t VALUES ('halo')")
    conn.commit()
    conn.close()
    settings = tmp_path / "settings.json"
    settings.write_text("{}")
    (tmp_path / "technicians.json").write_text('{"admin": {}}')
    (tmp_path / "license.json").write_text('{"key": "x"}')
    photos = tmp_path / "case_photos" / "NS-1"
    photos.mkdir(parents=True)
    (photos / "a.jpg").write_bytes(b"jpg")
    monkeypatch.setattr(dbb, "APP_DB_PATH", db)
    monkeypatch.setattr(dbb, "APP_SETTINGS_PATH", settings)
    return dbb, tmp_path


def test_backup_includes_accounts_and_license_but_photos_optional(app_data):
    dbb, tmp_path = app_data
    names = zipfile.ZipFile(dbb.backup_app_database(tmp_path / "b1")).namelist()
    assert {"nexa_service.db", "settings.json", "technicians.json", "license.json"} <= set(names)
    assert not any(n.startswith("case_photos") for n in names)

    names = zipfile.ZipFile(dbb.backup_app_database(tmp_path / "b2", include_photos=True)).namelist()
    assert "case_photos/NS-1/a.jpg" in names


def test_backup_snapshot_is_valid_sqlite_and_encrypted_roundtrip(app_data):
    dbb, tmp_path = app_data
    zip_path = dbb.backup_app_database(tmp_path / "enc", password="rahasia123")
    assert dbb.is_app_backup_encrypted(zip_path)

    target = tmp_path / "restored"
    target.mkdir()
    with pytest.raises(dbb.AppBackupError):
        dbb.restore_app_database(zip_path, target)  # tanpa password
    dbb.restore_app_database(zip_path, target, password="rahasia123")

    rows = sqlite3.connect(target / "nexa_service.db").execute("SELECT v FROM t").fetchall()
    assert rows == [("halo",)]
    assert (target / "technicians.json").exists()


def test_restore_prunes_old_safety_backups(app_data):
    dbb, tmp_path = app_data
    zip_path = dbb.backup_app_database(tmp_path / "b")
    target = tmp_path / "restored"
    safety = target / dbb.SAFETY_DIRNAME
    safety.mkdir(parents=True)
    for i in range(8):
        (safety / f"nexa_app_backup_2020010{i}_000000.zip").write_bytes(b"x")
    dbb.restore_app_database(zip_path, target)
    assert len(list(safety.glob("nexa_app_backup_*.zip"))) <= dbb.SAFETY_KEEP


# --- Kasus servis ------------------------------------------------------------
@pytest.fixture()
def sc(tmp_path, monkeypatch):
    import core.service_cases as m

    monkeypatch.setattr(m, "DB_PATH", tmp_path / "cases.db")
    monkeypatch.setattr(m, "DATA_DIR", tmp_path)
    return m


def test_cancelled_case_payment_not_counted_as_revenue(sc):
    ok = sc.create_case(customer_name="A", complaint="x", estimated_cost=100000)
    sc.update_payment(ok.id, "Lunas", 100000)
    gone = sc.create_case(customer_name="B", complaint="y", estimated_cost=50000)
    sc.update_payment(gone.id, "DP", 20000)
    sc.update_status(gone.id, "Cancelled")

    today = sc.datetime.now().strftime("%Y-%m-%d")
    summary = sc.get_business_summary(today, today)
    assert summary.total_revenue == 100000


def test_lunas_with_gap_is_recorded_in_timeline(sc):
    case = sc.create_case(customer_name="A", complaint="x", estimated_cost=100000)
    sc.update_payment(case.id, "Lunas", 90000)
    notes = [e["note"] for e in sc.get_timeline(case.id) if e["event_type"] == "payment"]
    assert any("selisih" in n for n in notes)


def test_update_estimated_cost_logged_and_validated(sc):
    case = sc.create_case(customer_name="A", complaint="x", estimated_cost=100000)
    updated = sc.update_estimated_cost(case.id, 150000)
    assert updated.estimated_cost == 150000
    assert any(e["event_type"] == "edit" and e["new_value"] == "Rp150,000" for e in sc.get_timeline(case.id))
    with pytest.raises(ValueError):
        sc.update_estimated_cost(case.id, -1)


def test_delete_photo_removes_managed_file_only(sc, tmp_path):
    case = sc.create_case(customer_name="A", complaint="x")
    managed_dir = tmp_path / "case_photos" / case.case_number
    managed_dir.mkdir(parents=True)
    managed = managed_dir / "m.jpg"
    managed.write_bytes(b"1")
    outside = tmp_path / "luar.jpg"
    outside.write_bytes(b"2")

    p1 = sc.add_photo(case.id, str(managed))
    p2 = sc.add_photo(case.id, str(outside))
    sc.delete_photo(p1.id)
    sc.delete_photo(p2.id)

    assert not managed.exists()
    assert outside.exists()
    assert sc.get_photos(case.id) == []
