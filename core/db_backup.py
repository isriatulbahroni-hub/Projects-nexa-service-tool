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

import os
import shutil
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

from .config import PROJECT_ROOT

try:
    import pyzipper
except ImportError:  # pragma: no cover - dependensi opsional
    pyzipper = None

APP_DB_PATH = PROJECT_ROOT / "data" / "nexa_service.db"
APP_SETTINGS_PATH = PROJECT_ROOT / "data" / "settings.json"
DEFAULT_BACKUP_DIR = PROJECT_ROOT / "data" / "app_backups"


# File kecil lain di folder data yang ikut di-backup (akun teknisi & lisensi).
# Dicari relatif terhadap folder database, jadi ikut berpindah saat data dir berubah.
EXTRA_DATA_FILES = ("technicians.json", "license.json")
PHOTOS_DIRNAME = "case_photos"
SAFETY_DIRNAME = "pre_restore_safety"
SAFETY_KEEP = 5


class AppBackupError(RuntimeError):
    pass


def _snapshot_database(src: Path, dst: Path) -> None:
    """Salin database yang konsisten walau sedang dipakai (API backup SQLite).
    Kalau file bukan SQLite valid, jatuh ke salin file biasa."""
    try:
        with closing(sqlite3.connect(f"{src.resolve().as_uri()}?mode=ro", uri=True)) as source, \
                closing(sqlite3.connect(str(dst))) as target:
            source.backup(target)
    except sqlite3.Error:
        shutil.copy2(src, dst)


def backup_app_database(
    backup_dir: Path = DEFAULT_BACKUP_DIR,
    password: str | None = None,
    include_photos: bool = False,
) -> Path | None:
    """Backup nexa_service.db + settings.json (+ technicians.json, license.json
    bila ada) ke satu file ZIP dengan timestamp. Database di-snapshot lewat API
    backup SQLite supaya konsisten walau sedang dipakai.

    - `password`: ZIP dienkripsi AES-256 (butuh pyzipper). Isinya data pelanggan.
    - `include_photos`: ikutkan folder case_photos (bisa besar, karena itu opsional).

    Return None kalau belum ada database untuk di-backup."""
    if not APP_DB_PATH.exists():
        return None
    if password and pyzipper is None:
        raise AppBackupError("Password diisi tapi pyzipper belum terpasang. Jalankan: pip install pyzipper")

    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = backup_dir / f"nexa_app_backup_{timestamp}.zip"
    data_dir = APP_DB_PATH.parent

    with tempfile.TemporaryDirectory() as tmp:
        snapshot = Path(tmp) / APP_DB_PATH.name
        _snapshot_database(APP_DB_PATH, snapshot)

        def _write_all(zf) -> None:
            zf.write(snapshot, APP_DB_PATH.name)
            if APP_SETTINGS_PATH.exists():
                zf.write(APP_SETTINGS_PATH, APP_SETTINGS_PATH.name)
            for name in EXTRA_DATA_FILES:
                extra = data_dir / name
                if extra.is_file():
                    zf.write(extra, name)
            photos = data_dir / PHOTOS_DIRNAME
            if include_photos and photos.is_dir():
                for file_path in photos.rglob("*"):
                    if file_path.is_file():
                        zf.write(file_path, Path(PHOTOS_DIRNAME) / file_path.relative_to(photos))

        if password:
            with pyzipper.AESZipFile(
                zip_path, "w", compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES
            ) as zf:
                zf.setpassword(password.encode("utf-8"))
                _write_all(zf)
        else:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                _write_all(zf)

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


def is_app_backup_encrypted(zip_path: Path) -> bool:
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            return any(info.flag_bits & 0x1 for info in zf.infolist())
    except zipfile.BadZipFile:
        return False


def _prune_safety_backups(safety_dir: Path, keep: int = SAFETY_KEEP) -> None:
    """Simpan hanya `keep` backup pengaman terbaru supaya folder tidak menumpuk."""
    try:
        files = sorted(Path(safety_dir).glob("nexa_app_backup_*.zip"), key=lambda p: p.stat().st_mtime)
    except OSError:
        return
    for old in files[:-keep] if keep > 0 else files:
        try:
            old.unlink()
        except OSError:
            continue


def restore_app_database(zip_path: Path, target_data_dir: Path = None, password: str | None = None) -> list[str]:
    """Restore nexa_service.db + settings.json (+ technicians.json, license.json,
    case_photos bila ada di ZIP). Membuat backup SAFETY dari kondisi saat ini
    dulu sebelum menimpa, supaya restore yang salah punya jalan mundur."""
    zip_path = Path(zip_path)
    target_data_dir = Path(target_data_dir) if target_data_dir else APP_DB_PATH.parent
    results = []

    encrypted = is_app_backup_encrypted(zip_path)
    if encrypted and not password:
        raise AppBackupError("Backup ini diproteksi password. Masukkan password untuk restore.")
    if encrypted and pyzipper is None:
        raise AppBackupError("Backup terenkripsi tapi pyzipper belum terpasang. Jalankan: pip install pyzipper")

    # Validasi isi ZIP SEBELUM menyentuh data yang ada.
    opener = pyzipper.AESZipFile if encrypted else zipfile.ZipFile
    root = target_data_dir.resolve()
    with opener(zip_path, "r") as zf:
        if encrypted:
            zf.setpassword(password.encode("utf-8"))
        names = zf.namelist()

        for member in names:
            member_path = (target_data_dir / member).resolve()
            if member_path != root and not member_path.is_relative_to(root):
                raise ValueError(f"File ZIP mencurigakan (path traversal): {member}")

        # Safety net: backup kondisi SEBELUM restore.
        safety_dir = target_data_dir / SAFETY_DIRNAME
        safety_backup = backup_app_database(safety_dir)
        if safety_backup:
            results.append(f"Backup pengaman sebelum restore: {safety_backup}")
            _prune_safety_backups(safety_dir)

        target_data_dir.mkdir(parents=True, exist_ok=True)
        for fixed in ("nexa_service.db", "settings.json", *EXTRA_DATA_FILES):
            if fixed not in names:
                continue
            tmp_target = target_data_dir / (fixed + ".restoring")
            tmp_target.write_bytes(zf.read(fixed))
            os.replace(tmp_target, target_data_dir / fixed)
            results.append(f"{fixed} berhasil di-restore.")

        photo_members = [n for n in names if n.startswith(PHOTOS_DIRNAME + "/") and not n.endswith("/")]
        for member in photo_members:
            dest = target_data_dir / member
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zf.read(member))
        if photo_members:
            results.append(f"{len(photo_members)} foto kasus di-restore.")

    return results
