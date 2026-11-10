import os
import sys
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parent.parent

_EXE = ".exe" if os.name == "nt" else ""
ADB_PATH = Path.home() / "platform-tools" / "platform-tools" / f"adb{_EXE}"
FASTBOOT_PATH = Path.home() / "platform-tools" / "platform-tools" / f"fastboot{_EXE}"


def _app_data_root() -> Path:
    """Folder induk untuk semua data pengguna (database, pengaturan, lisensi, log).

    Saat jalan dari source: folder proyek (perilaku lama, tidak berubah).
    Saat dibungkus PyInstaller (--onefile): folder program adalah direktori
    temp yang DIHAPUS setiap aplikasi ditutup, jadi semua data harus pindah
    ke folder data pengguna yang permanen. Tanpa ini database kasus servis,
    pengaturan, dan lisensi hilang setiap restart.
    """
    if getattr(sys, "frozen", False):
        base = (
            os.environ.get("LOCALAPPDATA")
            or os.environ.get("XDG_DATA_HOME")
            or str(Path.home() / ".local" / "share")
        )
        return Path(base) / "NexaServiceTool"
    return SOURCE_ROOT


APP_DATA_ROOT = _app_data_root()
DATA_DIR = APP_DATA_ROOT / "data"

# Nama lama, dipertahankan karena app.py masih memakai PROJECT_ROOT / "data" / "case_photos".
# Semua pemakainya hanya untuk folder data, jadi nilainya mengikuti APP_DATA_ROOT
# (folder proyek saat dari source, folder data pengguna saat build .exe).
PROJECT_ROOT = APP_DATA_ROOT
