"""Service-center case management with SQLite persistence.

Keeps customer/job information separate from diagnostic history while linking
cases to the device serial/IMEI when available.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .config import PROJECT_ROOT

DB_PATH = PROJECT_ROOT / "data" / "nexa_service.db"

STATUSES = ("Received", "Diagnosing", "Repairing", "Testing", "Completed", "Cancelled")
PAYMENT_STATUSES = ("Belum Bayar", "DP", "Lunas")


@dataclass(frozen=True)
class ServiceCase:
    id: int
    case_number: str
    customer_name: str
    customer_phone: str
    device_serial: str
    imei: str
    manufacturer: str
    model: str
    complaint: str
    technician: str
    status: str
    estimated_cost: float
    notes: str
    created_at: str
    updated_at: str
    payment_status: str = "Belum Bayar"
    paid_amount: float = 0.0
    estimated_completion: str = ""


@dataclass(frozen=True)
class CasePhoto:
    id: int
    case_id: int
    photo_path: str
    caption: str
    created_at: str


def _connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    """Migrasi ringan: tambah kolom kalau belum ada, supaya database yang
    sudah ada (dibuat sebelum fitur ini ditambahkan) tidak perlu dihapus
    manual - CREATE TABLE IF NOT EXISTS saja tidak menambah kolom baru ke
    tabel yang sudah eksis sebelumnya."""
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def init_service_cases() -> None:
    conn = _connection()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS service_cases (
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
            CREATE TABLE IF NOT EXISTS service_case_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                old_value TEXT DEFAULT '',
                new_value TEXT DEFAULT '',
                note TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY(case_id) REFERENCES service_cases(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS service_case_photos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id INTEGER NOT NULL,
                photo_path TEXT NOT NULL,
                caption TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY(case_id) REFERENCES service_cases(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_service_cases_status ON service_cases(status);
            CREATE INDEX IF NOT EXISTS idx_service_cases_serial ON service_cases(device_serial);
            CREATE INDEX IF NOT EXISTS idx_service_case_events_case ON service_case_events(case_id);
            CREATE INDEX IF NOT EXISTS idx_service_case_photos_case ON service_case_photos(case_id);
            """
        )
        # Migrasi kolom baru (payment tracking, SLA) untuk database yang
        # sudah ada dari sebelum fitur ini ditambahkan.
        _ensure_column(conn, "service_cases", "payment_status", "TEXT NOT NULL DEFAULT 'Belum Bayar'")
        _ensure_column(conn, "service_cases", "paid_amount", "REAL NOT NULL DEFAULT 0")
        _ensure_column(conn, "service_cases", "estimated_completion", "TEXT DEFAULT ''")
        conn.commit()
    finally:
        conn.close()


def _case(row: sqlite3.Row) -> ServiceCase:
    return ServiceCase(**dict(row))


def _new_case_number(conn: sqlite3.Connection) -> str:
    stamp = datetime.now().strftime("%Y%m%d")
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM service_cases WHERE case_number LIKE ?",
        (f"NS-{stamp}-%",),
    ).fetchone()
    return f"NS-{stamp}-{int(row['n']) + 1:04d}"


def create_case(
    customer_name: str,
    complaint: str,
    *,
    customer_phone: str = "",
    device_serial: str = "",
    imei: str = "",
    manufacturer: str = "",
    model: str = "",
    technician: str = "",
    estimated_cost: float = 0,
    notes: str = "",
    estimated_completion: str = "",
) -> ServiceCase:
    if not customer_name.strip():
        raise ValueError("customer_name is required")
    if not complaint.strip():
        raise ValueError("complaint is required")
    if estimated_cost < 0:
        raise ValueError("estimated_cost cannot be negative")

    init_service_cases()
    now = datetime.now().isoformat(timespec="seconds")
    conn = _connection()
    try:
        case_number = _new_case_number(conn)
        cur = conn.execute(
            """INSERT INTO service_cases
            (case_number, customer_name, customer_phone, device_serial, imei,
             manufacturer, model, complaint, technician, status, estimated_cost, notes,
             created_at, updated_at, payment_status, paid_amount, estimated_completion)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Received', ?, ?, ?, ?, 'Belum Bayar', 0, ?)""",
            (case_number, customer_name.strip(), customer_phone.strip(),
             device_serial.strip(), imei.strip(), manufacturer.strip(),
             model.strip(), complaint.strip(), technician.strip(), float(estimated_cost),
             notes.strip(), now, now, estimated_completion.strip()),
        )
        case_id = cur.lastrowid
        conn.execute(
            "INSERT INTO service_case_events (case_id, event_type, new_value, note, created_at) VALUES (?, 'created', 'Received', ?, ?)",
            (case_id, notes.strip(), now),
        )
        conn.commit()
        return get_case(case_id)
    finally:
        conn.close()


