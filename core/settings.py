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
}


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
