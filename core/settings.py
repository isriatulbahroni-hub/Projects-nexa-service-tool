"""Small JSON-backed settings store for Nexa Service Tool."""

from __future__ import annotations

import json
from pathlib import Path
from threading import RLock
from typing import Any

from .config import PROJECT_ROOT

SETTINGS_PATH = PROJECT_ROOT / "data" / "settings.json"
DEFAULTS: dict[str, Any] = {
    "auto_refresh_ms": 1500,
    "log_level": "INFO",
    "confirm_dangerous_actions": True,
    "mask_sensitive_identifiers": True,
    # Nama teknisi aktif - dipakai sebagai default di semua entry audit
    # trail (action_log). Sebelumnya semua tercatat sebagai "Technician"
    # generik, jadi kalau ada lebih dari satu orang pakai tool ini, tidak
    # bisa dibedakan siapa yang melakukan tindakan apa.
    "active_technician": "",
    "known_technicians": [],
    # Retensi file backup lokal (hari). 0 = jangan hapus otomatis.
    "backup_retention_days": 30,
    # Path adb/fastboot manual, kalau auto-detect (PATH/ToolRouter) gagal.
    "adb_path_override": "",
    "fastboot_path_override": "",
}


# Singleton di level modul - supaya core/adb.py & core/firmware.py bisa
# baca adb_path_override/fastboot_path_override tiap kali resolve path
# TANPA harus buka+parse settings.json ulang setiap panggilan run_adb()
# (yang bisa dipanggil sangat sering).
settings_store: "SettingsStore" = None  # type: ignore[assignment]


def get_settings_store() -> "SettingsStore":
    global settings_store
    if settings_store is None:
        settings_store = SettingsStore()
    return settings_store


class SettingsStore:
    """Thread-safe settings store with defaults and atomic-ish replacement."""

    def __init__(self, path: Path = SETTINGS_PATH, defaults: dict[str, Any] | None = None):
        self.path = Path(path)
        self.defaults = dict(DEFAULTS if defaults is None else defaults)
        self._lock = RLock()
        self._values: dict[str, Any] = {}
        self.load()

    def load(self) -> dict[str, Any]:
        with self._lock:
            values = {}
            if self.path.exists():
                try:
                    values = json.loads(self.path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    values = {}
            self._values = {**self.defaults, **values}
            return dict(self._values)

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._values.get(key, default)

    def set(self, key: str, value: Any, *, persist: bool = True) -> None:
        with self._lock:
            self._values[key] = value
            if persist:
                self.save()

    def update(self, values: dict[str, Any], *, persist: bool = True) -> None:
        with self._lock:
            self._values.update(values)
            if persist:
                self.save()

    def save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(self._values, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            tmp.replace(self.path)