def get_case(case_id: int) -> ServiceCase:
    init_service_cases()
    conn = _connection()
    try:
        row = conn.execute("SELECT * FROM service_cases WHERE id = ?", (case_id,)).fetchone()
        if row is None:
            raise KeyError(f"service case {case_id} not found")
        return _case(row)
    finally:
        conn.close()


def list_cases(status: str | None = None, search: str = "", limit: int = 200) -> list[ServiceCase]:
    init_service_cases()
    if status and status not in STATUSES:
        raise ValueError(f"invalid status: {status}")
    limit = max(1, min(int(limit), 1000))
    conn = _connection()
    try:
        clauses = []
        params: list[object] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if search.strip():
            like = f"%{search.strip()}%"
            clauses.append(
                "(case_number LIKE ? OR customer_name LIKE ? OR customer_phone LIKE ? "
                "OR device_serial LIKE ? OR imei LIKE ? OR model LIKE ?)"
            )
            params.extend([like] * 6)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = conn.execute(
            f"SELECT * FROM service_cases {where} ORDER BY updated_at DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
        return [_case(row) for row in rows]
    finally:
        conn.close()


def update_status(case_id: int, status: str, note: str = "") -> ServiceCase:
    if status not in STATUSES:
        raise ValueError(f"invalid status: {status}")
    init_service_cases()
    now = datetime.now().isoformat(timespec="seconds")
    conn = _connection()
    try:
        row = conn.execute("SELECT status FROM service_cases WHERE id = ?", (case_id,)).fetchone()
        if row is None:
            raise KeyError(f"service case {case_id} not found")
        old = row["status"]
        if old != status:
            conn.execute("UPDATE service_cases SET status = ?, updated_at = ? WHERE id = ?", (status, now, case_id))
            conn.execute(
                "INSERT INTO service_case_events (case_id, event_type, old_value, new_value, note, created_at) VALUES (?, 'status', ?, ?, ?, ?)",
                (case_id, old, status, note.strip(), now),
            )
        elif note.strip():
            conn.execute(
                "INSERT INTO service_case_events (case_id, event_type, note, created_at) VALUES (?, 'note', ?, ?)",
                (case_id, note.strip(), now),
            )
        conn.commit()
        return get_case(case_id)
    finally:
        conn.close()


def add_note(case_id: int, note: str) -> None:
    if not note.strip():
        raise ValueError("note is required")
    init_service_cases()
    now = datetime.now().isoformat(timespec="seconds")
    conn = _connection()
    try:
        if conn.execute("SELECT 1 FROM service_cases WHERE id = ?", (case_id,)).fetchone() is None:
            raise KeyError(f"service case {case_id} not found")
        conn.execute("UPDATE service_cases SET updated_at = ? WHERE id = ?", (now, case_id))
        conn.execute(
            "INSERT INTO service_case_events (case_id, event_type, note, created_at) VALUES (?, 'note', ?, ?)",
            (case_id, note.strip(), now),
        )
        conn.commit()
    finally:
        conn.close()


def get_timeline(case_id: int) -> list[dict[str, object]]:
    init_service_cases()
    conn = _connection()
    try:
        rows = conn.execute(
            "SELECT id, event_type, old_value, new_value, note, created_at FROM service_case_events WHERE case_id = ? ORDER BY created_at ASC, id ASC",
            (case_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def update_payment(case_id: int, payment_status: str, paid_amount: float, note: str = "") -> ServiceCase:
    if payment_status not in PAYMENT_STATUSES:
        raise ValueError(f"invalid payment_status: {payment_status}")
    if paid_amount < 0:
        raise ValueError("paid_amount cannot be negative")

    init_service_cases()
    now = datetime.now().isoformat(timespec="seconds")
    conn = _connection()
    try:
        row = conn.execute(
            "SELECT payment_status, paid_amount FROM service_cases WHERE id = ?", (case_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"service case {case_id} not found")

        conn.execute(
            "UPDATE service_cases SET payment_status = ?, paid_amount = ?, updated_at = ? WHERE id = ?",
            (payment_status, float(paid_amount), now, case_id),
        )
        conn.execute(
            """INSERT INTO service_case_events
            (case_id, event_type, old_value, new_value, note, created_at)
            VALUES (?, 'payment', ?, ?, ?, ?)""",
            (
                case_id,
                f"{row['payment_status']} (Rp{row['paid_amount']:,.0f})",
                f"{payment_status} (Rp{paid_amount:,.0f})",
                note.strip(),
                now,
            ),
        )
        conn.commit()
        return get_case(case_id)
    finally:
        conn.close()


def update_estimated_completion(case_id: int, estimated_completion: str) -> ServiceCase:
    init_service_cases()
    now = datetime.now().isoformat(timespec="seconds")
    conn = _connection()
    try:
        if conn.execute("SELECT 1 FROM service_cases WHERE id = ?", (case_id,)).fetchone() is None:
            raise KeyError(f"service case {case_id} not found")
        conn.execute(
            "UPDATE service_cases SET estimated_completion = ?, updated_at = ? WHERE id = ?",
            (estimated_completion.strip(), now, case_id),
        )
        conn.commit()
        return get_case(case_id)
    finally:
        conn.close()


def update_case_info(
    case_id: int,
    customer_name: str | None = None,
    customer_phone: str | None = None,
    complaint: str | None = None,
    imei: str | None = None,
) -> ServiceCase:
    """Perbaiki data dasar case yang salah ketik saat input awal (nama,
    no. HP, keluhan, IMEI) - sebelumnya cuma bisa update status/pembayaran/
    catatan tambahan, tidak ada cara membetulkan data awal yang salah."""
    init_service_cases()
    now = datetime.now().isoformat(timespec="seconds")
    conn = _connection()
    try:
        row = conn.execute(
            "SELECT customer_name, customer_phone, complaint, imei FROM service_cases WHERE id = ?",
            (case_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"service case {case_id} not found")

        new_name = customer_name.strip() if customer_name is not None else row["customer_name"]
        new_phone = customer_phone.strip() if customer_phone is not None else row["customer_phone"]
        new_complaint = complaint.strip() if complaint is not None else row["complaint"]
        new_imei = imei.strip() if imei is not None else row["imei"]

        if not new_name:
            raise ValueError("Nama customer tidak boleh kosong.")
        if not new_complaint:
            raise ValueError("Keluhan tidak boleh kosong.")

        changes = []
        if new_name != row["customer_name"]:
            changes.append(f"nama: '{row['customer_name']}' -> '{new_name}'")
        if new_phone != row["customer_phone"]:
            changes.append(f"HP: '{row['customer_phone']}' -> '{new_phone}'")
        if new_complaint != row["complaint"]:
            changes.append(f"keluhan: '{row['complaint']}' -> '{new_complaint}'")
        if new_imei != row["imei"]:
            changes.append(f"IMEI: '{row['imei']}' -> '{new_imei}'")

        conn.execute(
            """UPDATE service_cases
            SET customer_name = ?, customer_phone = ?, complaint = ?, imei = ?, updated_at = ?
            WHERE id = ?""",
            (new_name, new_phone, new_complaint, new_imei, now, case_id),
        )

        if changes:
            conn.execute(
                "INSERT INTO service_case_events (case_id, event_type, note, created_at) VALUES (?, 'edit', ?, ?)",
                (case_id, "; ".join(changes), now),
            )

        conn.commit()
        return get_case(case_id)
    finally:
        conn.close()


def add_photo(case_id: int, photo_path: str, caption: str = "") -> CasePhoto:
    init_service_cases()
    now = datetime.now().isoformat(timespec="seconds")
    conn = _connection()
    try:
        if conn.execute("SELECT 1 FROM service_cases WHERE id = ?", (case_id,)).fetchone() is None:
            raise KeyError(f"service case {case_id} not found")

        cur = conn.execute(
            "INSERT INTO service_case_photos (case_id, photo_path, caption, created_at) VALUES (?, ?, ?, ?)",
            (case_id, photo_path, caption.strip(), now),
        )
        conn.execute(
            "INSERT INTO service_case_events (case_id, event_type, note, created_at) VALUES (?, 'photo', ?, ?)",
            (case_id, caption.strip() or "Foto ditambahkan", now),
        )
        conn.commit()
        photo_id = cur.lastrowid
        row = conn.execute(
            "SELECT * FROM service_case_photos WHERE id = ?", (photo_id,)
        ).fetchone()
        return CasePhoto(**dict(row))
    finally:
        conn.close()


def get_photos(case_id: int) -> list[CasePhoto]:
    init_service_cases()
    conn = _connection()
    try:
        rows = conn.execute(
            "SELECT * FROM service_case_photos WHERE case_id = ? ORDER BY id ASC",
            (case_id,),
        ).fetchall()
        return [CasePhoto(**dict(row)) for row in rows]
    finally:
        conn.close()


def delete_photo(photo_id: int) -> None:
    conn = _connection()
    try:
        conn.execute("DELETE FROM service_case_photos WHERE id = ?", (photo_id,))
        conn.commit()
    finally:
        conn.close()


@dataclass(frozen=True)
class BusinessSummary:
    period_label: str
    total_cases: int
    completed_cases: int
    cancelled_cases: int
    total_revenue: float
    outstanding_balance: float
    avg_turnaround_hours: float | None
    status_breakdown: dict[str, int]
    technician_breakdown: dict[str, dict[str, float]]


def get_business_summary(start_date: str, end_date: str) -> BusinessSummary:
    """Ringkasan bisnis untuk rentang tanggal (format 'YYYY-MM-DD') -
    dipakai halaman Laporan supaya pemilik konter bisa lihat jumlah case,
    pendapatan, dan sisa tagihan tanpa harus hitung manual dari daftar
    case satu-satu."""
    init_service_cases()
    conn = _connection()
    try:
        rows = conn.execute(
            """SELECT status, technician, estimated_cost, paid_amount, created_at, updated_at
            FROM service_cases
            WHERE date(created_at) >= date(?) AND date(created_at) <= date(?)""",
            (start_date, end_date),
        ).fetchall()

        total_cases = len(rows)
        completed = sum(1 for r in rows if r["status"] == "Completed")
        cancelled = sum(1 for r in rows if r["status"] == "Cancelled")
        total_revenue = sum(r["paid_amount"] for r in rows)
        outstanding = sum(
            max(0.0, r["estimated_cost"] - r["paid_amount"])
            for r in rows if r["status"] not in ("Cancelled",)
        )

        breakdown: dict[str, int] = {status: 0 for status in STATUSES}
        for r in rows:
            breakdown[r["status"]] = breakdown.get(r["status"], 0) + 1

        # Breakdown per teknisi - berguna kalau konter sudah punya lebih
        # dari 1 teknisi, supaya kelihatan siapa yang paling banyak
        # menyelesaikan case dan kontribusi pendapatannya masing-masing.
        technician_breakdown: dict[str, dict[str, float]] = {}
        for r in rows:
            name = r["technician"].strip() if r["technician"] and r["technician"].strip() else "(Belum diisi)"
            entry = technician_breakdown.setdefault(
                name, {"total_cases": 0, "completed_cases": 0, "revenue": 0.0}
            )
            entry["total_cases"] += 1
            if r["status"] == "Completed":
                entry["completed_cases"] += 1
            entry["revenue"] += r["paid_amount"]

        turnaround_hours = []
        for r in rows:
            if r["status"] != "Completed":
                continue
            try:
                created = datetime.fromisoformat(r["created_at"][:19])
                updated = datetime.fromisoformat(r["updated_at"][:19])
                turnaround_hours.append((updated - created).total_seconds() / 3600)
            except ValueError:
                continue

        avg_turnaround = (
            sum(turnaround_hours) / len(turnaround_hours) if turnaround_hours else None
        )

        return BusinessSummary(
            period_label=f"{start_date} s/d {end_date}",
            total_cases=total_cases,
            completed_cases=completed,
            cancelled_cases=cancelled,
            total_revenue=total_revenue,
            outstanding_balance=outstanding,
            avg_turnaround_hours=avg_turnaround,
            status_breakdown=breakdown,
            technician_breakdown=technician_breakdown,
        )
    finally:
        conn.close()


def export_cases_csv(output_path, start_date: str = "", end_date: str = "") -> Path:
    """Export semua case (opsional difilter rentang tanggal) ke CSV untuk
    dibuka di Excel/Google Sheets - kebutuhan pembukuan/laporan pajak yang
    sebelumnya cuma bisa dilihat manual di aplikasi atau per-case PDF."""
    import csv as csv_module

    init_service_cases()
    conn = _connection()
    try:
        query = "SELECT * FROM service_cases"
        params: list[object] = []
        if start_date and end_date:
            query += " WHERE date(created_at) >= date(?) AND date(created_at) <= date(?)"
            params = [start_date, end_date]
        query += " ORDER BY created_at ASC"
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "case_number", "customer_name", "customer_phone", "device_serial", "imei",
        "manufacturer", "model", "complaint", "technician", "status",
        "estimated_cost", "payment_status", "paid_amount", "estimated_completion",
        "notes", "created_at", "updated_at",
    ]

    with output_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv_module.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row[k] for k in fieldnames})

    return output_path
