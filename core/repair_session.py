"""Logika sesi perbaikan yang dipakai GUI: deteksi mode, reboot, persiapan flash, format hasil.

Semua fungsi menerima pembaca/penulis yang bisa diganti supaya bisa dites tanpa HP.
"""
from __future__ import annotations

from pathlib import Path

from . import bootloop
from .adb import ADBError, get_devices_with_state, reboot_device
from .firmware import (
    FastbootError,
    get_fastboot_vars,
    list_fastboot_devices,
    reboot_from_fastboot,
    reboot_to_bootloader_from_fastboot,
    reboot_to_fastbootd,
    run_fastboot,
)
from .flash_safety import FlashItem, sha256_file, validate_queue

REBOOT_TARGETS = {
    "system": "Sistem",
    "recovery": "Recovery",
    "bootloader": "Bootloader",
    "fastboot": "fastbootd",
    "sideload": "Sideload",
}


def resolve_serial(preferred: str | None, fastboot_serials: list[str]) -> str | None:
    if preferred:
        return preferred
    if len(fastboot_serials) == 1:
        return fastboot_serials[0]
    return None


def detect_current_mode(
    serial: str | None,
    *,
    state_reader=get_devices_with_state,
    fastboot_lister=list_fastboot_devices,
    vars_reader=get_fastboot_vars,
) -> tuple[str, str | None]:
    """Kembalikan (mode, serial yang dipakai). Mode salah satu dari repair_data.MODES."""
    try:
        states = state_reader()
    except ADBError:
        states = {}
    try:
        fastboot = fastboot_lister()
    except FastbootError:
        fastboot = []
    used = resolve_serial(serial, fastboot)
    if used is None:
        only = list(states)
        used = only[0] if len(only) == 1 else None
    if used is None:
        return "none", None
    fb_vars: dict[str, str] = {}
    if used in fastboot:
        try:
            fb_vars = vars_reader(used)
        except FastbootError:
            fb_vars = {}
    return bootloop.detect_mode(states.get(used, ""), fastboot, used, fb_vars), used


def resolve_sideload_serial(preferred: str | None, *, state_reader=get_devices_with_state) -> str | None:
    """Serial perangkat yang sedang di mode sideload (preferred bila cocok, atau satu-satunya)."""
    try:
        states = state_reader()
    except ADBError:
        return None
    if preferred and states.get(preferred) == "sideload":
        return preferred
    candidates = [s for s, state in states.items() if state == "sideload"]
    return candidates[0] if len(candidates) == 1 else None


def reboot_to(serial: str, target: str, mode: str) -> str:
    if target not in REBOOT_TARGETS:
        raise ValueError(f"Target reboot tidak dikenal: {target}")
    if mode in ("fastboot", "fastbootd"):
        if target == "system":
            return reboot_from_fastboot(serial)
        if target == "bootloader":
            return reboot_to_bootloader_from_fastboot(serial)
        if target == "fastboot":
            return reboot_to_fastbootd(serial)
        if target == "recovery":
            return run_fastboot("-s", serial, "reboot", "recovery", timeout=30)
        raise FastbootError(
            "Mode sideload tidak bisa dicapai dari fastboot. Reboot ke recovery lalu pilih 'Apply update from ADB'."
        )
    if mode in ("android", "recovery", "sideload"):
        return reboot_device(serial, mode=target)
    raise ADBError("Perangkat tidak terdeteksi lewat ADB maupun fastboot.")


def prepare_flash(
    serial: str,
    partition: str,
    image_path: str,
    expected_codename: str | None = None,
    *,
    vars_reader=get_fastboot_vars,
) -> dict:
    """Pemeriksaan sebelum konfirmasi flash. Tidak menulis apa pun ke perangkat."""
    fb_vars = vars_reader(serial)
    errors, warnings = validate_queue([FlashItem(partition, image_path)], fb_vars, expected_codename or None)
    if not expected_codename:
        warnings.append("Codename firmware tidak diisi: kecocokan model tidak diperiksa.")
    sha = sha256_file(image_path) if Path(image_path).is_file() else ""
    return {"errors": errors, "warnings": warnings, "product": fb_vars.get("product", ""), "sha256": sha}


def format_symptom_result(result: dict) -> str:
    def fmt(values: dict) -> str:
        if not values:
            return "-"
        return ", ".join(f"{k}={'tidak terbaca' if v is None else v}" for k, v in values.items())

    lines = [f"Gejala: {result['symptom']}", f"Sebelum: {fmt(result['before'])}", ""]
    for step in result["steps"]:
        lines.append(f"[{'OK' if step['ok'] else 'GAGAL'}] {step['title']}")
        if not step["ok"] and step["output"]:
            lines.append(f"    {step['output']}")
    lines += ["", f"Sesudah: {fmt(result['after'])}"]
    return "\n".join(lines)


def format_touch(points: list[tuple[int, int]]) -> str:
    if not points:
        return "Tidak ada sentuhan terbaca. Layar mungkin tidak merespons, atau tidak disentuh selama pengujian."
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (
        f"{len(points)} titik sentuh terbaca. X {min(xs)}-{max(xs)}, Y {min(ys)}-{max(ys)}.\n"
        "Sentuh sudut-sudut layar: kalau rentang jauh lebih sempit dari resolusi layar, ada area layar yang mati."
    )
