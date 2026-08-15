"""
Automation module -- macro & batch command runner untuk mempercepat kerja
teknisi yang berulang (mis: satu urutan langkah standar servis tipe HP
tertentu, dijalankan tinggal sekali klik -- bahkan ke banyak device sekaligus).

Standalone module, BELUM di-wire ke app.py (sengaja, biar tidak bentrok
dengan sesi lain yang sedang merombak app.py).
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable, Optional

from .adb import run_adb, reboot_device, ADBError
from . import packages, file_explorer


MACROS_DIR = Path(__file__).resolve().parent.parent / "data" / "macros"


class MacroError(RuntimeError):
    pass


@dataclass
class MacroStep:
    action: str                          # nama aksi, lihat ACTIONS di bawah
    params: dict = field(default_factory=dict)
    label: str = ""


@dataclass
class Macro:
    name: str
    description: str = ""
    steps: list[MacroStep] = field(default_factory=list)


def _do_wait(serial: str, seconds: float = 1, **_):
    time.sleep(float(seconds))
    return f"Menunggu {seconds} detik selesai"


# Registry aksi yang bisa dipanggil macro. Tiap fungsi menerima (serial, **params).
# Gampang ditambah: tinggal daftarkan fungsi baru di sini.
ACTIONS: dict[str, Callable] = {
    "adb_shell": lambda serial, cmd="", **_: run_adb("-s", serial, "shell", cmd, timeout=30),
    "reboot": lambda serial, mode="system", **_: reboot_device(serial, mode),
    "install_apk": lambda serial, apk_path="", **_: packages.install_apk(serial, apk_path),
    "uninstall_app": lambda serial, package="", **_: packages.uninstall_package(serial, package),
    "clear_app_data": lambda serial, package="", **_: packages.clear_app_data(serial, package),
    "force_stop_app": lambda serial, package="", **_: packages.force_stop(serial, package),
    "disable_app": lambda serial, package="", **_: packages.disable_app(serial, package),
    "push_file": lambda serial, local_path="", remote_path="", **_: file_explorer.push_file(serial, local_path, remote_path),
    "pull_file": lambda serial, remote_path="", local_path="", **_: file_explorer.pull_file(serial, remote_path, local_path),
    "delete_file": lambda serial, remote_path="", **_: file_explorer.delete_remote(serial, remote_path),
    "wait": _do_wait,
}


def run_macro(
    serial: str,
    macro: Macro,
    on_step: Optional[Callable[[int, MacroStep, str], None]] = None,
    stop_on_error: bool = True,
) -> list[str]:
    """
    Jalankan macro langkah demi langkah pada satu device.

    on_step(index, step, result_or_error) dipanggil tiap langkah selesai --
    cocok untuk update progress bar / log di UI nanti.
    """
    results: list[str] = []

    for i, step in enumerate(macro.steps):
        action_fn = ACTIONS.get(step.action)
        if action_fn is None:
            raise MacroError(f"Aksi tidak dikenal: '{step.action}'")

        try:
            result = action_fn(serial, **step.params)
            result_str = str(result)
            results.append(result_str)
            if on_step:
                on_step(i, step, result_str)
        except ADBError as exc:
            error_msg = f"GAGAL di step {i} ({step.action}): {exc}"
            results.append(error_msg)
            if on_step:
                on_step(i, step, error_msg)
            if stop_on_error:
                raise MacroError(error_msg) from exc

    return results


def run_macro_batch(serials: list[str], macro: Macro) -> dict[str, object]:
    """Jalankan macro yang sama ke banyak device sekaligus (sequential per device,
    lebih aman untuk ADB daripada paralel)."""
    results: dict[str, object] = {}

    for serial in serials:
        try:
            results[serial] = {"ok": True, "log": run_macro(serial, macro)}
        except MacroError as exc:
            results[serial] = {"ok": False, "error": str(exc)}

    return results


def save_macro(macro: Macro) -> Path:
    """Simpan macro ke file JSON supaya bisa dipakai lagi nanti."""
    MACROS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(c for c in macro.name if c.isalnum() or c in (" ", "_", "-")).strip()
    if not safe_name:
        raise MacroError("Nama macro tidak valid.")

    file_path = MACROS_DIR / f"{safe_name}.json"
    data = {
        "name": macro.name,
        "description": macro.description,
        "steps": [asdict(step) for step in macro.steps],
    }
    file_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return file_path


def load_macro(file_path: str) -> Macro:
    path = Path(file_path)
    if not path.exists():
        raise MacroError(f"File macro tidak ditemukan: {file_path}")

    data = json.loads(path.read_text(encoding="utf-8"))
    steps = [MacroStep(**s) for s in data.get("steps", [])]
    return Macro(name=data["name"], description=data.get("description", ""), steps=steps)


def list_saved_macros() -> list[str]:
    if not MACROS_DIR.exists():
        return []
    return sorted(str(p) for p in MACROS_DIR.glob("*.json"))
