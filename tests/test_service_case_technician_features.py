"""Test untuk fitur teknisi service center yang baru ditambahkan ke
Service Cases: dokumentasi foto, tracking pembayaran, cetak nota/label,
notifikasi WhatsApp, dan SLA (estimasi selesai).
"""
import shutil
import tempfile
from pathlib import Path

import pytest

pytest.importorskip("reportlab")

from core.service_cases import (
    create_case,
    update_payment,
    add_photo,
    get_photos,
    delete_photo,
    update_estimated_completion,
    get_timeline,
    PAYMENT_STATUSES,
)
from core.invoice import generate_case_invoice, generate_case_label
from core.whatsapp import normalize_phone_number, build_whatsapp_link, build_case_status_message


@pytest.fixture()
def db(tmp_path, monkeypatch):
    import core.service_cases as sc
    monkeypatch.setattr(sc, "DB_PATH", tmp_path / "test_cases.db")
    return sc


def test_create_case_with_sla(db):
    case = db.create_case(
        customer_name="Budi", complaint="Layar retak",
        estimated_cost=150000, estimated_completion="2026-08-20",
    )
    assert case.payment_status == "Belum Bayar"
    assert case.paid_amount == 0
    assert case.estimated_completion == "2026-08-20"


def test_update_payment_records_event(db):
    case = db.create_case(customer_name="Budi", complaint="Baterai boros", estimated_cost=100000)
    updated = db.update_payment(case.id, "DP", 30000, note="DP awal")
    assert updated.payment_status == "DP"
    assert updated.paid_amount == 30000

    updated2 = db.update_payment(case.id, "Lunas", 100000)
    assert updated2.payment_status == "Lunas"

    timeline = db.get_timeline(case.id)
    payment_events = [e for e in timeline if e["event_type"] == "payment"]
    assert len(payment_events) == 2


def test_update_payment_rejects_invalid_status(db):
    case = db.create_case(customer_name="Budi", complaint="Test", estimated_cost=0)
    with pytest.raises(ValueError):
        db.update_payment(case.id, "Status Ngawur", 0)


def test_update_payment_rejects_negative_amount(db):
    case = db.create_case(customer_name="Budi", complaint="Test", estimated_cost=0)
    with pytest.raises(ValueError):
        db.update_payment(case.id, "DP", -1000)


def test_add_and_get_photos(db, tmp_path):
    case = db.create_case(customer_name="Budi", complaint="Layar retak", estimated_cost=0)

    fake_photo = tmp_path / "foto1.jpg"
    fake_photo.write_bytes(b"fake jpeg data")

    photo = db.add_photo(case.id, str(fake_photo), caption="Kondisi awal - layar retak")
    assert photo.caption == "Kondisi awal - layar retak"

    photos = db.get_photos(case.id)
    assert len(photos) == 1
    assert photos[0].photo_path == str(fake_photo)

    timeline = db.get_timeline(case.id)
    assert any(e["event_type"] == "photo" for e in timeline)


def test_delete_photo(db, tmp_path):
    case = db.create_case(customer_name="Budi", complaint="Test", estimated_cost=0)
    fake_photo = tmp_path / "foto1.jpg"
    fake_photo.write_bytes(b"data")
    photo = db.add_photo(case.id, str(fake_photo))

    db.delete_photo(photo.id)
    assert db.get_photos(case.id) == []


def test_update_estimated_completion(db):
    case = db.create_case(customer_name="Budi", complaint="Test", estimated_cost=0)
    updated = db.update_estimated_completion(case.id, "2026-09-01")
    assert updated.estimated_completion == "2026-09-01"


def test_old_database_migrates_new_columns(tmp_path, monkeypatch):
    """Database yang dibuat SEBELUM fitur payment/photo/SLA ditambahkan
    harus tetap bisa dipakai tanpa hilang data - kolom baru ditambahkan
    otomatis lewat migrasi ringan (ALTER TABLE)."""
    import sqlite3
    import core.service_cases as sc

    db_path = tmp_path / "old.db"
    monkeypatch.setattr(sc, "DB_PATH", db_path)

    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE service_cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_number TEXT NOT NULL UNIQUE,
            customer_name TEXT NOT NULL,
            customer_phone TEXT DEFAULT '',
            device_serial TEXT DEFAULT '',
            imei TEXT DEFAULT '',
            manufacturer TEXT DEFAULT '',
            model TEXT DEFAULT '',
            complaint TEXT NOT NULL,
            technician TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'Received',
            estimated_cost REAL NOT NULL DEFAULT 0,
            notes TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    conn.execute(
        "INSERT INTO service_cases (case_number, customer_name, complaint, created_at, updated_at) "
        "VALUES ('OLD-001', 'Pelanggan Lama', 'Baterai boros', '2026-01-01', '2026-01-01')"
    )
    conn.commit()
    conn.close()

    sc.init_service_cases()
    cases = sc.list_cases()
    assert len(cases) == 1
    assert cases[0].payment_status == "Belum Bayar"
    assert cases[0].paid_amount == 0

    updated = sc.update_payment(cases[0].id, "Lunas", 100000)
    assert updated.payment_status == "Lunas"


def _sample_case(db):
    return db.create_case(
        customer_name="Budi Santoso", complaint="Layar retak dan baterai boros",
        customer_phone="081234567890", manufacturer="Xiaomi", model="Redmi Note 10",
        technician="Ani", estimated_cost=350000, estimated_completion="2026-08-20",
    )


def test_generate_case_invoice(db, tmp_path):
    case = _sample_case(db)
    db.update_payment(case.id, "DP", 100000)
    case = db.get_case(case.id)

    output = generate_case_invoice(case, tmp_path / "nota.pdf")
    assert output.exists()
    assert output.stat().st_size > 0


def test_generate_case_label(db, tmp_path):
    case = _sample_case(db)
    output = generate_case_label(case, tmp_path / "label.pdf")
    assert output.exists()
    assert output.stat().st_size > 0


def test_whatsapp_normalize_phone_number():
    assert normalize_phone_number("081234567890") == "6281234567890"
    assert normalize_phone_number("+6281234567890") == "6281234567890"
    assert normalize_phone_number("6281234567890") == "6281234567890"
    assert normalize_phone_number("") == ""


def test_whatsapp_build_link_rejects_empty_phone():
    with pytest.raises(ValueError):
        build_whatsapp_link("", "test message")


def test_whatsapp_build_link_success():
    link = build_whatsapp_link("081234567890", "Halo dunia")
    assert link.startswith("https://wa.me/6281234567890?text=")


def test_whatsapp_status_message_for_completed_case(db):
    case = _sample_case(db)
    db_updated = db.update_status(case.id, "Completed")
    message = build_case_status_message(db_updated)
    assert "SELESAI" in message
    assert case.case_number in message


def test_whatsapp_status_message_includes_sla_when_not_done(db):
    case = _sample_case(db)
    message = build_case_status_message(case)
    assert "2026-08-20" in message
