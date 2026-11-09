// Deep Scan: deteksi kerusakan lanjutan (hanya membaca).
// Port dari core/advanced_diagnosis.py. Aturan, ambang, dan bobotnya HARUS sama;
// kedua versi dites dengan berkas yang sama (tests/fixtures/deepscan_cases.json).
//
// Batas yang jujur: ADB hanya melihat HP yang sudah menyala. Kerusakan fisik,
// cairan, dan board tanpa gejala di software tidak terbaca. Hasil = petunjuk.

export const C = {
  BATTERY: "Baterai",
  CHARGE: "Port charge / IC pengisian",
  STORAGE: "Penyimpanan (eMMC/UFS)",
  TOUCH: "Layar / touch panel",
  BOARD: "Mainboard / catu daya",
  MODEM: "Modem / sinyal",
  SENSOR: "Sensor",
  CAMERA: "Kamera",
  SOFTWARE: "Software / sistem",
  THERMAL: "Panas berlebih / pendinginan",
};

export const ACTIONS = {
  [C.BATTERY]: "Uji dengan baterai pengganti atau ganti baterai. Jangan dipakai kalau menggembung.",
  [C.CHARGE]: "Bersihkan port, coba kabel dan adaptor lain, lalu periksa flex/port charge dan IC pengisian.",
  [C.STORAGE]: "Backup data sekarang. Kalau sudah lambat atau umur flash tinggi, siapkan ganti/reball storage.",
  [C.TOUCH]: "Coba layar lain untuk membandingkan. Periksa flex touch dan IC touch kalau layar baru pun sama.",
  [C.BOARD]: "Cek baterai dan konektor dulu. Kalau tetap restart sendiri, periksa IC power (PMIC) dan jalur power di board.",
  [C.MODEM]: "Cek SIM tray dan antena. Kalau baseband hilang, periksa IC/EMMC modem atau lakukan perbaikan IMEI/baseband resmi.",
  [C.SENSOR]: "Cek flex sensor dan konektor. Bandingkan dengan HP sejenis yang normal.",
  [C.CAMERA]: "Cek konektor modul kamera dan coba modul pengganti.",
  [C.SOFTWARE]: "Update/flash firmware resmi setelah backup. Kalau gejala tetap ada, curigai hardware.",
  [C.THERMAL]: "Bersihkan debu, periksa pasta/pad panas dan baterai. Panas saat idle sering tanda korsleng atau baterai rusak.",
};

const SEVERITY_WEIGHT = { info: 0, warn: 1.2, fail: 3.0 };

// ---------------------------------------------------------------------------
// Parser (fungsi murni)
// ---------------------------------------------------------------------------

const toInt = (v) => {
  if (v == null) return null;
  const s = String(v).trim();
  return /^[+-]?\d+$/.test(s) ? parseInt(s, 10) : null;
};

const escRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

function kv(text, key) {
  const m = new RegExp(`^\\s*${escRe(key)}:\\s*(.+?)\\s*$`, "im").exec(text || "");
  return m ? m[1] : null;
}

function kvBool(text, key) {
  const v = kv(text, key);
  return v == null ? null : v.toLowerCase() === "true";
}

export function parseBattery(dumpsysBattery, sysfs = "") {
  const sys = {};
  for (const line of (sysfs || "").split("\n")) {
    const i = line.indexOf("=");
    if (i >= 0) sys[line.slice(0, i).trim()] = toInt(line.slice(i + 1));
  }
  const temp = toInt(kv(dumpsysBattery, "temperature"));
  return {
    present: kvBool(dumpsysBattery, "present"),
    health_code: toInt(kv(dumpsysBattery, "health")),
    status_code: toInt(kv(dumpsysBattery, "status")),
    level: toInt(kv(dumpsysBattery, "level")),
    temp_c: temp != null ? temp / 10 : null,
    voltage_mv: toInt(kv(dumpsysBattery, "voltage")),
    ac: kvBool(dumpsysBattery, "AC powered"),
    usb: kvBool(dumpsysBattery, "USB powered"),
    wireless: kvBool(dumpsysBattery, "Wireless powered"),
    cycle_count: sys.cycle_count ?? null,
    charge_full: sys.charge_full ?? null,
    charge_full_design: sys.charge_full_design ?? null,
  };
}

