"""Test untuk fitur baru sesi ini:
- PIN kunci halaman Settings (core/settings.py)
- Business summary & export CSV (core/service_cases.py)
- Search case by nomor HP (bug fix)
- Modul stok sparepart (core/parts.py)
"""
import tempfile
from pathlib import Path

import pytest

from core.settings import SettingsStore
from core.parts import (
    add_part, list_parts, update_stock, use_part, delete_part,
    get_usage_for_case,
)


# ------------------------------------------------------------------
# PIN Settings
# ------------------------------------------------------------------
def test_pin_not_set_by_default(tmp_path):
    s = SettingsStore(path=tmp_path / "settings.json")
    assert s.has_pin() is False
    assert s.verify_pin("1234") is False


def test_set_and_verify_pin(tmp_path):
    s = SettingsStore(path=tmp_path / "settings.json")
    s.set_pin("1234")
    assert s.has_pin() is True
    assert s.verify_pin("1234") is True
    assert s.verify_pin("9999") is False


def test_pin_persists_across_reload(tmp_path):
    path = tmp_path / "settings.json"
    s1 = SettingsStore(path=path)
    s1.set_pin("5678")

    s2 = SettingsStore(path=path)
    assert s2.verify_pin("5678") is True


def test_clear_pin(tmp_path):
    s = SettingsStore(path=tmp_path / "settings.json")
    s.set_pin("1234")
    s.clear_pin()
    assert s.has_pin() is False
    assert s.verify_pin("1234") is False


def test_pin_hash_is_not_plaintext(tmp_path):
    s = SettingsStore(path=tmp_path / "settings.json")
    s.set_pin("1234")
    stored = s.get("settings_pin_hash", "")
    assert stored != "1234"
    assert len(stored) > 10  # hash, bukan angka pendek


# ------------------------------------------------------------------
# Business Summary & CSV Export
# ------------------------------------------------------------------
@pytest.fixture()
def db(tmp_path, monkeypatch):
    import core.service_cases as sc
    monkeypatch.setattr(sc, "DB_PATH", tmp_path / "test_cases.db")
    return sc


def test_search_case_by_phone_number(db):
    db.create_case(customer_name="Budi", complaint="Layar retak", customer_phone="081234567890")
    db.create_case(customer_name="Ani", complaint="Baterai boros", customer_phone="089876543210")

    results = db.list_cases(search="081234567890")
    assert len(results) == 1
    assert results[0].customer_name == "Budi"

    partial = db.list_cases(search="0812")
    assert len(partial) == 1


def test_business_summary_counts_and_revenue(db):
    c1 = db.create_case(customer_name="Budi", complaint="Layar retak", estimated_cost=200000)
    db.update_payment(c1.id, "Lunas", 200000)
    db.update_status(c1.id, "Completed")

    c2 = db.create_case(customer_name="Ani", complaint="Baterai", estimated_cost=100000)
    db.update_payment(c2.id, "DP", 30000)

    c3 = db.create_case(customer_name="Citra", complaint="Charging port", estimated_cost=50000)
    db.update_status(c3.id, "Cancelled")

    today = db.datetime.now().strftime("%Y-%m-%d")
    summary = db.get_business_summary(today, today)

    assert summary.total_cases == 3
    assert summary.completed_cases == 1
    assert summary.cancelled_cases == 1
    assert summary.total_revenue == 230000
    assert summary.outstanding_balance == 70000  # hanya c2 (c3 cancelled diabaikan)


def test_business_summary_excludes_outside_date_range(db):
    db.create_case(customer_name="Budi", complaint="Test", estimated_cost=100000)

    summary = db.get_business_summary("2000-01-01", "2000-01-02")
    assert summary.total_cases == 0


