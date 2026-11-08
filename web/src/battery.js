// Halaman Baterai: kesehatan kapasitas, siklus, arus pengisian langsung, dan temuan dalam bahasa servis.
// Semua data dibaca (tidak mengubah HP). Sumbernya bisa berbeda tiap merek, jadi setiap angka
// yang tidak tersedia ditampilkan sebagai "tidak terbaca", bukan ditebak.
import { esc, num, gauge, spark, saveTest } from "./kit.js";

const STATUS = { 1: "Tidak diketahui", 2: "Mengisi", 3: "Dipakai (tidak mengisi)", 4: "Dicolok tapi tidak mengisi", 5: "Penuh" };
const HEALTH = { 1: "Tidak diketahui", 2: "Baik", 3: "Terlalu panas", 4: "Rusak", 5: "Tegangan berlebih", 6: "Gagal", 7: "Terlalu dingin" };

// "POWER_SUPPLY_CAPACITY=87" -> { CAPACITY: "87" }
export function parseUevent(text) {
  const o = {};
  for (const line of String(text || "").split("\n")) {
    const m = line.match(/^\s*(?:POWER_SUPPLY_)?([A-Za-z0-9_]+)=(.*)$/);
    if (m) o[m[1].toUpperCase()] = m[2].trim();
  }
  return o;
}

// "  level: 87" -> { level: "87" }
export function parseDump(text) {
  const o = {};
  for (const line of String(text || "").split("\n")) {
    const m = line.match(/^\s*([A-Za-z][A-Za-z ]*?):\s*(.+?)\s*$/);
    if (m) o[m[1].toLowerCase()] = m[2];
  }
  return o;
}

export function parseStats(text) {
  const t = String(text || "");
  const est = (t.match(/Estimated battery capacity:\s*([\d.]+)\s*mAh/i) || [])[1];
  const des = (t.match(/^\s*Capacity:\s*([\d.]+)/im) || [])[1];
  return { est: est ? Number(est) : null, design: des ? Number(des) : null };
}

const toVolts = (v) => (v == null ? null : v > 100000 ? v / 1e6 : v > 100 ? v / 1000 : v);
// Kebanyakan HP melaporkan mikroampere; nilai kecil dianggap sudah miliampere.
const toMa = (v) => (v == null ? null : Math.abs(v) >= 10000 ? v / 1000 : v);
const toMah = (v) => (v == null ? null : v > 100000 ? Math.round(v / 1000) : Math.round(v));
const f1 = (v, d = 1) => (v == null ? "tidak terbaca" : Number(v).toFixed(d));

export async function readBattery(sh) {
  const [dumpRaw, uevRaw, usbRaw] = await Promise.all([
    sh("dumpsys battery"),
    sh("cat /sys/class/power_supply/battery/uevent /sys/class/power_supply/bms/uevent 2>/dev/null"),
    sh("cat /sys/class/power_supply/usb/uevent 2>/dev/null"),
  ]);
  const d = parseDump(dumpRaw);
  const k = parseUevent(uevRaw);
  const u = parseUevent(usbRaw);
  const tempRaw = d.temperature != null ? num(d.temperature) : num(k.TEMP);
  const maxA = num(d["max charging current"]) ?? num(u.CURRENT_MAX);
  const maxV = num(d["max charging voltage"]) ?? num(u.VOLTAGE_MAX);
  const isTrue = (s) => /true/i.test(s || "");
  return {
    ok: Boolean(dumpRaw),
    level: num(d.level) ?? num(k.CAPACITY),
    tempC: tempRaw == null ? null : tempRaw / 10,
    volt: toVolts(num(k.VOLTAGE_NOW) ?? num(d.voltage)),
    currentMa: toMa(num(k.CURRENT_NOW)),
    cycle: num(k.CYCLE_COUNT),
    status: num(d.status),
    healthCode: num(d.health),
    tech: d.technology || k.TECHNOLOGY || null,
    plug: { ac: isTrue(d["ac powered"]), usb: isTrue(d["usb powered"]), wireless: isTrue(d["wireless powered"]) },
    maxMa: maxA == null ? null : toMa(maxA),
    maxV: maxV == null ? null : toVolts(maxV),
    counter: num(d["charge counter"]),
    full: num(k.CHARGE_FULL),
    design: num(k.CHARGE_FULL_DESIGN),
  };
}

