"""Tes perbaikan audit pada core/service_cases.py."""
import csv
import sqlite3
from datetime import datetime, timedelta

import pytest

import core.service_cases as sc


@pytest.fixture()
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "DB_PATH", tmp_path / "cases.db")
    return sc


def test_case_number_never_collides_after_gaps(db):
    c1 = db.create_case("A", "x")
    c2 = db.create_case("B", "y")
    conn = sqlite3.connect(str(db.DB_PATH))
    conn.execute("DELETE FROM service_cases WHERE id = ?", (c1.id,))  # lubang di urutan
    conn.commit()
    conn.close()
    c3 = db.create_case("C", "z")
    assert c3.case_number != c2.case_number
    assert int(c3.case_number[-4:]) == int(c2.case_number[-4:]) + 1


def test_foreign_keys_enforced_and_cascade(db):
    case = db.create_case("A", "x")
    db.add_note(case.id, "catatan")
    conn = db._connection()
    try:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        conn.execute("DELETE FROM service_cases WHERE id = ?", (case.id,))
        conn.commit()
        assert conn.execute("SELECT COUNT(*) FROM service_case_events").fetchone()[0] == 0
    finally:
        conn.close()


def test_csv_export_neutralizes_formulas_but_keeps_phone_numbers(db, tmp_path):
    db.create_case("=HYPERLINK(\"http://evil\",\"x\")", "@SUM(A1)", customer_phone="+62 812-3456-7890", notes="-2+3")
    out = db.export_cases_csv(tmp_path / "out.csv")
    with open(out, encoding="utf-8-sig", newline="") as f:
        row = next(csv.DictReader(f))
    assert row["customer_name"].startswith("'=")
    assert row["complaint"].startswith("'@")
    assert row["notes"].startswith("'-")
    assert row["customer_phone"] == "+62 812-3456-7890"


def test_payment_status_and_amount_must_be_consistent(db):
    case = db.create_case("A", "x", estimated_cost=100000)
    with pytest.raises(ValueError):
        db.update_payment(case.id, "Lunas", 0)
    with pytest.raises(ValueError):
        db.update_payment(case.id, "DP", 0)
    with pytest.raises(ValueError):
        db.update_payment(case.id, "Belum Bayar", 5000)
    with pytest.raises(ValueError):
        db.update_payment(case.id, "Lunas", float("nan"))
    with pytest.raises(ValueError):
        db.update_payment(case.id, "Lunas", float("inf"))
    assert db.update_payment(case.id, "Belum Bayar", 0).paid_amount == 0


def test_summary_rejects_invalid_or_reversed_dates(db):
    for start, end in [("bukan-tanggal", "2026-01-01"), ("2026-02-31", "2026-03-01"), ("2026-03-02", "2026-03-01")]:
        with pytest.raises(ValueError):
            db.get_business_summary(start, end)
    with pytest.raises(ValueError):
        db.export_cases_csv("x.csv", "2026-03-02", "2026-03-01")


def test_turnaround_uses_completion_event_not_last_edit(db):
    case = db.create_case("A", "x")
    created = datetime.now().replace(microsecond=0) - timedelta(hours=10)
    done = created + timedelta(hours=2)
    later_edit = created + timedelta(hours=9)
    conn = sqlite3.connect(str(db.DB_PATH))
    conn.execute("UPDATE service_cases SET created_at=?, updated_at=?, status='Completed' WHERE id=?",
                 (created.isoformat(), later_edit.isoformat(), case.id))
    conn.execute("INSERT INTO service_case_events (case_id, event_type, old_value, new_value, created_at) "
                 "VALUES (?, 'status', 'Testing', 'Completed', ?)", (case.id, done.isoformat()))
    conn.commit()
    conn.close()
    today = created.strftime("%Y-%m-%d")
    summary = db.get_business_summary(today, today)
    assert summary.avg_turnaround_hours == pytest.approx(2.0, abs=0.01)