def test_export_cases_csv(db, tmp_path):
    db.create_case(customer_name="Budi Santoso", complaint="Layar retak", estimated_cost=200000)
    db.create_case(customer_name="Ani", complaint="Baterai boros", estimated_cost=100000)

    output = db.export_cases_csv(tmp_path / "export.csv")
    assert output.exists()

    content = output.read_text(encoding="utf-8-sig")
    assert "Budi Santoso" in content
    assert "Ani" in content
    assert "case_number" in content  # header


# ------------------------------------------------------------------
# Stok Sparepart
# ------------------------------------------------------------------
@pytest.fixture()
def parts_db(tmp_path, monkeypatch):
    import core.parts as p
    monkeypatch.setattr(p, "DB_PATH", tmp_path / "test_parts.db")
    return p


def test_add_part_and_list(parts_db):
    part = parts_db.add_part("LCD Redmi Note 10", category="LCD", stock_qty=5, min_stock=2, unit_price=250000)
    assert part.stock_qty == 5

    results = parts_db.list_parts()
    assert len(results) == 1
    assert results[0].name == "LCD Redmi Note 10"


def test_add_part_rejects_empty_name(parts_db):
    with pytest.raises(ValueError):
        parts_db.add_part("")


def test_add_part_rejects_negative_values(parts_db):
    with pytest.raises(ValueError):
        parts_db.add_part("Test Part", stock_qty=-1)


def test_use_part_reduces_stock(parts_db):
    part = parts_db.add_part("Baterai A32", stock_qty=10)
    updated = parts_db.use_part(part.id, 3)
    assert updated.stock_qty == 7


def test_use_part_rejects_insufficient_stock(parts_db):
    part = parts_db.add_part("Baterai A32", stock_qty=2)
    with pytest.raises(ValueError):
        parts_db.use_part(part.id, 100)

    # Stok tidak boleh berubah kalau ditolak
    unchanged = parts_db.list_parts()[0]
    assert unchanged.stock_qty == 2


def test_use_part_rejects_zero_or_negative_quantity(parts_db):
    part = parts_db.add_part("Test Part", stock_qty=10)
    with pytest.raises(ValueError):
        parts_db.use_part(part.id, 0)
    with pytest.raises(ValueError):
        parts_db.use_part(part.id, -5)


def test_use_part_records_usage_linked_to_case(parts_db):
    part = parts_db.add_part("LCD", stock_qty=10)
    parts_db.use_part(part.id, 2, case_id=42, note="Dipasang di case #42")

    usage = parts_db.get_usage_for_case(42)
    assert len(usage) == 1
    assert usage[0].quantity == 2
    assert usage[0].part_name == "LCD"


def test_low_stock_filter(parts_db):
    parts_db.add_part("Part Aman", stock_qty=50, min_stock=5)
    parts_db.add_part("Part Menipis", stock_qty=1, min_stock=5)

    low_stock = parts_db.list_parts(low_stock_only=True)
    assert len(low_stock) == 1
    assert low_stock[0].name == "Part Menipis"


def test_update_stock_restock(parts_db):
    part = parts_db.add_part("Test Part", stock_qty=5)
    updated = parts_db.update_stock(part.id, 100)
    assert updated.stock_qty == 100


def test_update_stock_rejects_negative(parts_db):
    part = parts_db.add_part("Test Part", stock_qty=5)
    with pytest.raises(ValueError):
        parts_db.update_stock(part.id, -1)


def test_delete_part(parts_db):
    part = parts_db.add_part("Test Part", stock_qty=5)
    parts_db.delete_part(part.id)
    assert parts_db.list_parts() == []


def test_search_parts_by_name_or_category(parts_db):
    parts_db.add_part("LCD Redmi Note 10", category="LCD")
    parts_db.add_part("Baterai A32", category="Baterai")

    results = parts_db.list_parts(search="LCD")
    assert len(results) == 1
    assert results[0].name == "LCD Redmi Note 10"

    results2 = parts_db.list_parts(search="Baterai")
    assert len(results2) == 1
