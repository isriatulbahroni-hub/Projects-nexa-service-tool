import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .config import PROJECT_ROOT

DB_PATH = PROJECT_ROOT / "data" / "nexa_service.db"


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS service_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                serial TEXT NOT NULL,
                manufacturer TEXT,
                model TEXT,
                android_version TEXT,
                battery_level TEXT,
                battery_status TEXT,
                battery_health TEXT,
                storage TEXT,
                screen_state TEXT,
                usb_debugging TEXT,
                health_score INTEGER,
                recommendations TEXT,
                note TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


@dataclass
class ServiceRecord:
    id: int
    serial: str
    manufacturer: str
    model: str
    android_version: str
    battery_level: str
    battery_status: str
    battery_health: str
    storage: str
    screen_state: str
    usb_debugging: str
    health_score: int
    recommendations: str
    note: str
    created_at: str


def save_service_record(
    serial: str,
    manufacturer: str,
    model: str,
    android_version: str,
    diag,
    health_score: int,
    recommendations: list[str],
    note: str = "",
) -> int:
    init_db()
    conn = get_connection()

    try:
        cursor = conn.execute(
            """
            INSERT INTO service_history (
                serial, manufacturer, model, android_version,
                battery_level, battery_status, battery_health,
                storage, screen_state, usb_debugging,
                health_score, recommendations, note, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                serial,
                manufacturer,
                model,
                android_version,
                diag.battery_level,
                diag.battery_status,
                diag.battery_health,
                diag.storage,
                diag.screen_state,
                diag.usb_debugging,
                health_score,
                " | ".join(recommendations),
                note,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_history(serial: str | None = None, limit: int = 100) -> list[ServiceRecord]:
    init_db()
    conn = get_connection()

    try:
        if serial:
            rows = conn.execute(
                """
                SELECT * FROM service_history
                WHERE serial = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (serial, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM service_history
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [ServiceRecord(**dict(row)) for row in rows]
    finally:
        conn.close()


def delete_record(record_id: int) -> None:
    conn = get_connection()

    try:
        conn.execute("DELETE FROM service_history WHERE id = ?", (record_id,))
        conn.commit()
    finally:
        conn.close()
