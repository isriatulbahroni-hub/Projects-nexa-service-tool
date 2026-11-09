import zipfile

import pytest

from core import bootloop
from core.firmware import FastbootError  # noqa: F401
from core.flash_safety import (
    FlashItem,
    FlashSafetyError,
    build_queue_from_folder,
    execute_queue,
    sha256_file,
    validate_queue,
)
from core.hardware_active import parse_battery, parse_touch_device, parse_touch_events
from core.repair_actions import run_symptom
from core.sideload import validate_ota_package

VARS = {"unlocked": "yes", "product": "abc", "is-userspace": "no", "partition-size:boot": "0x10"}


def _img(tmp_path, name="boot.img", size=16):
    path = tmp_path / name
    path.write_bytes(b"x" * size)
    return str(path)


# ---- bootloop ----
def test_detect_mode():
    assert bootloop.detect_mode("device", [], "S") == "android"
    assert bootloop.detect_mode("sideload", [], "S") == "sideload"
    assert bootloop.detect_mode("", ["S"], "S", {"is-userspace": "yes"}) == "fastbootd"
    assert bootloop.detect_mode("", ["S"], "S", {"is-userspace": "no"}) == "fastboot"
    assert bootloop.detect_mode("weird", [], "S") == "none"


def test_destructive_steps_locked_until_safe_steps_done():
    states = {s["id"]: s["state"] for s in bootloop.next_steps("recovery")}
    assert states["factory_reset"] == "locked"
    assert states["reflash_boot"] == "wrong_mode"
    done = {"charge_restart", "wipe_cache", "sideload_ota"}
    states = {s["id"]: s["state"] for s in bootloop.next_steps("recovery", done=done)}
    assert states["factory_reset"] == "ready"


# ---- flash_safety ----
def test_valid_queue(tmp_path):
    errors, _ = validate_queue([FlashItem("boot", _img(tmp_path))], VARS, "ABC")
    assert errors == []


def test_locked_bootloader_blocked(tmp_path):
    errors, _ = validate_queue([FlashItem("boot", _img(tmp_path))], {**VARS, "unlocked": "no"})
    assert any("terkunci" in e for e in errors)


def test_critical_partition_blocked(tmp_path):
    errors, _ = validate_queue([FlashItem("modem", _img(tmp_path, "modem.img"))], VARS)
    assert any("kritis" in e for e in errors)


def test_logical_partition_needs_fastbootd(tmp_path):
    errors, _ = validate_queue([FlashItem("system", _img(tmp_path, "system.img"))], VARS)
    assert any("fastbootd" in e for e in errors)
    errors, _ = validate_queue([FlashItem("system", _img(tmp_path, "system.img"))], {**VARS, "is-userspace": "yes"})
    assert errors == []


def test_oversize_codename_and_sha(tmp_path):
    errors, _ = validate_queue([FlashItem("boot", _img(tmp_path, size=17))], VARS)
    assert errors
    path = _img(tmp_path)
    errors, _ = validate_queue([FlashItem("boot", path)], VARS, "xyz")
    assert any("Codename" in e for e in errors)
    errors, _ = validate_queue([FlashItem("boot", path, sha256="0" * 64)], VARS)
    assert any("SHA-256" in e for e in errors)
    errors, _ = validate_queue([FlashItem("boot", path, sha256=sha256_file(path))], VARS)
    assert errors == []


def test_all_or_nothing(tmp_path):
    calls = []
    items = [FlashItem("boot", _img(tmp_path)), FlashItem("modem", _img(tmp_path, "modem.img"))]
    with pytest.raises(FlashSafetyError):
        execute_queue(
            "S1",
            items,
            flasher=lambda p, i, serial=None: calls.append(p) or "ok",
            vars_reader=lambda s: VARS,
            device_lister=lambda: ["S1"],
        )
    assert calls == []


def test_execute_ok_and_requires_serial(tmp_path):
    calls = []
    items = [FlashItem("boot", _img(tmp_path))]
    kwargs = dict(
        flasher=lambda p, i, serial=None: calls.append(p) or "ok",
        vars_reader=lambda s: VARS,
        device_lister=lambda: ["S1"],
    )
    assert execute_queue("S1", items, **kwargs) == [("boot", "ok")]
    assert calls == ["boot"]
    with pytest.raises(FlashSafetyError):
        execute_queue("", items, **kwargs)
    with pytest.raises(FlashSafetyError):
        execute_queue("OTHER", items, **kwargs)


def test_build_queue_from_folder(tmp_path):
    for name in ("boot.img", "userdata.img", "modem.img"):
        _img(tmp_path, name)
    (tmp_path / "notes.txt").write_text("x")
    items, skipped = build_queue_from_folder(tmp_path)
    assert [i.partition for i in items] == ["boot"]
    assert sorted(skipped) == ["modem.img", "userdata.img"]


# ---- sideload ----
def _ota(tmp_path, meta="pre-device=abc,def\nota-type=AB\n", payload=True):
    path = tmp_path / "ota.zip"
    with zipfile.ZipFile(path, "w") as archive:
        if meta is not None:
            archive.writestr("META-INF/com/android/metadata", meta)
        if payload:
            archive.writestr("payload.bin", b"x")
    return path


def test_ota_validation(tmp_path):
    assert validate_ota_package(_ota(tmp_path), "DEF").ok
    assert not validate_ota_package(_ota(tmp_path), "xyz").ok
    assert not validate_ota_package(_ota(tmp_path, meta=None)).ok
    assert not validate_ota_package(_ota(tmp_path, payload=False)).ok
    junk = tmp_path / "junk.zip"
    junk.write_text("bukan zip")
    assert not validate_ota_package(junk).ok


# ---- hardware_active ----
GETEVENT_LP = """add device 1: /dev/input/event0
  name:     "gpio-keys"
  events:
    KEY (0001): KEY_VOLUMEUP
add device 2: /dev/input/event3
  name:     "touchpanel"
  events:
    ABS (0003): ABS_MT_POSITION_X    : value 0, min 0, max 1079
                ABS_MT_POSITION_Y    : value 0, min 0, max 2399
"""

GETEVENT_EVENTS = """/dev/input/event3: EV_ABS       ABS_MT_POSITION_X    000001f4
/dev/input/event3: EV_ABS       ABS_MT_POSITION_Y    00000320
/dev/input/event3: EV_SYN       SYN_REPORT           00000000
"""


def test_touch_parsing():
    assert parse_touch_device(GETEVENT_LP) == "/dev/input/event3"
    assert parse_touch_events(GETEVENT_EVENTS) == [(500, 800)]


def test_battery_parsing():
    info = parse_battery("Current Battery Service state:\n  status: 3\n  health: 2\n  level: 87\n  temperature: 291\n")
    assert info == {"level": 87, "temperature_c": 29.1, "health": "good"}


# ---- repair_actions ----
def test_run_symptom_measures_before_and_after():
    def runner(*args, timeout=15):
        if "df" in args:
            return "Filesystem 1K-blocks Used Available Use% Mounted on\n/dev/block/dm-5 100 40 60 40% /data"
        return ""

    result = run_symptom("S1", "storage_penuh", runner=runner, sleep=lambda s: None)
    assert result["before"]["storage_free_kb"] == 60
    assert all(step["ok"] for step in result["steps"])
    with pytest.raises(ValueError):
        run_symptom("S1", "tidak_ada", runner=runner)
