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


def _connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


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
            CREATE INDEX IF NOT EXISTS idx_service_cases_status ON service_cases(status);
            CREATE INDEX IF NOT EXISTS idx_service_cases_serial ON service_cases(device_serial);
            CREATE INDEX IF NOT EXISTS idx_service_case_events_case ON service_case_events(case_id);
            """
        )
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
             manufacturer, model, technician, status, estimated_cost, notes,
             created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Received', ?, ?, ?, ?)""",
            (case_number, customer_name.strip(), customer_phone.strip(),
             device_serial.strip(), imei.strip(), manufacturer.strip(),
             model.strip(), technician.strip(), float(estimated_cost),
             notes.strip(), now, now),
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
            clauses.append("(case_number LIKE ? OR customer_name LIKE ? OR device_serial LIKE ? OR imei LIKE ? OR model LIKE ?)")
            params.extend([like] * 5)
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