export function parseStorage(lifeText, diskstats, dfText = "") {
  const lives = [];
  for (const tok of (lifeText || "").match(/0x[0-9a-fA-F]+|\b[0-9a-fA-F]{1,2}\b/g) || []) {
    const n = parseInt(tok, 16);
    if (Number.isFinite(n) && n >= 1 && n <= 11) lives.push(n);
  }
  let latency = null;
  const lm = /Latency:\s*(\d+)\s*ms\s*\[512B Data Write\]/i.exec(diskstats || "");
  if (lm) latency = parseInt(lm[1], 10);
  let free = null;
  const fm = /Data-Free:.*?=\s*(\d+)%\s*free/i.exec(diskstats || "");
  if (fm) free = parseInt(fm[1], 10);
  else if (dfText && dfText.trim()) {
    const last = dfText.trim().split("\n").pop().trim().split(/\s+/);
    const total = parseFloat(last[1]), used = parseFloat(last[2]);
    if (total > 0) free = Math.round(100 - (used / total) * 100);
  }
  return { life: lives.length ? Math.max(...lives) : null, write_latency_ms: latency, free_percent: free };
}

const ABNORMAL_BOOT = ["kernel_panic", "panic", "watchdog", "wdt", "hard_reset", "hw_reset", "pmic",
  "undervoltage", "brownout", "shutdown,thermal", "thermal", "shutdown,battery", "power_loss", "cold"];
const POWER_BOOT = ["pmic", "undervoltage", "brownout", "shutdown,battery", "power_loss", "cold"];
const DROPBOX_TAGS = ["system_server_watchdog", "system_server_crash", "system_tombstone",
  "system_last_kmsg", "system_fsck", "system_restart", "system_boot"];

export function parseBoot(history, currentReason, dropbox) {
  const lines = (history || "").split("\n").map((l) => l.trim().toLowerCase()).filter(Boolean);
  if (currentReason && currentReason.trim()) lines.push(currentReason.trim().toLowerCase());
  const has = (l, keys) => keys.some((k) => l.includes(k));
  const counts = {};
  for (const tag of DROPBOX_TAGS) counts[tag] = ((dropbox || "").match(new RegExp(tag, "gi")) || []).length;
  return {
    history_count: lines.length,
    abnormal: lines.filter((l) => has(l, ABNORMAL_BOOT)).length,
    power: lines.filter((l) => has(l, POWER_BOOT)).length,
    kernel: lines.filter((l) => l.includes("panic") || l.includes("watchdog") || l.includes("wdt")).length,
    dropbox: counts,
  };
}

export function parseThermal(zonesText, thermalservice) {
  const zones = {};
  for (const line of (zonesText || "").split("\n")) {
    const i = line.indexOf("=");
    if (i < 0) continue;
    let v = parseFloat(line.slice(i + 1).trim());
    if (!Number.isFinite(v) || !/^[+-]?\d+(\.\d+)?$/.test(line.slice(i + 1).trim())) continue;
    if (Math.abs(v) >= 1000) v /= 1000;
    if (v >= -20 && v <= 150) zones[line.slice(0, i).trim() || "zone"] = v;
  }
  const re = /mValue=([\-\d.]+),\s*mType=\d+,\s*mName=([^,}]+)/g;
  let m;
  while ((m = re.exec(thermalservice || ""))) {
    const v = parseFloat(m[1]);
    const name = m[2].trim();
    if (v >= -20 && v <= 150) zones[name] = Math.max(v, zones[name] ?? v);
  }
  const sm = /Thermal Status:\s*(\d+)/.exec(thermalservice || "");
  const vals = Object.values(zones);
  return { zones, max_c: vals.length ? Math.max(...vals) : null, status: sm ? parseInt(sm[1], 10) : null };
}

export function parseInputDevices(getevent) {
  const devices = [];
  const blocks = (getevent || "").split(/^add device \d+:\s*/m);
  for (const block of blocks.slice(1)) {
    const path = block.split("\n")[0].trim();
    const name = /name:\s*"([^"]*)"/.exec(block);
    const xm = /ABS_MT_POSITION_X\s*:.*?max\s+(\d+)/.exec(block) || /\bABS_X\s*:.*?max\s+(\d+)/.exec(block);
    const ym = /ABS_MT_POSITION_Y\s*:.*?max\s+(\d+)/.exec(block) || /\bABS_Y\s*:.*?max\s+(\d+)/.exec(block);
    if (xm && ym) devices.push({ path, name: name ? name[1] : "", x_max: parseInt(xm[1], 10), y_max: parseInt(ym[1], 10) });
  }
  return devices;
}