// Urutan sumber, dari yang paling dipercaya.
export function capacityHealth(b, stats = {}) {
  const ok = (p) => Number.isFinite(p) && p > 0 && p <= 115;
  const pack = (p, src, fullMah, designMah) => ({ pct: Math.min(100, Math.round(p)), src, fullMah, designMah });
  if (b.full && b.design) {
    const p = (b.full / b.design) * 100;
    if (ok(p)) return pack(p, "Dibaca dari sensor baterai (kapasitas penuh dibanding desain).", toMah(b.full), toMah(b.design));
  }
  if (stats.est && stats.design) {
    const p = (stats.est / stats.design) * 100;
    if (ok(p)) return pack(p, "Estimasi Android dari riwayat pengisian (batterystats).", Math.round(stats.est), Math.round(stats.design));
  }
  if (b.counter && b.level >= 30 && stats.design) {
    const full = b.counter / 1000 / (b.level / 100);
    const p = (full / stats.design) * 100;
    if (ok(p)) return pack(p, "Perkiraan kasar dari charge counter. Kurang akurat, ulangi saat baterai 60% ke atas.", Math.round(full), Math.round(stats.design));
  }
  return null;
}

export function verdictText(pct) {
  if (pct >= 85) return "Baik. Belum perlu ganti.";
  if (pct >= 70) return "Mulai menurun, masih layak pakai.";
  if (pct >= 50) return "Menurun jauh. Disarankan ganti.";
  return "Sangat rendah. Ganti baterai.";
}

export function judge(b, cap) {
  const rows = [];
  const add = (level, title, detail) => rows.push({ level, title, detail });
  if (cap) {
    if (cap.pct >= 85) add("ok", `Kapasitas baik (${cap.pct}%)`, "Baterai masih mendekati kapasitas awal.");
    else if (cap.pct >= 70) add("warn", `Kapasitas mulai menurun (${cap.pct}%)`, "Masih layak, tapi daya tahan berkurang. Pantau lagi beberapa bulan.");
    else if (cap.pct >= 50) add("bad", `Kapasitas turun jauh (${cap.pct}%)`, "Ganti baterai kalau pelanggan mengeluh cepat habis atau HP mati mendadak.");
    else add("bad", `Kapasitas sangat rendah (${cap.pct}%)`, "Ganti baterai. Baterai selemah ini bisa membuat HP restart sendiri.");
  } else {
    add("info", "Kapasitas tidak terbaca", "HP ini tidak membuka data kapasitas lewat ADB. Ukur dengan alat uji baterai atau menu servis bawaan merek.");
  }
  if (b.cycle != null) {
    if (b.cycle < 300) add("ok", `Siklus pengisian ${b.cycle}`, "Masih rendah.");
    else if (b.cycle <= 600) add("warn", `Siklus pengisian ${b.cycle}`, "Sudah banyak. Kapasitas biasanya mulai turun di rentang ini.");
    else add("bad", `Siklus pengisian ${b.cycle}`, "Melewati umur normal sel Li-ion.");
  }
  if (b.tempC != null) {
    if (b.tempC >= 45) add("bad", `Suhu ${f1(b.tempC)} °C`, "Terlalu panas. Cek charger, aplikasi yang boros, atau sel yang kembung.");
    else if (b.tempC >= 40) add("warn", `Suhu ${f1(b.tempC)} °C`, "Agak hangat. Ukur ulang saat HP dingin.");
  }
  if (b.healthCode != null && b.healthCode !== 2) {
    add(b.healthCode === 1 ? "info" : "bad", `Android melaporkan: ${HEALTH[b.healthCode] || b.healthCode}`, "Status kesehatan dari sistem, di luar angka kapasitas.");
  }
  if (b.volt != null && b.level != null && b.volt < 3.6 && b.level > 20) {
    add("bad", `Tegangan ${f1(b.volt, 2)} V terlalu rendah untuk level ${b.level}%`, "Tanda sel lemah. Biasanya HP mati mendadak saat dipakai berat.");
  }
  const plugged = b.plug.ac || b.plug.usb || b.plug.wireless;
  if (plugged && (b.status === 3 || b.status === 4)) {
    add("warn", "Dicolok tapi tidak mengisi", "Coba kabel dan charger lain. Kalau tetap, periksa port pengisian atau IC charging.");
  } else if (plugged && b.status === 2 && b.currentMa != null && Math.abs(b.currentMa) < 150 && (b.level ?? 0) < 95) {
    add("warn", `Arus pengisian kecil (${f1(Math.abs(b.currentMa), 0)} mA)`, "Mungkin charger lemah, kabel buruk, atau port kotor.");
  }
  const status = rows.some((r) => r.level === "bad") ? "FAIL" : rows.some((r) => r.level === "warn") ? "WARN" : rows.some((r) => r.level === "ok") ? "PASS" : "INFO";
  return { rows, status };
}

const plugText = (p) => [p.ac && "AC", p.usb && "USB", p.wireless && "Nirkabel"].filter(Boolean).join(", ") || "Tidak dicolok";

