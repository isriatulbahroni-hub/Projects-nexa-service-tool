"""Tes aktif perangkat lewat ADB: getar, kamera, mikrofon, sentuh, kapasitas baterai.

Catatan: perintah getar berbeda antar versi Android; beberapa varian dicoba berurutan.
"""
from __future__ import annotations

import re

from .adb import ADBError, run_adb

VIBRATE_COMMANDS = (
    ("cmd", "vibrator_manager", "synced", "-f", "oneshot", "{ms}"),
    ("cmd", "vibrator", "vibrate", "{ms}", "shell"),
)

HEALTH_CODES = {2: "good", 3: "overheat", 4: "dead", 5: "over_voltage", 6: "failure", 7: "cold"}


def vibrate(serial: str, ms: int = 600, runner=run_adb) -> str:
    last: Exception | None = None
    for template in VIBRATE_COMMANDS:
        command = [part.format(ms=ms) for part in template]
        try:
            output = runner("-s", serial, "shell", *command, timeout=10)
        except ADBError as exc:
            last = exc
            continue
        if "unknown" in (output or "").lower() or "error" in (output or "").lower():
            last = ADBError(output)
            continue
        return " ".join(command)
    raise ADBError(f"Getar tidak bisa dipicu lewat ADB di perangkat ini: {last}")


def _start(serial: str, action: str, runner) -> str:
    output = runner("-s", serial, "shell", "am", "start", "-a", action, timeout=10)
    if "Error" in output:
        raise ADBError(output.strip())
    return output


def open_camera(serial: str, video: bool = False, runner=run_adb) -> str:
    action = "android.media.action.VIDEO_CAMERA" if video else "android.media.action.STILL_IMAGE_CAMERA"
    return _start(serial, action, runner)


def open_voice_recorder(serial: str, runner=run_adb) -> str:
    return _start(serial, "android.provider.MediaStore.RECORD_SOUND", runner)


def parse_touch_device(getevent_lp: str) -> str | None:
    """Cari perangkat input yang punya sumbu sentuh multi-touch dari keluaran `getevent -lp`."""
    blocks: list[tuple[str, str]] = []
    path = None
    lines: list[str] = []
    for line in getevent_lp.splitlines():
        if line.startswith("add device"):
            if path:
                blocks.append((path, "\n".join(lines)))
            path = line.split(": ", 1)[1].strip() if ": " in line else None
            lines = []
        else:
            lines.append(line)
    if path:
        blocks.append((path, "\n".join(lines)))
    for device, body in blocks:
        if "ABS_MT_POSITION_X" in body and "ABS_MT_POSITION_Y" in body:
            return device
    return None


def parse_touch_events(text: str) -> list[tuple[int, int]]:
    points: list[tuple[int, int]] = []
    x = y = None
    for line in text.splitlines():
        match = re.search(r"ABS_MT_POSITION_([XY])\s+([0-9a-fA-F]+)\s*$", line)
        if match:
            value = int(match.group(2), 16)
            if match.group(1) == "X":
                x = value
            else:
                y = value
        elif "SYN_REPORT" in line and x is not None and y is not None:
            points.append((x, y))
    return points


def read_touch_points(serial: str, count: int = 30, timeout: int = 30, runner=run_adb) -> list[tuple[int, int]]:
    device = parse_touch_device(runner("-s", serial, "shell", "getevent", "-lp", timeout=10))
    if not device:
        raise ADBError("Perangkat sentuh tidak ditemukan.")
    output = runner("-s", serial, "shell", "getevent", "-l", "-c", str(count * 4), device, timeout=timeout)
    return parse_touch_events(output)


def parse_battery(dumpsys_text: str) -> dict:
    values: dict[str, int] = {}
    for line in dumpsys_text.splitlines():
        match = re.match(r"\s*(level|temperature|health|status):\s*(-?\d+)", line)
        if match:
            values[match.group(1)] = int(match.group(2))
    out: dict = {}
    if "level" in values:
        out["level"] = values["level"]
    if "temperature" in values:
        out["temperature_c"] = values["temperature"] / 10
    if "health" in values:
        out["health"] = HEALTH_CODES.get(values["health"], "unknown")
    return out


def _read_int(serial: str, path: str, runner) -> int | None:
    try:
        return int(runner("-s", serial, "shell", "cat", path, timeout=10).strip())
    except (ADBError, ValueError):
        return None


def read_battery_capacity(serial: str, runner=run_adb) -> dict:
    """Level + suhu dari dumpsys, dan kesehatan kapasitas (charge_full / charge_full_design) bila tersedia."""
    info = parse_battery(runner("-s", serial, "shell", "dumpsys", "battery", timeout=10))
    base = "/sys/class/power_supply/battery/"
    full = _read_int(serial, base + "charge_full", runner)
    design = _read_int(serial, base + "charge_full_design", runner)
    if full and design:
        info["capacity_health_pct"] = round(full * 100 / design, 1)
    return info
