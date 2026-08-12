import zipfile
from datetime import datetime
from pathlib import Path
from typing import Callable

from .adb import run_adb, ADBError, is_device_connected

# Folder umum yang sering dibutuhkan saat servis (bukan full system backup,
# karena adb backup/restore native sudah deprecated di banyak versi Android).
DEFAULT_BACKUP_TARGETS = [
    "/sdcard/DCIM",
    "/sdcard/Download",
    "/sdcard/Pictures",
    "/sdcard/WhatsApp",
]


def backup_device(
    serial: str,
    output_dir: Path,
    targets: list[str] | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> Path:
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


def restore_device(
    serial: str,
    zip_path: Path,
    remote_base: str = "/sdcard",
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> list[str]:
    import tempfile

    results = []

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        with zipfile.ZipFile(zip_path, "r") as zf:
            # Guard "zip slip": tolak entry yang mencoba keluar dari
            # tmp_path (mis. "../../something") sebelum ekstrak apapun.
            for member in zf.namelist():
                member_path = (tmp_path / member).resolve()
                if not str(member_path).startswith(str(tmp_path.resolve())):
                    raise ValueError(f"File ZIP mencurigakan (path traversal): {member}")
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
