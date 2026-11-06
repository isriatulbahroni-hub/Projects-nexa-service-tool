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
        # Audit trail untuk tindakan berisiko (backup, restore, uninstall,
        # install, flash partition, verifikasi FRP, reboot recovery/
        # bootloader, dll). Sebelumnya TIDAK ADA pencatatan sama sekali
        # untuk aksi-aksi ini - kalau ada sengketa dengan pelanggan
        # ("data saya kok hilang?", "kenapa HP saya di-flash?"), tidak ada
        # bukti tercatat siapa melakukan apa dan kapan.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS action_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                serial TEXT,
                action TEXT NOT NULL,
                detail TEXT,
                status TEXT NOT NULL,
                technician TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_action_log_serial ON action_log(serial)"
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
    # Urut berdasarkan id (bukan created_at) - created_at cuma presisi
    # sampai detik (timespec="seconds"), jadi dua record yang tersimpan
    # dalam detik yang sama bisa salah urutan kalau di-sort dari teksnya.
    # id AUTOINCREMENT selalu bertambah sesuai urutan insert, jadi lebih
    # bisa diandalkan untuk urutan kronologis yang benar.
    init_db()
    conn = get_connection()

    try:
        if serial:
            rows = conn.execute(
                """
                SELECT * FROM service_history
                WHERE serial = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (serial, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM service_history
                ORDER BY id DESC
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


@dataclass
class ActionLogEntry:
    id: int
    serial: str
    action: str
    detail: str
    status: str
    technician: str
    created_at: str


def log_action(
    action: str,
    detail: str = "",
    status: str = "OK",
    serial: str | None = None,
    technician: str = "Technician",
) -> int:
    """Catat satu tindakan ke audit trail. Dipanggil setelah aksi berisiko
    selesai (backup, restore, uninstall, install, flash, verifikasi FRP,
    reboot recovery/bootloader, dll) - baik sukses maupun gagal, supaya ada
    jejak lengkap untuk akuntabilitas ke pelanggan."""
    init_db()
    conn = get_connection()

    try:
        cursor = conn.execute(
            """
            INSERT INTO action_log (serial, action, detail, status, technician, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                serial or "",
                action,
                detail,
                status,
                technician,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_action_log(serial: str | None = None, limit: int = 200) -> list[ActionLogEntry]:
    # Sama seperti get_history() - urut by id, bukan created_at (lihat
    # penjelasan di get_history()).
    init_db()
    conn = get_connection()

    try:
        if serial:
            rows = conn.execute(
                """
                SELECT * FROM action_log
                WHERE serial = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (serial, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM action_log
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [ActionLogEntry(**dict(row)) for row in rows]
    finally:
        conn.close()
