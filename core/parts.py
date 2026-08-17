"""Manajemen stok sparepart untuk service center - tracking part masuk/
keluar dan pemakaian part per case servis.

Kenapa ini penting: konter servis HP biasanya jual/pasang sparepart
(LCD, baterai, konektor casing, dll) sebagai bagian dari servis, tapi
sebelumnya tidak ada cara melacak stok atau tahu part mana yang habis/
menipis, apalagi menghubungkan part yang dipakai ke case tertentu.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .config import PROJECT_ROOT

DB_PATH = PROJECT_ROOT / "data" / "nexa_service.db"


@dataclass(frozen=True)
class SparePart:
    id: int
    name: str
    category: str
    stock_qty: int
    min_stock: int
    unit_price: float
    notes: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class PartUsage:
    id: int
    part_id: int
    part_name: str
    case_id: int | None
    quantity: int
    note: str
    created_at: str


def _connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_parts() -> None:
    conn = _connection()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS spare_parts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT DEFAULT '',
                stock_qty INTEGER NOT NULL DEFAULT 0,
                min_stock INTEGER NOT NULL DEFAULT 0,
                unit_price REAL NOT NULL DEFAULT 0,
                notes TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS spare_part_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                part_id INTEGER NOT NULL,
                case_id INTEGER,
                quantity INTEGER NOT NULL,
                note TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY(part_id) REFERENCES spare_parts(id)
            );
            CREATE INDEX IF NOT EXISTS idx_spare_parts_name ON spare_parts(name);
            CREATE INDEX IF NOT EXISTS idx_part_usage_case ON spare_part_usage(case_id);
            """
        )
        conn.commit()
    finally:
        conn.close()


def _part(row: sqlite3.Row) -> SparePart:
    return SparePart(**{k: row[k] for k in row.keys()})


def add_part(
    name: str, category: str = "", stock_qty: int = 0, min_stock: int = 0,
    unit_price: float = 0, notes: str = "",
) -> SparePart:
    if not name.strip():
        raise ValueError("Nama part wajib diisi.")
    if stock_qty < 0 or min_stock < 0 or unit_price < 0:
        raise ValueError("Jumlah stok/harga tidak boleh negatif.")

    init_parts()
    now = datetime.now().isoformat(timespec="seconds")
    conn = _connection()
    try:
        cur = conn.execute(
            """INSERT INTO spare_parts
            (name, category, stock_qty, min_stock, unit_price, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (name.strip(), category.strip(), stock_qty, min_stock, unit_price, notes.strip(), now, now),
        )
        conn.commit()
        return get_part(cur.lastrowid)
    finally:
        conn.close()


def get_part(part_id: int) -> SparePart:
    conn = _connection()
    try:
        row = conn.execute("SELECT * FROM spare_parts WHERE id = ?", (part_id,)).fetchone()
        if row is None:
            raise KeyError(f"Part {part_id} tidak ditemukan.")
        return _part(row)
    finally:
        conn.close()


def list_parts(search: str = "", low_stock_only: bool = False) -> list[SparePart]:
    init_parts()
    conn = _connection()
    try:
        query = "SELECT * FROM spare_parts"
        clauses = []
        params: list[object] = []

        if search.strip():
            clauses.append("(name LIKE ? OR category LIKE ?)")
            like = f"%{search.strip()}%"
            params.extend([like, like])

        if low_stock_only:
            clauses.append("stock_qty <= min_stock")

        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY name ASC"

        rows = conn.execute(query, params).fetchall()
        return [_part(row) for row in rows]
    finally:
        conn.close()


def update_stock(part_id: int, new_qty: int) -> SparePart:
    if new_qty < 0:
        raise ValueError("Stok tidak boleh negatif.")

    now = datetime.now().isoformat(timespec="seconds")
    conn = _connection()
    try:
        if conn.execute("SELECT 1 FROM spare_parts WHERE id = ?", (part_id,)).fetchone() is None:
            raise KeyError(f"Part {part_id} tidak ditemukan.")
        conn.execute(
            "UPDATE spare_parts SET stock_qty = ?, updated_at = ? WHERE id = ?",
            (new_qty, now, part_id),
        )
        conn.commit()
        return get_part(part_id)
    finally:
        conn.close()


def use_part(part_id: int, quantity: int, case_id: int | None = None, note: str = "") -> SparePart:
    """Catat pemakaian part (mis. dipasang ke case servis tertentu) dan
    otomatis kurangi stok. Menolak kalau stok tidak cukup - supaya stok
    tidak bisa jadi negatif secara tidak sengaja."""
    if quantity <= 0:
        raise ValueError("Jumlah pemakaian harus lebih dari 0.")

    now = datetime.now().isoformat(timespec="seconds")
    conn = _connection()
    try:
        row = conn.execute("SELECT stock_qty FROM spare_parts WHERE id = ?", (part_id,)).fetchone()
        if row is None:
            raise KeyError(f"Part {part_id} tidak ditemukan.")
        if row["stock_qty"] < quantity:
            raise ValueError(
                f"Stok tidak cukup (tersedia {row['stock_qty']}, diminta {quantity})."
            )

        conn.execute(
            "UPDATE spare_parts SET stock_qty = stock_qty - ?, updated_at = ? WHERE id = ?",
            (quantity, now, part_id),
        )
        conn.execute(
            "INSERT INTO spare_part_usage (part_id, case_id, quantity, note, created_at) VALUES (?, ?, ?, ?, ?)",
            (part_id, case_id, quantity, note.strip(), now),
        )
        conn.commit()
        return get_part(part_id)
    finally:
        conn.close()


def get_usage_for_case(case_id: int) -> list[PartUsage]:
    init_parts()
    conn = _connection()
    try:
        rows = conn.execute(
            """SELECT u.id, u.part_id, p.name AS part_name, u.case_id, u.quantity, u.note, u.created_at
            FROM spare_part_usage u
            JOIN spare_parts p ON p.id = u.part_id
            WHERE u.case_id = ?
            ORDER BY u.id ASC""",
            (case_id,),
        ).fetchall()
        return [PartUsage(**{k: row[k] for k in row.keys()}) for row in rows]
    finally:
        conn.close()


def get_total_usage_cost(start_date: str, end_date: str) -> float:
    """Total biaya sparepart yang dipakai dalam rentang tanggal tertentu
    (qty x harga satuan SAAT INI part terkait) - dipakai Laporan Bisnis
    untuk hitung profit bersih (pendapatan dikurangi biaya part).
    Catatan: karena harga part bisa berubah dari waktu ke waktu dan
    pemakaian tidak menyimpan harga historis saat dipakai, ini pakai
    harga SAAT INI sebagai pendekatan - cukup akurat untuk part yang
    harganya relatif stabil, tapi bisa sedikit meleset untuk part yang
    baru saja naik/turun harga signifikan."""
    init_parts()
    conn = _connection()
    try:
        row = conn.execute(
            """SELECT COALESCE(SUM(u.quantity * p.unit_price), 0) AS total_cost
            FROM spare_part_usage u
            JOIN spare_parts p ON p.id = u.part_id
            WHERE date(u.created_at) >= date(?) AND date(u.created_at) <= date(?)""",
            (start_date, end_date),
        ).fetchone()
        return float(row["total_cost"])
    finally:
        conn.close()


def delete_part(part_id: int) -> None:
    conn = _connection()
    try:
        conn.execute("DELETE FROM spare_parts WHERE id = ?", (part_id,))
        conn.commit()
    finally:
        conn.close()