const TOUCH_NAME_HINT = /ts|touch|fts|goodix|synaptics|focaltech|himax|nvt|novatek|gt9|atmel|elan|sec_/i;

export function pickTouchscreen(devices) {
  if (!devices.length) return null;
  const hinted = devices.filter((d) => TOUCH_NAME_HINT.test(d.name || ""));
  const pool = hinted.length ? hinted : devices;
  return pool.reduce((a, b) => (b.x_max * b.y_max > a.x_max * a.y_max ? b : a));
}

// Posisi dicatat saat SYN_REPORT dan dipisah per jari (ABS_MT_SLOT).
export function touchCoverage(eventsText, xMax, yMax, cols = 6, rows = 10) {
  const text = eventsText || "";
  const hasSyn = text.includes("SYN_REPORT");
  const absRe = /ABS_(MT_POSITION_|MT_SLOT|)([XY]?)\s+([0-9a-fA-F]+)/;
  const visited = new Set();
  let points = 0;
  let slot = 0;
  const pos = {};
  let dirty = {};

  const commit = (sl) => {
    const [x, y] = pos[sl] || [null, null];
    if (x == null || y == null) return;
    const cx = Math.min(cols - 1, Math.max(0, Math.trunc((x / (xMax + 1)) * cols)));
    const cy = Math.min(rows - 1, Math.max(0, Math.trunc((y / (yMax + 1)) * rows)));
    visited.add(`${cx},${cy}`);
    points += 1;
  };

  for (const line of text.split("\n")) {
    if (line.includes("SYN_REPORT")) {
      for (const sl of Object.keys(dirty)) if (dirty[sl].size) commit(Number(sl));
      dirty = {};
      continue;
    }
    const m = absRe.exec(line);
    if (!m) continue;
    const kind = m[1], axis = m[2], raw = parseInt(m[3], 16);
    if (kind === "MT_SLOT") { slot = raw; continue; }
    if (kind === "" && line.includes("ABS_MT")) continue;
    if (axis !== "X" && axis !== "Y") continue;
    if (!pos[slot]) pos[slot] = [null, null];
    pos[slot][axis === "X" ? 0 : 1] = raw;
    if (!dirty[slot]) dirty[slot] = new Set();
    dirty[slot].add(axis);
    if (!hasSyn && dirty[slot].size === 2) { commit(slot); dirty[slot] = new Set(); }
  }
  for (const sl of Object.keys(dirty)) if (dirty[sl].size) commit(Number(sl));

  const uncovered = [];
  for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) if (!visited.has(`${c},${r}`)) uncovered.push([c, r]);
  return { cols, rows, points, coverage: visited.size / (cols * rows), uncovered };
}

export function parseModem(props, radioLog = "") {
  return {
    sim_state: (props["gsm.sim.state"] || "").trim(),
    baseband: (props["gsm.version.baseband"] || "").trim(),
    radio_unavailable: ((radioLog || "").match(/RADIO_NOT_AVAILABLE|radio not available/gi) || []).length,
  };
}

export function parseSensors(text) {
  const low = (text || "").toLowerCase();
  return {
    read: low.trim().length > 0,
    accelerometer: low.includes("accelerometer"),
    proximity: low.includes("proximity"),
    light: low.includes("light"),
    gyroscope: low.includes("gyroscope"),
  };
}

export function parseCamera(dumpsysCamera, features) {
  const m = /Number of camera devices:\s*(\d+)/.exec(dumpsysCamera || "");
  return { count: m ? parseInt(m[1], 10) : null, claimed: (features || "").includes("android.hardware.camera") };
}

export function parseSoftware(logcatCrash) {
  const t = logcatCrash || "";
  return {
    crashes: (t.match(/FATAL EXCEPTION/g) || []).length,
    anrs: (t.match(/ANR in /g) || []).length,
    core_crashes: (t.match(/Process:\s*(?:com\.android\.systemui|com\.android\.phone|system_server)/g) || []).length,
  };
}

// ---------------------------------------------------------------------------
// Penyimpul
// ---------------------------------------------------------------------------

