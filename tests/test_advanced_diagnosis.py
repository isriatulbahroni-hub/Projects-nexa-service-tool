import json
from pathlib import Path

import pytest

from core import advanced_diagnosis as ad

CASES = json.loads((Path(__file__).parent / "fixtures" / "deepscan_cases.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_analyze_matches_shared_cases(case):
    facts = json.loads(json.dumps(case["facts"]))
    if "touch_test" in facts:
        facts["touch_test"]["uncovered"] = [tuple(c) for c in facts["touch_test"]["uncovered"]]
    report = ad.analyze(facts)
    exp = case["expect"]
    assert sorted(f.code for f in report.findings) == exp["codes"]
    assert report.score == exp["score"]
    if exp["top"] is None:
        assert not report.suspects
    else:
        assert report.suspects[0].component == exp["top"]
        assert report.suspects[0].level == exp["level"]


def test_parse_battery_reads_wear_inputs():
    raw = """Current Battery Service state:
  AC powered: false
  USB powered: true
  Wireless powered: false
  status: 2
  health: 2
  present: true
  level: 85
  voltage: 4123
  temperature: 305
"""
    b = ad.parse_battery(raw, "cycle_count=312\ncharge_full=4400000\ncharge_full_design=5000000\n")
    assert b["usb"] is True and b["ac"] is False
    assert b["temp_c"] == 30.5 and b["level"] == 85 and b["voltage_mv"] == 4123
    assert b["cycle_count"] == 312 and b["charge_full"] == 4400000


def test_parse_battery_empty_sysfs_values_are_none():
    b = ad.parse_battery("  present: true\n", "cycle_count=\ncharge_full=\ncharge_full_design=\n")
    assert b["cycle_count"] is None and b["charge_full"] is None


def test_parse_storage_life_latency_free():
    diskstats = "Latency: 21ms [512B Data Write]\nData-Free: 12345K / 112345K total = 11% free\n"
    s = ad.parse_storage("0x01 0x0a\n", diskstats)
    assert s == {"life": 10, "write_latency_ms": 21, "free_percent": 11}


def test_parse_boot_classifies_reasons():
    hist = "reboot,userrequested,1699\nkernel_panic,1700\nwatchdog,1701\nshutdown,battery,1702\n"
    dropbox = "2026-11-01 10:00:00 SYSTEM_LAST_KMSG (text, 100 bytes)\n2026-11-02 system_server_watchdog (text)\n"
    b = ad.parse_boot(hist, "", dropbox)
    assert b["abnormal"] == 3 and b["power"] == 1 and b["kernel"] == 2
    assert b["dropbox"]["system_last_kmsg"] == 1 and b["dropbox"]["system_server_watchdog"] == 1


def test_parse_thermal_normalizes_millidegrees_and_hal():
    zones = "cpu-0-0=45000\nbattery=31200\nbogus=abc\n"
    svc = "Thermal Status: 0\nTemperature{mValue=36.5, mType=3, mName=skin, mStatus=0}"
    t = ad.parse_thermal(zones, svc)
    assert t["zones"]["cpu-0-0"] == 45.0 and t["zones"]["skin"] == 36.5
    assert t["max_c"] == 45.0 and t["status"] == 0


GETEVENT_LP = """add device 1: /dev/input/event2
  name:     "gpio-keys"
  events:
    KEY (0001): KEY_POWER
add device 2: /dev/input/event3
  name:     "fts_ts"
  events:
    ABS (0003): ABS_MT_SLOT           : value 0, min 0, max 9, fuzz 0, flat 0, resolution 0
                ABS_MT_POSITION_X     : value 0, min 0, max 1079, fuzz 0, flat 0, resolution 0
                ABS_MT_POSITION_Y     : value 0, min 0, max 2399, fuzz 0, flat 0, resolution 0
"""


def test_input_device_detection_picks_touchscreen():
    devs = ad.parse_input_devices(GETEVENT_LP)
    assert len(devs) == 1
    d = ad.pick_touchscreen(devs)
    assert d == {"path": "/dev/input/event3", "name": "fts_ts", "x_max": 1079, "y_max": 2399}


def test_no_touch_device():
    assert ad.parse_input_devices("add device 1: /dev/input/event2\n  name: \"gpio-keys\"\n") == []
    assert ad.pick_touchscreen([]) is None


def _sweep(x_max, y_max, skip=lambda c, r: False, cols=6, rows=10):
    lines = []
    for r in range(rows):
        for c in range(cols):
            if skip(c, r):
                continue
            x = int((c + 0.5) / cols * (x_max + 1))
            y = int((r + 0.5) / rows * (y_max + 1))
            lines.append(f"/dev/input/event3: EV_ABS       ABS_MT_POSITION_X    {x:08x}")
            lines.append(f"/dev/input/event3: EV_ABS       ABS_MT_POSITION_Y    {y:08x}")
            lines.append("/dev/input/event3: EV_SYN       SYN_REPORT           00000000")
    return "\n".join(lines)


def test_touch_coverage_full_sweep():
    res = ad.touch_coverage(_sweep(1079, 2399), 1079, 2399)
    assert res["coverage"] == 1.0 and res["uncovered"] == []


def test_touch_coverage_finds_dead_block():
    dead = lambda c, r: c <= 1 and r <= 1
    res = ad.touch_coverage(_sweep(1079, 2399, skip=dead), 1079, 2399)
    assert sorted(res["uncovered"]) == [(0, 0), (0, 1), (1, 0), (1, 1)]
    assert res["coverage"] == pytest.approx(56 / 60)


def test_run_touch_test_uses_timeout_and_validates_path():
    seen = {}

    def runner(serial, cmd):
        seen["cmd"] = cmd
        return _sweep(1079, 2399)

    dev = {"path": "/dev/input/event3", "x_max": 1079, "y_max": 2399}
    res = ad.run_touch_test("S", dev, seconds=12, runner=runner)
    assert res["coverage"] == 1.0
    assert seen["cmd"] == "timeout 12 getevent -l /dev/input/event3; true"
    with pytest.raises(ad.ADBError):
        ad.run_touch_test("S", {"path": "/dev/input/event3; rm -rf /", "x_max": 1, "y_max": 1}, runner=runner)


def test_collect_facts_marks_failed_probes_unreadable_and_never_guesses():
    def runner(serial, cmd):
        if cmd == "dumpsys battery":
            return "  present: true\n  level: 50\n  health: 2\n  USB powered: true\n"
        if cmd.startswith("logcat"):
            raise ad.ADBError("permission denied")
        if cmd == "getevent -lp":
            return GETEVENT_LP
        return ""

    facts = ad.collect_facts("S", runner=runner, usb_connected=True)
    assert facts["battery"]["level"] == 50
    assert facts["input"]["touch_found"] is True
    assert any("Log radio" in u for u in facts["unreadable"])
    assert any("Log crash" in u for u in facts["unreadable"])
    report = ad.analyze(facts)
    assert report.score >= 90  # tidak ada temuan karangan dari data kosong


def test_collect_facts_all_probes_failing_yields_honest_note():
    def runner(serial, cmd):
        raise ad.ADBError("offline")

    facts = ad.collect_facts("S", runner=runner)
    report = ad.analyze(facts)
    assert not report.findings
    assert any("tidak terbaca" in n for n in report.notes)


def test_touch_coverage_separates_fingers_by_slot():
    # Jari 0 di sel (0,0), jari 1 di sel (5,9). Tanpa pemisahan slot, X jari 1
    # bisa terpasang dengan Y jari 0 dan mencatat sel yang tidak pernah disentuh.
    ev = "\n".join([
        "EV_ABS ABS_MT_SLOT 00000000",
        "EV_ABS ABS_MT_POSITION_X 00000010",
        "EV_ABS ABS_MT_POSITION_Y 00000010",
        "EV_ABS ABS_MT_SLOT 00000001",
        "EV_ABS ABS_MT_POSITION_X 00000430",
        "EV_ABS ABS_MT_POSITION_Y 00000950",
        "EV_SYN SYN_REPORT 00000000",
    ])
    res = ad.touch_coverage(ev, 1079, 2399)
    assert res["points"] == 2
    assert len(res["uncovered"]) == 58
    assert (0, 0) not in res["uncovered"] and (5, 9) not in res["uncovered"]
    assert (5, 0) in res["uncovered"] and (0, 9) in res["uncovered"]


def test_touch_coverage_without_syn_falls_back_to_pairs():
    ev = "ABS_MT_POSITION_X 00000010\nABS_MT_POSITION_Y 00000010\n"
    res = ad.touch_coverage(ev, 1079, 2399)
    assert res["points"] == 1 and (0, 0) not in res["uncovered"]


def test_is_usb_serial():
    assert ad.is_usb_serial("R58M123ABC")
    assert not ad.is_usb_serial("192.168.1.20:37123")
    assert not ad.is_usb_serial("adb-R58M123-abcd._adb-tls-connect._tcp")
    assert not ad.is_usb_serial("")


def test_render_html_escapes_and_shows_touch_map():
    facts = {"battery": {"present": False}, "touch_test": {
        "cols": 6, "rows": 10, "coverage": 0.9, "points": 5, "uncovered": [(0, 0)]}}
    report = ad.analyze(facts)
    html = ad.render_html(report, facts["touch_test"])
    assert "Baterai tidak terdeteksi" in html and "#ff6b6b" in html
    assert "Peta uji sentuh (90% tersentuh)" in html
    report.findings.append(ad.Finding("X", "<b>x</b>", "info", "<script>alert(1)</script>", "d"))
    assert "<script>" not in ad.render_html(report)
