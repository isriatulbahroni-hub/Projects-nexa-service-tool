"""Backup untuk database APLIKASI itu sendiri (service_cases, action_log,
spare_parts, dll di nexa_service.db + settings.json) - beda dari
'Backup Device' yang itu buat data di HP pelanggan (DCIM/WhatsApp/dll).

Kenapa ini penting: semua data bisnis (case servis, riwayat pembayaran,
stok sparepart, audit trail) tersimpan di SATU file SQLite di laptop
teknisi. Kalau laptopnya rusak/kena virus/HDD mati tanpa backup ini,
seluruh data bisnis hilang permanen - beda dari data HP pelanggan yang
memang cuma sementara "numpang" di tool ini.
"""
from __future__ import annotations

import shutil
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from .config import PROJECT_ROOT

APP_DB_PATH = PROJECT_ROOT / "data" / "nexa_service.db"
APP_SETTINGS_PATH = PROJECT_ROOT / "data" / "settings.json"
DEFAULT_BACKUP_DIR = PROJECT_ROOT / "data" / "app_backups"


def backup_app_database(backup_dir: Path = DEFAULT_BACKUP_DIR) -> Path | None:
    """Backup nexa_service.db + settings.json ke satu file ZIP dengan
    timestamp. Return None kalau belum ada database sama sekali untuk
    di-backup (mis. instalasi baru yang belum pernah dipakai)."""
    if not APP_DB_PATH.exists():
        return None

    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = backup_dir / f"nexa_app_backup_{timestamp}.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(APP_DB_PATH, APP_DB_PATH.name)
        if APP_SETTINGS_PATH.exists():
            zf.write(APP_SETTINGS_PATH, APP_SETTINGS_PATH.name)

    return zip_path


def get_last_backup_time(backup_dir: Path = DEFAULT_BACKUP_DIR) -> datetime | None:
    backup_dir = Path(backup_dir)
    if not backup_dir.exists():
        return None

    backups = sorted(backup_dir.glob("nexa_app_backup_*.zip"))
    if not backups:
        return None

    return datetime.fromtimestamp(backups[-1].stat().st_mtime)


def should_auto_backup(backup_dir: Path = DEFAULT_BACKUP_DIR, interval_hours: int = 24) -> bool:
    """True kalau belum pernah backup sama sekali, atau backup terakhir
    sudah lebih lama dari interval_hours - dipakai untuk auto-backup diam-
    diam saat aplikasi dibuka, tanpa nge-spam backup setiap kali app
    dibuka berkali-kali dalam sehari."""
    last = get_last_backup_time(backup_dir)
    if last is None:
        return True
    return datetime.now() - last > timedelta(hours=interval_hours)


def cleanup_old_app_backups(backup_dir: Path = DEFAULT_BACKUP_DIR, retention_days: int = 30) -> int:
    backup_dir = Path(backup_dir)
    if retention_days <= 0 or not backup_dir.exists():
        return 0

    cutoff = datetime.now() - timedelta(days=retention_days)
    removed = 0

    for item in backup_dir.glob("nexa_app_backup_*.zip"):
        try:
            mtime = datetime.fromtimestamp(item.stat().st_mtime)
        except OSError:
            continue
        if mtime < cutoff:
            try:
                item.unlink()
                removed += 1
            except OSError:
                continue

    return removed


def restore_app_database(zip_path: Path, target_data_dir: Path = None) -> list[str]:
    """Restore nexa_service.db + settings.json dari ZIP backup. Membuat
    backup SAFETY dari file yang ada saat ini dulu sebelum menimpa,
    supaya restore yang salah tidak menghancurkan data terkini tanpa
    jalan mundur."""
    target_data_dir = Path(target_data_dir) if target_data_dir else APP_DB_PATH.parent
    results = []

    # Safety net: backup kondisi SEBELUM restore, supaya tidak hilang
    # kalau ternyata restore-nya salah/tidak sesuai yang diinginkan.
    safety_backup = backup_app_database(target_data_dir / "pre_restore_safety")
    if safety_backup:
        results.append(f"Backup pengaman sebelum restore: {safety_backup}")

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()

        for member in names:
            member_path = (target_data_dir / member).resolve()
            if not str(member_path).startswith(str(target_data_dir.resolve())):
                raise ValueError(f"File ZIP mencurigakan (path traversal): {member}")

        if "nexa_service.db" in names:
            zf.extract("nexa_service.db", target_data_dir)
            results.append("Database (nexa_service.db) berhasil di-restore.")

        if "settings.json" in names:
            zf.extract("settings.json", target_data_dir)
            results.append("Settings (settings.json) berhasil di-restore.")

    return results