export async function renderBattery(view, { sh, getId }) {
  view.innerHTML = `<p class="muted">Membaca data baterai…</p>`;
  const [b, statsRaw] = await Promise.all([
    readBattery(sh),
    sh('dumpsys batterystats 2>/dev/null | grep -m12 -iE "Estimated battery capacity|^ *Capacity:"'),
  ]);
  if (!b.ok) {
    view.innerHTML = `<div class="card"><h2 class="fail">Baterai tidak terbaca</h2><p>HP tidak menjawab perintah <code>dumpsys battery</code>. Cabut dan colok kabel USB, lalu buka halaman ini lagi.</p></div>`;
    return () => {};
  }
  const stats = parseStats(statsRaw);
  const cap = capacityHealth(b, stats);
  const { rows, status } = judge(b, cap);
  const note = [cap ? `kapasitas ${cap.pct}%` : null, b.cycle != null ? `${b.cycle} siklus` : null, b.tempC != null ? `${f1(b.tempC)} °C` : null].filter(Boolean).join(", ");
  saveTest(getId(), "battery", { name: "Baterai", status, note: note || "Data kapasitas tidak terbaca" });

  const hero = cap
    ? `<div><p class="bh-k">Kesehatan kapasitas</p><p class="bh-v">${cap.pct}<span>%</span></p>${gauge(cap.pct, { warn: 85, bad: 70 })}
        <p class="bh-s">${esc(verdictText(cap.pct))}</p><p class="bh-note">${esc(cap.src)}</p></div>`
    : `<div><p class="bh-k">Kesehatan kapasitas</p><p class="bh-v bh-na">Tidak terbaca</p>${gauge(null)}
        <p class="bh-note">HP ini tidak membuka data kapasitas lewat ADB. Cek lewat alat uji baterai atau menu servis bawaan merek.</p></div>`;
  const cell = (k, v) => `<div><dt>${k}</dt><dd>${esc(v)}</dd></div>`;
  const mah = (v) => (v == null ? "tidak terbaca" : `${v.toLocaleString("id-ID")} mAh`);

  view.innerHTML = `
    <section class="bh">${hero}
      <dl class="bh-m">
        ${cell("Kapasitas penuh sekarang", mah(cap?.fullMah))}
        ${cell("Kapasitas desain", mah(cap?.designMah ?? (stats.design ? Math.round(stats.design) : null)))}
        ${cell("Siklus pengisian", b.cycle == null ? "tidak terbaca" : String(b.cycle))}
        ${cell("Level sekarang", b.level == null ? "-" : b.level + "%")}
      </dl>
    </section>
    <h2 class="gap">Temuan</h2>
    <ul class="rows">${rows.map((r) => `<li data-s="${r.level}"><span class="mk"></span><div>${esc(r.title)}<em>${esc(r.detail)}</em></div><span class="st">${r.level === "bad" ? "Bermasalah" : r.level === "warn" ? "Perlu dicek" : r.level === "ok" ? "Baik" : "Info"}</span></li>`).join("")}</ul>
    <h2 class="gap">Pantauan langsung</h2>
    <div id="blive" class="live"></div>
    <p class="muted">Dibaca tiap 2,5 detik. Colok dan cabut charger untuk melihat perbedaannya. Tanda plus atau minus pada arus berbeda tiap merek, jadi grafik memakai nilai mutlak.</p>
    <div class="card"><h2>Data lengkap</h2><dl class="kv">
      ${cell("Tegangan", b.volt == null ? "tidak terbaca" : f1(b.volt, 2) + " V")}
      ${cell("Suhu", b.tempC == null ? "tidak terbaca" : f1(b.tempC) + " °C")}
      ${cell("Status pengisian", STATUS[b.status] || "tidak terbaca")}
      ${cell("Kesehatan menurut Android", HEALTH[b.healthCode] || "tidak terbaca")}
      ${cell("Sumber daya", plugText(b.plug))}
      ${cell("Arus maksimal charger", b.maxMa == null ? "tidak terbaca" : f1(b.maxMa, 0) + " mA")}
      ${cell("Tegangan maksimal charger", b.maxV == null ? "tidak terbaca" : f1(b.maxV, 1) + " V")}
      ${cell("Teknologi", b.tech || "tidak terbaca")}
    </dl></div>`;

  const cur = [], volt = [], temp = [], lvl = [];
  const push = (arr, v) => { if (v != null) { arr.push(v); if (arr.length > 40) arr.shift(); } };
  let dead = false;
  let timer = null;
  const draw = () => {
    const box = view.querySelector("#blive");
    if (!box || dead) return;
    box.innerHTML = spark("Arus", cur, " mA") + spark("Tegangan", volt, " V", { digits: 2 }) + spark("Suhu", temp, " °C", { digits: 1 }) + spark("Level", lvl, "%", { lo: 0, hi: 100 });
  };
  const tick = async () => {
    if (dead) return;
    try {
      const x = await readBattery(sh);
      push(cur, x.currentMa == null ? null : Math.abs(x.currentMa));
      push(volt, x.volt);
      push(temp, x.tempC);
      push(lvl, x.level);
      draw();
    } catch {}
    if (!dead) timer = setTimeout(tick, 2500);
  };
  draw();
  tick();
  return () => { dead = true; clearTimeout(timer); };
}
