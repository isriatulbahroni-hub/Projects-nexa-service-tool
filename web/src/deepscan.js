// Halaman Deep Scan: probe baca-saja ke HP + uji sentuh, lalu tampilkan dugaan komponen rusak.
// Aturan penyimpulnya ada di deepscan-engine.js (sama dengan core/advanced_diagnosis.py).

import {
  analyze, parseBattery, parseStorage, parseBoot, parseThermal, parseInputDevices, pickTouchscreen,
  touchCoverage, parseModem, parseSensors, parseCamera, parseSoftware,
} from "./deepscan-engine.js";

const ERR_RE = /(permission denied|not found|inaccessible|no such file|operation not permitted|unknown command|can't find service|not allowed|securityexception)/i;

const SYSFS_BATTERY =
  'for f in cycle_count charge_full charge_full_design; do echo "$f=$(cat /sys/class/power_supply/battery/$f 2>/dev/null)"; done';
const LIFE_CMD =
  "cat $(find /sys/devices /sys/block -maxdepth 7 \\( -name life_time -o -name life_time_estimation_a -o -name life_time_estimation_b \\) 2>/dev/null | head -4) 2>/dev/null; true";
const ZONES_CMD =
  'for z in /sys/class/thermal/thermal_zone*; do echo "$(cat $z/type 2>/dev/null)=$(cat $z/temp 2>/dev/null)"; done';

// run(cmd) harus melempar error kalau perintah gagal dijalankan. Keluaran yang
// jelas berupa pesan galat juga dianggap "tidak terbaca" (ADB web tidak memberi kode keluar).
export async function collectFacts(run, { usbConnected = true, onStep = () => {} } = {}) {
  const unreadable = [];
  let probes = 0;

  const probe = async (name, cmd, requireText = false) => {
    probes += 1;
    onStep(name);
    try {
      const out = (await run(cmd)) || "";
      const trimmed = out.trim();
      if (trimmed.length < 400 && ERR_RE.test(trimmed)) {
        unreadable.push(name);
        return "";
      }
      if (requireText && !trimmed) unreadable.push(name);
      return out;
    } catch (e) {
      unreadable.push(`${name} (${e.message || e})`);
      return "";
    }
  };

  const batRaw = await probe("Baterai", "dumpsys battery", true);
  const batSys = await probe("Baterai (sysfs)", SYSFS_BATTERY);
  const life = await probe("Umur storage", LIFE_CMD);
  const disk = await probe("Latensi storage", "dumpsys diskstats", true);
  const df = await probe("Kapasitas storage", "df -k /data");
  const hist = await probe("Riwayat boot", "getprop persist.sys.boot.reason.history");
  const cur = await probe("Alasan boot", "getprop sys.boot.reason");
  const dropbox = await probe("Dropbox sistem", "dumpsys dropbox");
  const zones = await probe("Suhu zona", ZONES_CMD);
  const thermal = await probe("Thermal service", "dumpsys thermalservice");
  const evLp = await probe("Perangkat input", "getevent -lp", true);
  const props = {};
  for (const p of ["gsm.sim.state", "gsm.version.baseband"]) props[p] = (await probe(`Prop ${p}`, `getprop ${p}`)).trim();
  const radio = await probe("Log radio", "logcat -d -b radio -t 500");
  const sensors = await probe("Sensor", "dumpsys sensorservice", true);
  const cam = await probe("Kamera", "dumpsys media.camera");
  const feats = await probe("Fitur", "pm list features");
  const crash = await probe("Log crash", "logcat -d -b crash -t 500");

  const touch = pickTouchscreen(parseInputDevices(evLp));
  return {
    battery: parseBattery(batRaw, batSys),
    usb_connected: usbConnected,
    storage: parseStorage(life, disk, df),
    boot: parseBoot(hist, cur, dropbox),
    thermal: parseThermal(zones, thermal),
    input: { touch_found: evLp.trim() ? touch != null : null, device: touch },
    modem: parseModem(props, radio),
    sensors: parseSensors(sensors),
    camera: parseCamera(cam, feats),
    software: parseSoftware(crash),
    unreadable,
    probe_count: probes,
  };
}

export async function runTouchTest(run, device, seconds = 12) {
  if (!/^\/dev\/input\/event\d+$/.test(device.path)) throw new Error("Path perangkat input tidak valid.");
  const out = await run(`timeout ${seconds} getevent -l ${device.path}; true`);
  return touchCoverage(out, device.x_max, device.y_max);
}

const LEVEL_COLOR = { Tinggi: "var(--bad)", Sedang: "var(--warn)", Rendah: "var(--mute)" };
const SEV = { fail: ["fail", "RUSAK?"], warn: ["warn", "CEK"], info: ["info", "INFO"] };

export function renderResult(report, touchTest, esc) {
  const parts = [
    `<div class="card"><h2>Skor ${report.score}/100</h2><p><b>${esc(report.verdict)}</b></p></div>`,
  ];
  if (report.suspects.length) {
    parts.push(`<div class="card"><h2>Dugaan komponen</h2>${report.suspects.map((s) => {
      const pct = Math.round(s.confidence * 100);
      return `<div style="margin:0 0 14px"><b>${esc(s.component)}</b>
        <span style="color:${LEVEL_COLOR[s.level]}"> keyakinan ${s.level} (${pct}%)</span>
        <div style="background:var(--line);height:6px;border-radius:3px;margin:5px 0">
          <div style="background:${LEVEL_COLOR[s.level]};width:${pct}%;height:6px;border-radius:3px"></div></div>
        <div class="muted">Bukti: ${esc(s.reasons.join("; "))}</div>
        <div>Saran: ${esc(s.action)}</div></div>`;
    }).join("")}</div>`);
  }
  if (report.findings.length) {
    parts.push(`<div class="card"><h2>Semua temuan</h2><table>${report.findings.map((f) => {
      const [cls, label] = SEV[f.severity];
      return `<tr><td class="${cls}"><b>${label}</b></td><td>${esc(f.component)}</td>
        <td><b>${esc(f.title)}</b><br><span class="muted">${esc(f.detail)}</span></td></tr>`;
    }).join("")}</table></div>`);
  }
  if (touchTest) {
    const dead = new Set(touchTest.uncovered.map(([c, r]) => `${c},${r}`));
    let cells = "";
    for (let r = 0; r < touchTest.rows; r++) {
      for (let c = 0; c < touchTest.cols; c++) {
        cells += `<i style="display:block;height:14px;border-radius:2px;background:${dead.has(`${c},${r}`) ? "var(--bad)" : "var(--ok)"}"></i>`;
      }
    }
    parts.push(`<div class="card"><h2>Peta uji sentuh (${(touchTest.coverage * 100).toFixed(0)}% tersentuh)</h2>
      <div style="display:grid;grid-template-columns:repeat(${touchTest.cols},22px);gap:2px">${cells}</div>
      <p class="muted">Hijau = merespons, merah = tidak tersentuh.</p></div>`);
  }
  if (report.unreadable.length) {
    parts.push(`<div class="card"><h2>Tidak terbaca</h2><ul>${report.unreadable.map((u) => `<li>${esc(u)}</li>`).join("")}</ul></div>`);
  }
  for (const n of report.notes) parts.push(`<p class="muted">${esc(n)}</p>`);
  return parts.join("");
}

export async function renderDeepScan(view, ctx) {
  const { runStrict, esc } = ctx;
  let facts = null;

  view.innerHTML = `
    <div class="card">
      <h2>Deep Scan</h2>
      <p class="muted">Deteksi kerusakan lanjutan: baterai (keausan, siklus), port charge, umur storage, restart sendiri,
      sentuh, modem, sensor, kamera, dan panas. Hanya membaca. Hasil berupa dugaan komponen dengan tingkat keyakinan;
      kerusakan fisik, cairan, dan board tanpa gejala di software tidak terbaca lewat ADB.</p>
      <div class="row">
        <button id="dsStart" class="primary">▶ Mulai Deep Scan</button>
        <button id="dsTouch">👆 Uji Sentuh (12 detik)</button>
      </div>
      <p id="dsStat" class="muted">Tekan Mulai Deep Scan.</p>
    </div>
    <div id="dsOut"></div>`;

  const $ = (s) => view.querySelector(s);
  const stat = (t) => { const el = $("#dsStat"); if (el) el.textContent = t; };
  const busy = (b) => { for (const id of ["#dsStart", "#dsTouch"]) { const el = $(id); if (el) el.disabled = b; } };
  const draw = () => {
    const out = $("#dsOut");
    if (!out) return;
    out.innerHTML = renderResult(analyze(facts || {}), facts?.touch_test, esc);
  };

  $("#dsStart").onclick = async () => {
    busy(true);
    try {
      const prev = facts?.touch_test;
      facts = await collectFacts(runStrict, { usbConnected: true, onStep: (n) => stat(`Memeriksa: ${n}…`) });
      if (prev) facts.touch_test = prev;
      stat("Selesai.");
      draw();
    } catch (e) {
      stat("Gagal: " + (e.message || e));
    } finally {
      busy(false);
    }
  };

  $("#dsTouch").onclick = async () => {
    busy(true);
    try {
      const device = pickTouchscreen(parseInputDevices(await runStrict("getevent -lp")));
      if (!device) throw new Error("Panel sentuh tidak terdeteksi di HP ini.");
      if (!confirm("Setelah menekan OK, sapukan jari ke SELURUH layar HP (atas ke bawah, kiri ke kanan) selama 12 detik. Layar harus menyala dan tidak terkunci.")) return;
      let left = 12;
      stat(`Sapu seluruh layar HP sekarang… ${left} detik`);
      const timer = setInterval(() => { left = Math.max(0, left - 1); stat(`Sapu seluruh layar HP sekarang… ${left} detik`); }, 1000);
      let result;
      try { result = await runTouchTest(runStrict, device, 12); } finally { clearInterval(timer); }
      facts = facts || {};
      facts.touch_test = result;
      stat(`Uji sentuh selesai: ${(result.coverage * 100).toFixed(0)}% layar tersentuh.`);
      draw();
    } catch (e) {
      stat("Gagal: " + (e.message || e));
    } finally {
      busy(false);
    }
  };
}