export function analyze(facts) {
  const findings = [];
  const unreadable = [...(facts.unreadable || [])];
  const notes = [];
  const add = (code, component, severity, title, detail, weight = null) =>
    findings.push({ code, component, severity, title, detail, weight });

  const b = facts.battery || {};

  // --- baterai ---
  if (b.present === false) add("BAT_ABSENT", C.BATTERY, "fail", "Baterai tidak terdeteksi", "Sistem melaporkan baterai tidak ada.", 4.0);
  const healthNames = { 3: "Overheat", 4: "Dead", 5: "Over voltage", 6: "Unspecified failure", 7: "Cold" };
  if (b.health_code in healthNames) {
    add("BAT_HEALTH", C.BATTERY, "fail", `Kesehatan baterai: ${healthNames[b.health_code]}`,
      "Android sendiri menandai baterai bermasalah.", b.health_code === 4 || b.health_code === 6 ? 4.0 : 3.0);
  }
  const full = b.charge_full, design = b.charge_full_design;
  if (full && design && design > 0 && full / design >= 0.3 && full / design <= 1.3) {
    const wear = Math.max(0, (1 - full / design) * 100);
    if (wear >= 40) add("BAT_WEAR", C.BATTERY, "fail", `Baterai aus ${wear.toFixed(0)}%`, "Kapasitas penuh jauh di bawah kapasitas desain.", 3.5);
    else if (wear >= 25) add("BAT_WEAR", C.BATTERY, "warn", `Baterai mulai aus ${wear.toFixed(0)}%`, "Kapasitas penuh turun dari kapasitas desain.");
  }
  const cyc = b.cycle_count;
  if (cyc != null && cyc > 0) {
    if (cyc >= 1000) add("BAT_CYCLE", C.BATTERY, "fail", `${cyc} siklus charge`, "Siklus sangat tinggi; baterai lazimnya sudah aus.", 3.0);
    else if (cyc >= 700) add("BAT_CYCLE", C.BATTERY, "warn", `${cyc} siklus charge`, "Siklus tinggi; pantau kapasitas baterai.");
  }
  const t = b.temp_c;
  if (t != null) {
    if (t >= 50) {
      add("BAT_TEMP", C.BATTERY, "fail", `Suhu baterai ${t.toFixed(1)} °C`, "Terlalu panas; cek korsleng atau baterai rusak.", 3.0);
      add("BAT_TEMP_T", C.THERMAL, "warn", `Suhu baterai ${t.toFixed(1)} °C`, "Panas berlebih.");
    } else if (t >= 42) {
      add("BAT_TEMP", C.THERMAL, "warn", `Suhu baterai ${t.toFixed(1)} °C`, "Lebih hangat dari wajar.");
    }
  }
  const v = b.voltage_mv, lvl = b.level;
  if (v && lvl != null && v < 3300 && lvl > 20) {
    add("BAT_SAG", C.BATTERY, "warn", `Tegangan ${v} mV tidak cocok dengan level ${lvl}%`, "Level tinggi tapi tegangan rendah menandakan sel baterai lemah.");
  }

  // --- pengisian ---
  const powered = ["ac", "usb", "wireless"].some((k) => b[k]);
  const knownPower = ["ac", "usb", "wireless"].some((k) => b[k] != null);
  if (facts.usb_connected && knownPower && !powered) {
    add("CHG_NONE", C.CHARGE, "fail", "Tersambung USB tapi tidak ada daya masuk", "Data lewat tapi HP tidak mengisi. Coba kabel/port lain untuk memastikan.", 3.0);
  }
  if (b.status_code === 4 && powered) {
    add("CHG_BLOCKED", C.CHARGE, "warn", "Status 'Not charging' padahal terhubung daya", "Pengisian diblokir; bisa karena suhu, baterai, atau IC pengisian.");
  }

  // --- penyimpanan ---
  const s = facts.storage || {};
  if (s.life != null) {
    if (s.life >= 10) add("STO_LIFE", C.STORAGE, "fail", `Umur flash hampir habis (tingkat ${s.life}/11)`, "Estimasi umur eMMC/UFS 90% terpakai atau lebih.", 4.0);
    else if (s.life >= 8) add("STO_LIFE", C.STORAGE, "warn", `Umur flash menurun (tingkat ${s.life}/11)`, "Estimasi 70-80% terpakai.");
  }
  if (s.write_latency_ms != null) {
    if (s.write_latency_ms >= 500) add("STO_SLOW", C.STORAGE, "fail", `Tulis ke storage sangat lambat (${s.write_latency_ms} ms)`, "Latensi tulis 512B sangat tinggi.", 3.0);
    else if (s.write_latency_ms >= 100) add("STO_SLOW", C.STORAGE, "warn", `Tulis ke storage lambat (${s.write_latency_ms} ms)`, "Latensi tulis 512B di atas normal.");
  }
  if (s.free_percent != null && s.free_percent <= 3) {
    add("STO_FULL", C.SOFTWARE, "warn", `Penyimpanan hampir penuh (${s.free_percent}% bebas)`, "Penyimpanan penuh membuat HP lambat dan error; belum tentu rusak.");
  }

  // --- restart sendiri / catu daya ---
  const bt = facts.boot || {};
  const dbx = bt.dropbox || {};
  if ((bt.kernel || 0) >= 1 || (dbx.system_last_kmsg || 0) >= 1) {
    const n = Math.max(bt.kernel || 0, dbx.system_last_kmsg || 0);
    add("BOOT_PANIC", C.BOARD, "fail", `Jejak kernel panic/watchdog (${n}x)`, "HP pernah restart karena kernel crash atau watchdog.", n >= 2 ? 3.5 : 3.0);
  }
  if ((bt.power || 0) >= 1) {
    add("BOOT_POWER", C.BOARD, bt.power >= 3 ? "fail" : "warn", `Restart karena daya (${bt.power}x)`, "Alasan boot menunjukkan tegangan jatuh atau daya terputus mendadak.");
    add("BOOT_POWER_B", C.BATTERY, "warn", "Restart karena daya", "Baterai lemah ikut dicurigai.");
  }
  if ((bt.abnormal || 0) >= 4) add("BOOT_MANY", C.BOARD, "fail", `${bt.abnormal} restart tidak normal`, "Restart sendiri berulang.", 3.0);
  else if ((bt.abnormal || 0) >= 2) add("BOOT_MANY", C.BOARD, "warn", `${bt.abnormal} restart tidak normal`, "Restart sendiri lebih dari sekali.");
  if ((dbx.system_server_watchdog || 0) >= 1) add("SYS_WDT", C.SOFTWARE, "warn", `Watchdog system_server (${dbx.system_server_watchdog}x)`, "Sistem Android pernah macet dan dimatikan watchdog.");
  if ((dbx.system_fsck || 0) >= 1) add("FS_FSCK", C.STORAGE, "warn", "Pemeriksaan sistem file (fsck) pernah jalan", "Biasanya karena mati mendadak atau sektor storage bermasalah.");
  if ((dbx.system_tombstone || 0) >= 8) add("TOMBSTONES", C.SOFTWARE, "warn", `${dbx.system_tombstone} crash native`, "Banyak crash tingkat sistem.");

  // --- panas ---
  const th = facts.thermal || {};
  const mx = th.max_c;
  if (mx != null) {
    if (mx >= 85) {
      add("THERMAL_MAX", C.THERMAL, "fail", `Suhu internal ${mx.toFixed(0)} °C`, "Terlalu panas saat diperiksa.", 3.0);
      add("THERMAL_BOARD", C.BOARD, "warn", `Suhu internal ${mx.toFixed(0)} °C`, "Panas ekstrem sering berasal dari korsleng di board.");
    } else if (mx >= 70) {
      add("THERMAL_MAX", C.THERMAL, "warn", `Suhu internal ${mx.toFixed(0)} °C`, "Lebih panas dari wajar untuk kondisi diam.");
    }
  }
  if (th.status != null && th.status >= 3) add("THERMAL_STATUS", C.THERMAL, "warn", `Status thermal ${th.status}`, "Sistem sedang membatasi performa karena panas.");

  // --- touch ---
  const inp = facts.input || {};
  if (inp.touch_found === false) add("TOUCH_NONE", C.TOUCH, "fail", "Panel sentuh tidak terdeteksi", "Tidak ada perangkat input sentuh di sistem.", 3.5);
  const tc = facts.touch_test;
  if (tc) {
    const cov = tc.coverage || 0;
    const unc = tc.uncovered || [];
    if (cov < 0.7) {
      notes.push(`Uji sentuh: sapuan baru menutup ${(cov * 100).toFixed(0)}% layar. Ulangi dengan menyapu seluruh layar.`);
    } else if (unc.length) {
      const cells = unc.slice(0, 8).map(([c, r]) => `(${c + 1},${r + 1})`).join(", ");
      const fail = unc.length >= 4;
      add("TOUCH_DEAD", C.TOUCH, fail ? "fail" : "warn", `${unc.length} area layar tidak merespons`,
        `Sel kolom,baris: ${cells}. Pastikan layar bersih dan tidak ada pelindung rusak.`, fail ? 3.5 : null);
    }
  }

  // --- modem ---
  const m = facts.modem || {};
  const sim = (m.sim_state || "").toUpperCase();
  const simPresent = sim && !["ABSENT", "UNKNOWN", "NOT_READY"].includes(sim);
  const base = (m.baseband || "").toLowerCase();
  if (simPresent && (!base || base === "unknown")) add("MODEM_BASEBAND", C.MODEM, "fail", "Baseband tidak terbaca padahal ada SIM", "Modem tidak melapor; cek IC modem atau baseband/IMEI.", 3.5);
  if ((m.radio_unavailable || 0) >= 3) add("MODEM_RADIO", C.MODEM, "warn", `Radio tidak tersedia (${m.radio_unavailable}x di log)`, "Lapisan radio sering gagal.");
  if (sim === "NOT_READY") add("MODEM_SIM", C.MODEM, "warn", "SIM belum siap", "Bisa SIM tray/SIM rusak atau modem bermasalah.");

  // --- sensor ---
  const se = facts.sensors || {};
  if (se.read) {
    if (!se.accelerometer) add("SENSOR_ACC", C.SENSOR, "warn", "Accelerometer tidak terdaftar", "Hampir semua HP punya accelerometer.");
    if (!se.proximity) add("SENSOR_PROX", C.SENSOR, "info", "Sensor proximity tidak terdaftar", "Bisa memang tidak ada di HP entry-level; layar bisa tetap menyala saat telepon.");
  }

  // --- kamera ---
  const c = facts.camera || {};
  if (c.claimed && c.count === 0) add("CAM_NONE", C.CAMERA, "fail", "Tidak ada kamera terdeteksi", "HP mengaku punya kamera tapi sistem tidak menemukan satu pun.", 3.0);

  // --- software ---
  const sw = facts.software || {};
  if ((sw.core_crashes || 0) >= 3) add("SW_CORE", C.SOFTWARE, "warn", `Komponen inti crash ${sw.core_crashes}x`, "SystemUI/telepon/system_server berulang crash.");
  if ((sw.crashes || 0) + (sw.anrs || 0) >= 15) add("SW_MANY", C.SOFTWARE, "warn", `${sw.crashes || 0} crash, ${sw.anrs || 0} ANR`, "Banyak crash aplikasi/sistem di log.");

  // --- ringkasan ---
  const weightOf = (f) => (f.weight == null ? SEVERITY_WEIGHT[f.severity] : f.weight);
  const scores = {};
  const reasons = {};
  for (const f of findings) {
    const w = weightOf(f);
    if (w <= 0) continue;
    scores[f.component] = (scores[f.component] || 0) + w;
    (reasons[f.component] ||= []).push(f.title);
  }
  const suspects = Object.entries(scores)
    .sort((a, b) => b[1] - a[1])
    .map(([component, sc]) => {
      const confidence = 1 - Math.exp(-sc / 3.0);
      const level = confidence >= 0.7 ? "Tinggi" : confidence >= 0.4 ? "Sedang" : "Rendah";
      return { component, confidence: Math.round(confidence * 100) / 100, level, reasons: reasons[component], action: ACTIONS[component] };
    });

  const penalty = findings.reduce((a, f) => a + weightOf(f), 0);
  const score = Math.max(0, Math.min(100, Math.floor(100 - penalty * 5 + 0.5)));
  let verdict;
  if (!findings.length) verdict = "Tidak ada tanda kerusakan yang terbaca";
  else if (suspects.length && suspects[0].level === "Tinggi") verdict = `Kemungkinan besar bermasalah di: ${suspects[0].component}`;
  else if (suspects.length) verdict = `Ada tanda masalah, dugaan utama: ${suspects[0].component}`;
  else verdict = "Hanya catatan informasi";

  const totalProbes = Math.max(1, Number(facts.probe_count || 0));
  if (unreadable.length && unreadable.length / totalProbes >= 0.6) {
    notes.push("Banyak data tidak terbaca (batas izin atau versi Android), jadi kesimpulan kurang lengkap.");
  }
  notes.push("Hasil berupa petunjuk. Kerusakan fisik, cairan, dan board yang tidak menimbulkan gejala di software tidak terbaca lewat ADB.");

  return { score, verdict, suspects, findings, unreadable, notes };
}
