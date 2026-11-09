import pytest

from core.repair_session import (
    detect_current_mode,
    format_symptom_result,
    format_touch,
    prepare_flash,
    resolve_serial,
    resolve_sideload_serial,
)

VARS = {"unlocked": "yes", "product": "abc", "is-userspace": "no", "partition-size:boot": "0x10"}


def test_resolve_serial():
    assert resolve_serial("A", ["B"]) == "A"
    assert resolve_serial(None, ["B"]) == "B"
    assert resolve_serial(None, ["B", "C"]) is None


def test_detect_mode_android_fastboot_and_none():
    assert detect_current_mode(
        "S1", state_reader=lambda: {"S1": "device"}, fastboot_lister=lambda: [], vars_reader=lambda s: {}
    ) == ("android", "S1")
    assert detect_current_mode(
        None, state_reader=lambda: {}, fastboot_lister=lambda: ["F1"], vars_reader=lambda s: {"is-userspace": "yes"}
    ) == ("fastbootd", "F1")
    assert detect_current_mode(
        None, state_reader=lambda: {}, fastboot_lister=lambda: [], vars_reader=lambda s: {}
    ) == ("none", None)
    assert detect_current_mode(
        None, state_reader=lambda: {"R1": "recovery"}, fastboot_lister=lambda: [], vars_reader=lambda s: {}
    ) == ("recovery", "R1")


def test_resolve_sideload_serial():
    assert resolve_sideload_serial("A", state_reader=lambda: {"A": "sideload"}) == "A"
    assert resolve_sideload_serial(None, state_reader=lambda: {"B": "sideload", "C": "device"}) == "B"
    assert resolve_sideload_serial("A", state_reader=lambda: {"A": "device"}) is None
    assert resolve_sideload_serial(None, state_reader=lambda: {"B": "sideload", "C": "sideload"}) is None


def test_prepare_flash(tmp_path):
    image = tmp_path / "boot.img"
    image.write_bytes(b"x" * 16)
    ok = prepare_flash("S1", "boot", str(image), "abc", vars_reader=lambda s: VARS)
    assert ok["errors"] == [] and ok["product"] == "abc" and len(ok["sha256"]) == 64
    no_name = prepare_flash("S1", "boot", str(image), None, vars_reader=lambda s: VARS)
    assert any("Codename" in w for w in no_name["warnings"])
    locked = prepare_flash("S1", "boot", str(image), "abc", vars_reader=lambda s: {**VARS, "unlocked": "no"})
    assert locked["errors"]


def test_formatters():
    text = format_symptom_result(
        {
            "symptom": "storage_penuh",
            "before": {"storage_free_kb": 10},
            "steps": [{"id": "x", "title": "Bersihkan cache", "ok": False, "output": "error"}],
            "after": {"storage_free_kb": None},
        }
    )
    assert "storage_free_kb=10" in text and "[GAGAL]" in text and "tidak terbaca" in text
    assert "Tidak ada sentuhan" in format_touch([])
    assert "2 titik" in format_touch([(1, 2), (3, 4)])
