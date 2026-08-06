import zipfile
from datetime import datetime
from pathlib import Path

from .adb import run_adb, ADBError

# Folder umum yang sering dibutuhkan saat servis (bukan full system backup,
# karena adb backup/restore native sudah deprecated di banyak versi Android).
DEFAULT_BACKUP_TARGETS = [
    "/sdcard/DCIM",
    "/sdcard/Download",
    "/sdcard/Pictures",
    "/sdcard/WhatsApp",
]


def backup_device(serial: str, output_dir: Path, targets: list[str] | None = None) -> Path:
    targets = targets or DEFAULT_BACKUP_TARGETS

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    staging_dir = output_dir / f"backup_{serial}_{timestamp}"
    staging_dir.mkdir(parents=True, exist_ok=True)

    errors = []

    for target in targets:
        folder_name = target.rstrip("/").split("/")[-1]
        local_target = staging_dir / folder_name

        try:
            run_adb("-s", serial, "pull", target, str(local_target), timeout=600)
        except ADBError as exc:
            errors.append(f"{target}: {exc}")

    zip_path = output_dir / f"backup_{serial}_{timestamp}.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in staging_dir.rglob("*"):
            if file_path.is_file():
                zf.write(file_path, file_path.relative_to(staging_dir))

    if errors:
        error_log = staging_dir / "backup_errors.txt"
        error_log.write_text("\n".join(errors), encoding="utf-8")

    return zip_path


def restore_device(serial: str, zip_path: Path, remote_base: str = "/sdcard") -> list[str]:
    import tempfile

    results = []

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmp_path)

        for item in tmp_path.iterdir():
            if item.is_dir():
                remote_target = f"{remote_base}/{item.name}"

                try:
                    run_adb("-s", serial, "push", str(item), remote_target, timeout=600)
                    results.append(f"OK: {item.name} -> {remote_target}")
                except ADBError as exc:
                    results.append(f"GAGAL: {item.name} - {exc}")

    return results
