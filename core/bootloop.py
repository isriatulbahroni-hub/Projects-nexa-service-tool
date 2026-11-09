"""Panduan bootloop/recovery berurutan, berdasarkan mode perangkat saat ini.

Aturan penting: langkah yang bisa menghapus data TERKUNCI sampai semua
langkah aman sebelumnya selesai atau sengaja di-skip. Data langkah ada di
core/repair_data.py (dibagi dengan versi web).
"""
from __future__ import annotations

from .repair_data import BOOTLOOP_STEPS, MODES


def detect_mode(adb_state: str, fastboot_serials: list[str], serial: str, fastboot_vars: dict[str, str] | None = None) -> str:
    """Petakan state ADB/Fastboot -> salah satu MODES."""
    if serial in fastboot_serials:
        return "fastbootd" if (fastboot_vars or {}).get("is-userspace", "").lower() == "yes" else "fastboot"
    return {
        "device": "android",
        "recovery": "recovery",
        "sideload": "sideload",
        "unauthorized": "unauthorized",
        "offline": "offline",
    }.get((adb_state or "").lower(), "none")


def next_steps(mode: str, done: set[str] | None = None, skipped: set[str] | None = None) -> list[dict]:
    """Daftar langkah beserta state: done | skipped | ready | locked | wrong_mode."""
    if mode not in MODES:
        mode = "none"
    done, skipped = set(done or ()), set(skipped or ())
    out: list[dict] = []
    safe_pending = False  # ada langkah aman (applicable) yang belum selesai/skip?
    for step in BOOTLOOP_STEPS:
        entry = dict(step)
        if step["id"] in done:
            entry["state"] = "done"
        elif step["id"] in skipped:
            entry["state"] = "skipped"
        elif mode not in step["modes"]:
            entry["state"] = "wrong_mode"
        elif step["data_loss"] != "none" and safe_pending:
            entry["state"] = "locked"
        else:
            entry["state"] = "ready"
            if step["data_loss"] == "none" and step["id"] != "hardware_suspect":
                safe_pending = True
        out.append(entry)
    return out
