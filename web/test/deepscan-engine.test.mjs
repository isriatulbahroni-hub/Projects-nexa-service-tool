import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import * as E from "../src/deepscan-engine.js";
import { collectFacts, renderResult, runTouchTest } from "../src/deepscan.js";

const CASES = JSON.parse(readFileSync(new URL("../../tests/fixtures/deepscan_cases.json", import.meta.url), "utf8"));

for (const c of CASES) {
  test(`kasus bersama: ${c.name}`, () => {
    const report = E.analyze(JSON.parse(JSON.stringify(c.facts)));
    assert.deepEqual(report.findings.map((f) => f.code).sort(), c.expect.codes);
    assert.equal(report.score, c.expect.score);
    if (c.expect.top === null) assert.equal(report.suspects.length, 0);
    else {
      assert.equal(report.suspects[0].component, c.expect.top);
      assert.equal(report.suspects[0].level, c.expect.level);
    }
  });
}

test("parseBattery membaca dumpsys dan sysfs", () => {
  const raw = "Current Battery Service state:\n  AC powered: false\n  USB powered: true\n  Wireless powered: false\n  status: 2\n  health: 2\n  present: true\n  level: 85\n  voltage: 4123\n  temperature: 305\n";
  const b = E.parseBattery(raw, "cycle_count=312\ncharge_full=4400000\ncharge_full_design=5000000\n");
  assert.equal(b.usb, true); assert.equal(b.ac, false);
  assert.equal(b.temp_c, 30.5); assert.equal(b.level, 85); assert.equal(b.voltage_mv, 4123);
  assert.equal(b.cycle_count, 312); assert.equal(b.charge_full, 4400000);
  const e = E.parseBattery("  present: true\n", "cycle_count=\ncharge_full=\ncharge_full_design=\n");
  assert.equal(e.cycle_count, null); assert.equal(e.charge_full, null);
});

test("parseStorage", () => {
  const s = E.parseStorage("0x01 0x0a\n", "Latency: 21ms [512B Data Write]\nData-Free: 12345K / 112345K total = 11% free\n");
  assert.deepEqual(s, { life: 10, write_latency_ms: 21, free_percent: 11 });
});

test("parseBoot memilah alasan restart", () => {
  const hist = "reboot,userrequested,1699\nkernel_panic,1700\nwatchdog,1701\nshutdown,battery,1702\n";
  const dropbox = "2026-11-01 10:00:00 SYSTEM_LAST_KMSG (text, 100 bytes)\n2026-11-02 system_server_watchdog (text)\n";
  const b = E.parseBoot(hist, "", dropbox);
  assert.equal(b.abnormal, 3); assert.equal(b.power, 1); assert.equal(b.kernel, 2);
  assert.equal(b.dropbox.system_last_kmsg, 1); assert.equal(b.dropbox.system_server_watchdog, 1);
});

test("parseThermal menormalkan mili-derajat dan HAL", () => {
  const t = E.parseThermal("cpu-0-0=45000\nbattery=31200\nbogus=abc\n", "Thermal Status: 0\nTemperature{mValue=36.5, mType=3, mName=skin, mStatus=0}");
  assert.equal(t.zones["cpu-0-0"], 45); assert.equal(t.zones.skin, 36.5);
  assert.equal(t.max_c, 45); assert.equal(t.status, 0);
});

const GETEVENT_LP = `add device 1: /dev/input/event2
  name:     "gpio-keys"
  events:
    KEY (0001): KEY_POWER
add device 2: /dev/input/event3
  name:     "fts_ts"
  events:
    ABS (0003): ABS_MT_SLOT           : value 0, min 0, max 9, fuzz 0, flat 0, resolution 0
                ABS_MT_POSITION_X     : value 0, min 0, max 1079, fuzz 0, flat 0, resolution 0
                ABS_MT_POSITION_Y     : value 0, min 0, max 2399, fuzz 0, flat 0, resolution 0
`;

test("deteksi layar sentuh", () => {
  const devs = E.parseInputDevices(GETEVENT_LP);
  assert.equal(devs.length, 1);
  assert.deepEqual(E.pickTouchscreen(devs), { path: "/dev/input/event3", name: "fts_ts", x_max: 1079, y_max: 2399 });
  assert.deepEqual(E.parseInputDevices('add device 1: /dev/input/event2\n  name: "gpio-keys"\n'), []);
  assert.equal(E.pickTouchscreen([]), null);
});

