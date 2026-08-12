import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from .adb import run_adb, ADBError, is_device_connected

try:
    import pyzipper
except ImportError:  # pragma: no cover - optional dependency
    pyzipper = None

# Folder umum yang sering dibutuhkan saat servis (bukan full system backup,
# karena adb backup/restore native sudah deprecated di banyak versi Android).
DEFAULT_BACKUP_TARGETS = [
    "/sdcard/DCIM",
    "/sdcard/Download",
    "/sdcard/Pictures",
    "/sdcard/WhatsApp",
]


class BackupError(RuntimeError):
    pass


def backup_device(
    serial: str,
    output_dir: Path,
    targets: list[str] | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
    password: str | None = None,
) -> Path:
    """Backup folder penting device ke ZIP. Kalau `password` diisi, ZIP-nya
    dienkripsi AES-256 (pakai pyzipper) - PENTING karena isi backup (foto,
    chat WhatsApp) adalah data pribadi pelanggan yang sensitif, dan
    sebelumnya selalu tersimpan sebagai ZIP polos tanpa proteksi apapun di
    komputer teknisi."""
    if password and pyzipper is None:
        raise BackupError(
            "Password diisi tapi pyzipper belum terpasang. "
            "Jalankan: pip install pyzipper"
        )

    targets = targets or DEFAULT_BACKUP_TARGETS

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    staging_dir = output_dir / f"backup_{serial}_{timestamp}"
    staging_dir.mkdir(parents=True, exist_ok=True)

    errors = []
    total = len(targets)
    device_lost = False

    for i, target in enumerate(targets, start=1):
        folder_name = target.rstrip("/").split("/")[-1]
        local_target = staging_dir / folder_name

        if progress_callback:
            progress_callback(i, total, target)

        if device_lost:
            errors.append(f"{target}: dilewati - device terputus.")
            continue

        try:
            run_adb("-s", serial, "pull", target, str(local_target), timeout=600)
        except ADBError as exc:
            errors.append(f"{target}: {exc}")

            # Kalau device benar-benar sudah terputus (bukan cuma folder
            # target-nya yang tidak ada), tidak ada gunanya coba target
            # sisanya satu-satu - masing-masing bakal timeout sendiri dan
            # bikin proses backup jauh lebih lama dari yang seharusnya.
            if not is_device_connected(serial):
                device_lost = True

    zip_path = output_dir / f"backup_{serial}_{timestamp}.zip"

    if password:
        with pyzipper.AESZipFile(
            zip_path, "w", compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES
        ) as zf:
            zf.setpassword(password.encode("utf-8"))
            for file_path in staging_dir.rglob("*"):
                if file_path.is_file():
                    zf.write(file_path, file_path.relative_to(staging_dir))
    else:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in staging_dir.rglob("*"):
                if file_path.is_file():
                    zf.write(file_path, file_path.relative_to(staging_dir))

    if device_lost:
        errors.append(
            "PERINGATAN: device terputus sebelum semua folder selesai di-backup. "
            "Hasil backup ini KEMUNGKINAN TIDAK LENGKAP."
        )

    if errors:
        error_log = staging_dir / "backup_errors.txt"
        error_log.write_text("\n".join(errors), encoding="utf-8")

    return zip_path


def is_zip_password_protected(zip_path: Path) -> bool:
    """Cek cepat apakah ZIP diproteksi password, tanpa perlu password itu
    sendiri - dipakai UI untuk tahu kapan perlu menampilkan prompt
    password sebelum restore. Flag bit 0x1 di setiap ZipInfo tetap
    terbaca oleh zipfile standar walau isi entry-nya dienkripsi AES."""
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            return any(info.flag_bits & 0x1 for info in zf.infolist())
    except zipfile.BadZipFile:
        return False


def restore_device(
    serial: str,
    zip_path: Path,
    remote_base: str = "/sdcard",
    progress_callback: Callable[[int, int, str], None] | None = None,
    password: str | None = None,
) -> list[str]:
    import tempfile

    if password and pyzipper is None:
        raise BackupError(
            "Password diisi tapi pyzipper belum terpasang. "
            "Jalankan: pip install pyzipper"
        )

    results = []

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        if password:
            with pyzipper.AESZipFile(zip_path, "r") as zf:
                zf.setpassword(password.encode("utf-8"))
                _validate_zip_members(zf.namelist(), tmp_path)
                zf.extractall(tmp_path)
        else:
            with zipfile.ZipFile(zip_path, "r") as zf:
                _validate_zip_members(zf.namelist(), tmp_path)
                zf.extractall(tmp_path)

        items = [item for item in tmp_path.iterdir() if item.is_dir()]
        total = len(items)
        device_lost = False

        for i, item in enumerate(items, start=1):
            remote_target = f"{remote_base}/{item.name}"

            if progress_callback:
                progress_callback(i, total, item.name)

            if device_lost:
                results.append(f"DILEWATI: {item.name} - device terputus.")
                continue

            try:
                run_adb("-s", serial, "push", str(item), remote_target, timeout=600)
                results.append(f"OK: {item.name} -> {remote_target}")
            except ADBError as exc:
                results.append(f"GAGAL: {item.name} - {exc}")

                if not is_device_connected(serial):
                    device_lost = True

        if device_lost:
            results.append(
                "PERINGATAN: device terputus sebelum semua folder selesai di-restore."
            )

    return results


def _validate_zip_members(namelist: list[str], extract_root: Path) -> None:
    """Guard 'zip slip' (path traversal) - tolak entry yang mencoba keluar
    dari folder tujuan ekstrak sebelum ekstrak apapun."""
    root = str(extract_root.resolve())
    for member in namelist:
        member_path = (extract_root / member).resolve()
        if not str(member_path).startswith(root):
            raise ValueError(f"File ZIP mencurigakan (path traversal): {member}")


def cleanup_old_backups(directory: Path, retention_days: int) -> int:
    """Hapus file backup_*.zip (dan folder staging yang tertinggal) di
    `directory` yang lebih tua dari `retention_days` hari. Sebelumnya
    backup menumpuk selamanya di disk teknisi tanpa retensi sama sekali.
    Mengembalikan jumlah item yang dihapus."""
    directory = Path(directory)

    if retention_days <= 0 or not directory.exists():
        return 0

    cutoff = datetime.now() - timedelta(days=retention_days)
    removed = 0

    for item in directory.glob("backup_*"):
        try:
            mtime = datetime.fromtimestamp(item.stat().st_mtime)
        except OSError:
            continue

        if mtime >= cutoff:
            continue

        try:
            if item.is_file():
                item.unlink()
                removed += 1
            elif item.is_dir():
                import shutil
                shutil.rmtree(item)
                removed += 1
        except OSError:
            continue

    return removed
