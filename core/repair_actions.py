"""Perbaikan per gejala: ukur sebelum, jalankan aksi, ukur sesudah."""
from __future__ import annotations

import re
import time

from .adb import ADBError, run_adb
from .repair_data import SYMPTOMS


def parse_df_free_kb(text: str) -> int | None:
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[-1] == "/data":
            try:
                return int(parts[3])
            except ValueError:
                return None
    return None


def parse_meminfo_available_kb(text: str) -> int | None:
    match = re.search(r"MemAvailable:\s+(\d+)", text)
    return int(match.group(1)) if match else None


def parse_battery_temp_c(text: str) -> float | None:
    match = re.search(r"temperature:\s*(-?\d+)", text)
    return int(match.group(1)) / 10 if match else None


_MEASURES = {
    "storage_free_kb": (("shell", "df", "/data"), parse_df_free_kb),
    "mem_available_kb": (("shell", "cat", "/proc/meminfo"), parse_meminfo_available_kb),
    "battery_temp_c": (("shell", "dumpsys", "battery"), parse_battery_temp_c),
}


def measure(serial: str, names: list[str], runner=run_adb) -> dict:
    out: dict = {}
    for name in names:
        args, parser = _MEASURES[name]
        try:
            out[name] = parser(runner("-s", serial, *args, timeout=15))
        except ADBError:
            out[name] = None
    return out


def run_symptom(serial: str, symptom_id: str, runner=run_adb, sleep=time.sleep) -> dict:
    profile = SYMPTOMS.get(symptom_id)
    if profile is None:
        raise ValueError(f"Gejala tidak dikenal: {symptom_id}")
    before = measure(serial, profile["measure"], runner)
    steps = []
    for action in profile["actions"]:
        try:
            output = runner("-s", serial, *action["cmd"], timeout=60)
            ok = True
        except ADBError as exc:
            output = str(exc)
            ok = False
        steps.append({"id": action["id"], "title": action["title"], "ok": ok, "output": (output or "")[:300]})
        if action.get("wait"):
            sleep(action["wait"])
    after = measure(serial, profile["measure"], runner)
    return {"symptom": symptom_id, "before": before, "steps": steps, "after": after}