function sweep(skip = () => false, cols = 6, rows = 10) {
  const lines = [];
  for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
    if (skip(c, r)) continue;
    const x = Math.trunc(((c + 0.5) / cols) * 1080), y = Math.trunc(((r + 0.5) / rows) * 2400);
    lines.push(`/dev/input/event3: EV_ABS       ABS_MT_POSITION_X    ${x.toString(16).padStart(8, "0")}`);
    lines.push(`/dev/input/event3: EV_ABS       ABS_MT_POSITION_Y    ${y.toString(16).padStart(8, "0")}`);
    lines.push("/dev/input/event3: EV_SYN       SYN_REPORT           00000000");
  }
  return lines.join("\n");
}

test("touchCoverage: sapuan penuh dan blok mati", () => {
  const full = E.touchCoverage(sweep(), 1079, 2399);
  assert.equal(full.coverage, 1); assert.deepEqual(full.uncovered, []);
  const res = E.touchCoverage(sweep((c, r) => c <= 1 && r <= 1), 1079, 2399);
  assert.deepEqual(res.uncovered, [[0, 0], [1, 0], [0, 1], [1, 1]]);
  assert.ok(Math.abs(res.coverage - 56 / 60) < 1e-9);
});

test("touchCoverage memisahkan jari per slot", () => {
  const ev = ["EV_ABS ABS_MT_SLOT 00000000", "EV_ABS ABS_MT_POSITION_X 00000010", "EV_ABS ABS_MT_POSITION_Y 00000010",
    "EV_ABS ABS_MT_SLOT 00000001", "EV_ABS ABS_MT_POSITION_X 00000430", "EV_ABS ABS_MT_POSITION_Y 00000950",
    "EV_SYN SYN_REPORT 00000000"].join("\n");
  const res = E.touchCoverage(ev, 1079, 2399);
  assert.equal(res.points, 2); assert.equal(res.uncovered.length, 58);
  assert.ok(!res.uncovered.some(([c, r]) => (c === 0 && r === 0) || (c === 5 && r === 9)));
});

test("touchCoverage tanpa SYN_REPORT memakai pasangan X dan Y", () => {
  const res = E.touchCoverage("ABS_MT_POSITION_X 00000010\nABS_MT_POSITION_Y 00000010\n", 1079, 2399);
  assert.equal(res.points, 1);
});

test("runTouchTest memakai timeout dan memvalidasi path", async () => {
  let seen = "";
  const run = async (cmd) => { seen = cmd; return sweep(); };
  const dev = { path: "/dev/input/event3", x_max: 1079, y_max: 2399 };
  assert.equal((await runTouchTest(run, dev, 12)).coverage, 1);
  assert.equal(seen, "timeout 12 getevent -l /dev/input/event3; true");
  await assert.rejects(() => runTouchTest(run, { path: "/dev/input/event3; rm -rf /", x_max: 1, y_max: 1 }), /tidak valid/);
});

test("collectFacts: probe gagal dan galat tertulis masuk 'tidak terbaca', tanpa menebak", async () => {
  const run = async (cmd) => {
    if (cmd === "dumpsys battery") return "  present: true\n  level: 50\n  health: 2\n  USB powered: true\n";
    if (cmd.startsWith("logcat")) throw new Error("izin ditolak");
    if (cmd === "getevent -lp") return GETEVENT_LP;
    if (cmd === "dumpsys media.camera") return "Can't find service: media.camera";
    return "";
  };
  const facts = await collectFacts(run, { usbConnected: true });
  assert.equal(facts.battery.level, 50);
  assert.equal(facts.input.touch_found, true);
  assert.ok(facts.unreadable.some((u) => u.startsWith("Log radio")));
  assert.ok(facts.unreadable.some((u) => u.startsWith("Log crash")));
  assert.ok(facts.unreadable.includes("Kamera"));
  assert.equal(facts.camera.count, null);
  assert.ok(E.analyze(facts).score >= 90);
});

test("semua probe gagal memberi catatan jujur dan nol temuan", async () => {
  const facts = await collectFacts(async () => { throw new Error("offline"); });
  const report = E.analyze(facts);
  assert.equal(report.findings.length, 0);
  assert.ok(report.notes.some((n) => n.includes("tidak terbaca")));
});

test("renderResult meng-escape teks dan menampilkan peta sentuh", () => {
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const report = E.analyze({ battery: { present: false } });
  report.findings.push({ code: "X", component: "<b>x</b>", severity: "info", title: "<script>alert(1)</script>", detail: "d", weight: null });
  const html = renderResult(report, { cols: 6, rows: 10, coverage: 0.9, uncovered: [[0, 0]] }, esc);
  assert.ok(html.includes("Baterai tidak terdeteksi"));
  assert.ok(html.includes("Peta uji sentuh (90% tersentuh)"));
  assert.ok(!html.includes("<script>"));
});
