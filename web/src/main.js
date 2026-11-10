import "./style.css";
import { assess } from "./health.js";
import { addSnap, listSnaps } from "./store.js";
import { startLive } from "./live.js";
import { buildReport, cmpTable } from "./report.js";
import { renderTriase } from "./triase.js";
import { Adb, adbDaemonAuthenticate } from "@yume-chan/adb";
import { AdbDaemonWebUsbDeviceManager } from "@yume-chan/adb-daemon-webusb";
import { AdbWebCryptoCredentialManager, TangoLocalStorage } from "@yume-chan/adb-credential-web";
import { renderRepair } from "./repair.js";
import { attachPkgPicker } from "./picker.js";
import { renderMirror, stopMirror, closeMirrorSync, prefetchServer } from "./mirror.js";
import { renderManualTests } from "./manual-tests.js";
import { renderBattery } from "./battery.js";
import { renderComponents } from "./components.js";
import { renderStorage } from "./storage.js";
import { renderService } from "./service.js";
import { renderAnalyzer } from "./analyze.js";
import { renderTransfer, extendMirror } from "./transfer.js";

// PWA: daftarkan service worker hanya di build produksi
if ("serviceWorker" in navigator && import.meta.env.PROD) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  });
}

// ---------------------------------------------------------------
// State & helpers
// ---------------------------------------------------------------
let adb = null;
let device = null;
let deviceId = "";
let connecting = false;
let currentPage = "dashboard";
let stopLive = () => {};

const ADB_KEY_STORAGE = "nexa-service-web-adb-key";
const CONNECT_TRIES = 3;

const MIRROR_HELP = `
  <details class="help" style="margin-top:12px">
    <summary><b>Layar HP tidak bisa disentuh / HP tidak terdeteksi?</b></summary>
    <p><b>HP menyala tapi layar tidak bisa disentuh (USB debugging belum aktif):</b></p>
    <ol>
      <li>Colok <b>mouse USB</b> ke HP pelanggan lewat adaptor OTG. Akan muncul kursor di layar.</li>
      <li>Buka Pengaturan, Tentang ponsel, ketuk <b>Build number</b> 7 kali, lalu Opsi pengembang dan aktifkan <b>USB debugging</b>.</li>
      <li>Cabut mouse, colok kabel dari HP ini ke HP pelanggan, tekan <b>Hubungkan HP (USB)</b>.</li>
      <li>Di HP pelanggan, ketuk <b>Izinkan</b> pada dialog debugging (pakai mouse), lalu tekan <b>Mulai</b> di sini.</li>
    </ol>
    <p><b>Layar mati total atau pecah:</b> kalau USB debugging sudah pernah diizinkan, mirror tetap bisa menampilkan layarnya. Kalau belum, ADB tidak bisa jalan; coba layar eksternal lewat USB-C ke HDMI (hanya HP yang mendukung) sambil memakai mouse.</p>
    <p><b>HP tidak bisa menyala:</b> alat ini tidak bisa membantu karena ADB butuh Android yang sudah berjalan. Cek charger, kabel, baterai, dan kerusakan hardware.</p>
    <p><b>HP terkunci:</b> minta pemilik membukanya sendiri. Alat ini tidak membuka kunci layar atau akun.</p>
  </details>`;

const $ = (sel) => document.querySelector(sel);
const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const PAGES = [
  ["dashboard", "Dashboard"],
  ["info", "Info Device"],
  ["hardware", "Hardware Test"],
  ["battery", "Baterai"],
  ["components", "Uji Komponen"],
  ["storage", "Penyimpanan"],
  ["security", "Security"],
  ["apps", "Aplikasi"],
  ["files", "File"],
  ["repair", "Perbaikan"],
  ["service", "Servis & Laporan"],
  ["mirror", "Mirror"],
  ["terminal", "Terminal & Log"],
  ["triase", "Triase HP"],
];

async function sh(cmd) {
  if (!adb) throw new Error("Device belum terhubung.");
  try {
    return (await adb.subprocess.noneProtocol.spawn(cmd).wait().toString()).trim();
  } catch (e) {
    return "";
  }
}
// Seperti sh(), tapi MELEMPAR error kalau koneksi/pengiriman perintah gagal (sh() menelannya
// dan mengembalikan ""). Dipakai pemeriksaan yang tidak boleh menampilkan PASS palsu.
async function shx(cmd) {
  if (!adb) throw new Error("Device belum terhubung.");
  return (await adb.subprocess.noneProtocol.spawn(cmd).wait().toString()).trim();
}
// Kutip tunggal: aman untuk karakter apa pun ($, `, ;, spasi, dll.) di sh.
const sq = (v) => `'${String(v).replace(/'/g, `'\\''`)}'`;
const PKG_NAME_RE = /^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+$/;
async function shBytes(cmd) {
  return adb.subprocess.noneProtocol.spawn(cmd).wait();
}
const prop = (k) => sh(`getprop ${k}`);
// ID HP untuk riwayat, hasil uji, dan tiket servis (sama dengan yang dipakai Dashboard).
const getId = () => (adb ? deviceId : "");
// Simpan fungsi pembersih halaman hanya kalau halamannya masih yang aktif.
const keep = (page, cleanup) => {
  if (currentPage === page) stopLive = cleanup || (() => {});
  else if (cleanup) cleanup();
};

function statusClass(s) {
  return { PASS: "pass", WARN: "warn", FAIL: "fail", INFO: "info" }[s] || "info";
}

// Tutup sesi dengan rapi saat tab ditutup/di-refresh supaya HP tidak menggantung
// pada sesi lama (penyebab koneksi berikutnya lambat atau gagal).
window.addEventListener("pagehide", () => {
  closeMirrorSync();
  try { adb?.close(); } catch {}
});

// ---------------------------------------------------------------
// Layout
// ---------------------------------------------------------------
$("#app").innerHTML = `
  <div class="app">
    <aside>
      <div class="brand">Nexa Service Tool<small>Versi web</small></div>
      <nav id="nav"></nav>
    </aside>
    <div class="col">
      <div class="top">
        <div class="mbrand">Nexa Service Tool</div>
        <div id="conn" class="chip"><span class="led"></span><span id="connText">Belum terhubung</span></div>
        <button id="btnConnect" class="primary">Hubungkan HP (USB)</button>
        <button id="btnDisconnect" style="display:none">Putuskan</button>
      </div>
      <main id="view"></main>
    </div>
    <div class="bnav" id="bnav">
      <button data-page="dashboard">Beranda</button>
      <button data-page="hardware">Diagnosa</button>
      <button class="scan" id="scan" aria-label="Jalankan semua pemeriksaan">Periksa</button>
      <button data-page="mirror">Mirror</button>
      <button data-page="terminal">Log</button>
    </div>
  </div>
`;

$("#nav").innerHTML = PAGES.map(([k, l]) => `<button data-page="${k}">${l}</button>`).join("");
$("#app").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-page]");
  if (b) go(b.dataset.page);
});
$("#scan").onclick = () => go("hardware");
$("#btnConnect").onclick = connect;
$("#btnDisconnect").onclick = disconnect;

function setConn(text, ok) {
  $("#connText").textContent = text;
  $("#conn").classList.toggle("on", ok);
  $("#btnConnect").style.display = ok ? "none" : "";
  $("#btnDisconnect").style.display = ok ? "" : "none";
  $("#btnConnect").disabled = connecting;
}

function needDevice() {
  $("#view").innerHTML = `
    <div class="empty">
      <h2>Hubungkan HP dulu</h2>
      <p>Colokkan HP lewat kabel USB, aktifkan <b>USB debugging</b>, lalu tekan <b>Hubungkan HP (USB)</b>. HP yang pernah diizinkan akan tersambung otomatis, tanpa dialog pemilih.</p>
      <p class="muted">Syarat: browser Chrome/Edge (desktop) atau Chrome Android dengan kabel OTG, halaman HTTPS.
      Kalau gagal "Access denied": di komputer jalankan <code>adb kill-server</code> (ADB server bawaan merebut koneksi USB) dan tutup aplikasi lain yang memakai ADB.</p>
      <p>HP tidak bisa menyala atau terkunci? <button data-page="triase">Buka Triase HP</button> <button data-page="service">Buka Servis &amp; Laporan</button></p>
      <div class="row"><button id="pickOther">Pilih perangkat lain</button><button id="forgetKey">Hapus kunci ADB browser ini</button></div>
      <p class="muted">Kunci ADB tersimpan di browser ini supaya HP tidak minta izin berulang. Hapus kalau perangkat ini dipinjamkan atau dipakai bersama.</p>
    </div>`;
  const po = $("#pickOther");
  if (po) po.onclick = () => connect(true);
  const fk = $("#forgetKey");
  if (fk) {
    fk.onclick = () => {
      if (!confirm("Hapus kunci ADB di browser ini? Semua HP akan meminta izin USB debugging lagi saat dihubungkan.")) return;
      try { localStorage.removeItem(ADB_KEY_STORAGE); } catch {}
      alert("Kunci ADB dihapus.");
    };
  }
}

async function go(page) {
  stopMirror();
  stopLive();
  stopLive = () => {};
  currentPage = page;
  document.querySelectorAll("#nav button, #bnav button[data-page]").forEach((b) => b.classList.toggle("active", b.dataset.page === page));
  // Servis & Laporan tetap bisa dibuka tanpa HP (riwayat tiket dan cetak laporan)
  if (!adb && page !== "triase" && page !== "service") return needDevice();
  const view = $("#view");
  view.innerHTML = `<p class="muted">Memuat…</p>`;
  try {
    await PAGE_RENDER[page](view);
  } catch (e) {
    view.innerHTML = `<div class="card"><h2 class="fail">Gagal</h2><pre>${esc(e.message || e)}</pre></div>`;
  }
}

// ---------------------------------------------------------------
// Connection
// ---------------------------------------------------------------
const usbManager = () => AdbDaemonWebUsbDeviceManager.BROWSER;

function showConnectError(e) {
  $("#view").innerHTML = `<div class="card"><h2 class="fail">Gagal terhubung</h2><pre>${esc(e?.message || e)}</pre>
    <p class="muted">Kemungkinan penyebab: sesi lama masih menggantung di HP (cabut dan colok kabel lagi), dialog izin USB debugging di HP belum disetujui,
    atau ADB server di komputer merebut koneksi USB (jalankan <code>adb kill-server</code> lalu coba lagi).</p>
    <div class="row"><button id="retry" class="primary">Coba lagi</button></div></div>`;
  const r = $("#retry");
  if (r) r.onclick = () => connect();
}

// Satu kali percobaan: buka USB lalu autentikasi. Menampilkan detik berjalan supaya jelas
// kalau lama karena menunggu dialog izin di HP.
async function openTransport(dev, label) {
  const t0 = Date.now();
  const tick = setInterval(() => {
    setConn(`${label} ${Math.round((Date.now() - t0) / 1000)} dtk (cek dialog izin di layar HP)`, false);
  }, 1000);
  try {
    const connection = await dev.connect();
    return await adbDaemonAuthenticate({
      serial: dev.serial,
      connection,
      credentialManager: new AdbWebCryptoCredentialManager(
        new TangoLocalStorage(ADB_KEY_STORAGE),
        "Nexa Service Tool Web",
      ),
    });
  } finally {
    clearInterval(tick);
  }
}

async function connectTo(dev, { silent = false } = {}) {
  if (connecting || adb) return;
  connecting = true;
  setConn("Menghubungkan\u2026", false);
  let lastErr;
  try {
    for (let i = 1; i <= CONNECT_TRIES; i++) {
      try {
        const label = i > 1 ? `Menghubungkan (percobaan ${i}/${CONNECT_TRIES})\u2026` : "Menghubungkan\u2026";
        const transport = await openTransport(dev, label);
        const mine = new Adb(transport);
        adb = mine;
        device = dev;
        transport.disconnected.then(() => {
          if (adb !== mine) return;
          adb = null;
          deviceId = "";
          stopMirror();
          setConn("Terputus", false);
          go(currentPage);
        });
        const model = await prop("ro.product.model");
        deviceId = (await prop("ro.serialno")) || dev.serial || "";
        connecting = false;
        setConn(`Terhubung: ${model || dev.serial}`, true);
        go("dashboard");
        return;
      } catch (e) {
        lastErr = e;
        if (i < CONNECT_TRIES) {
          setConn(`Gagal, mencoba lagi (${i}/${CONNECT_TRIES - 1})\u2026`, false);
          await sleep(1500);
          // handle USB lama bisa rusak setelah gagal; ambil yang baru
          try {
            const fresh = await usbManager().getDevices();
            dev = fresh.find((d) => d.serial === dev.serial) || dev;
          } catch {}
        }
      }
    }
    throw lastErr;
  } catch (e) {
    adb = null;
    deviceId = "";
    connecting = false;
    setConn("Gagal terhubung", false);
    if (!silent) showConnectError(e);
  } finally {
    connecting = false;
    $("#btnConnect").disabled = false;
  }
}

async function connect(forcePicker = false) {
  const manager = usbManager();
  if (!manager) {
    alert("Browser ini tidak mendukung WebUSB. Pakai Chrome atau Edge.");
    return;
  }
  if (connecting) return;
  try {
    // HP yang pernah diizinkan dipakai langsung (tanpa dialog pemilih) kalau hanya ada satu.
    let dev;
    if (forcePicker !== true) {
      const known = await manager.getDevices();
      if (known.length === 1) dev = known[0];
    }
    if (!dev) {
      setConn("Memilih perangkat\u2026", false);
      dev = await manager.requestDevice();
    }
    if (!dev) return setConn("Belum terhubung", false);
    await connectTo(dev);
  } catch (e) {
    adb = null;
    setConn("Gagal terhubung", false);
    showConnectError(e);
  }
}

// Sambung otomatis saat halaman dibuka atau HP dicolok ulang, hanya untuk HP yang sudah pernah diizinkan.
async function autoConnect() {
  const manager = usbManager();
  if (!manager || adb || connecting) return;
  try {
    const known = await manager.getDevices();
    if (known.length === 1) await connectTo(known[0], { silent: true });
  } catch {}
}
if (navigator.usb) {
  navigator.usb.addEventListener("connect", () => {
    if (!adb && !connecting) setTimeout(autoConnect, 1000);
  });
}

async function disconnect() {
  await stopMirror();
  try { await adb?.close(); } catch {}
  adb = null;
  deviceId = "";
  setConn("Belum terhubung", false);
  go(currentPage);
}

// ---------------------------------------------------------------
// Data collectors (pembacaan saja)
// ---------------------------------------------------------------
const BATTERY_HEALTH = { 1: "Unknown", 2: "Good", 3: "Overheat", 4: "Dead", 5: "Over voltage", 6: "Unspecified failure", 7: "Cold" };

function parseBattery(raw) {
  const g = (k) => (raw.match(new RegExp(`^\\s*${k}:\\s*(.+)$`, "m")) || [])[1]?.trim();
  return {
    level: g("level"),
    temp: g("temperature") ? Number(g("temperature")) / 10 : null,
    healthCode: Number(g("health")),
    health: BATTERY_HEALTH[Number(g("health"))] || g("health") || "?",
    powered: /(AC|USB|Wireless) powered: true/.test(raw),
    voltage: g("voltage"),
  };
}

async function parseStorage() {
  const out = await sh("df -k /data");
  const line = out.split("\n").filter(Boolean).pop() || "";
  const p = line.trim().split(/\s+/);
  const total = Number(p[1]) * 1024, used = Number(p[2]) * 1024;
  if (!total) return null;
  return { total, used, percent: Math.round((used / total) * 100) };
}

async function parseMemory() {
  const raw = await sh("cat /proc/meminfo");
  const kb = (k) => Number((raw.match(new RegExp(`^${k}:\\s+(\\d+)`, "m")) || [])[1] || 0);
  const total = kb("MemTotal") * 1024, avail = kb("MemAvailable") * 1024;
  if (!total) return null;
  return { total, avail, percentFree: (avail / total) * 100 };
}

// IMEI: bisa dibaca lewat ADB hanya di Android lama; Android 10+ biasanya memblokirnya.
async function readImei() {
  const raw = await sh("service call iphonesubinfo 1 s16 com.android.shell");
  const digits = [...raw.matchAll(/'([^']*)'/g)].map((m) => m[1]).join("").replace(/\D/g, "");
  return digits.length === 15 ? digits : null;
}

const gb = (b) => (b / 1024 ** 3).toFixed(1) + " GB";

// ---------------------------------------------------------------
// Pages
// ---------------------------------------------------------------
const PAGE_RENDER = {
  async dashboard(view) {
    const [brand, model, android, sdk, patch, serial, batRaw, storage, mem, ip] = await Promise.all([
      prop("ro.product.brand"), prop("ro.product.model"), prop("ro.build.version.release"),
      prop("ro.build.version.sdk"), prop("ro.build.version.security_patch"), prop("ro.serialno"),
      sh("dumpsys battery"), parseStorage(), parseMemory(),
      sh("ip -f inet addr show wlan0"),
    ]);
    const bat = parseBattery(batRaw);
    const wifiIp = (ip.match(/inet (\d+\.\d+\.\d+\.\d+)/) || [])[1] || "-";
    const a = assess({ bat, storage, mem, patch });
    const level = Number(bat.level) || 0;
    const id = serial || device?.serial || "";
    const snap = (tag) => ({ t: Date.now(), tag, score: a.score, level, temp: bat.temp, storage: storage?.percent ?? null, ram: mem ? Math.round(mem.percentFree) : null });
    const last = (tag) => [...listSnaps(id)].reverse().find((x) => x.tag === tag);
    addSnap(id, snap());
    const segs = Array.from({ length: 20 }, (_, i) => `<i style="--i:${i}" class="${i < Math.round(level / 5) ? "on" : ""}"></i>`).join("");
    const meta = (k, v) => `<div><dt>${k}</dt><dd>${esc(v)}</dd></div>`;
    const tiles = PAGES.map(([k, l]) => `<button data-page="${k}" class="${k === "dashboard" ? "active" : ""}">${l}</button>`).join("");
    const rowsHtml = a.reasons.length
      ? a.reasons.map((r) => `<li data-s="${r.level}"><span class="mk"></span><div>${esc(r.title)}<em>${esc(r.detail)}</em></div><span class="st">${r.level === "bad" ? "Bermasalah" : "Perlu dicek"}</span></li>`).join("")
      : `<li data-s="ok"><span class="mk"></span><div>Tidak ada kerusakan terdeteksi<em>Pemeriksaan lengkap ada di Hardware Test</em></div><span class="st">Baik</span></li>`;
    view.innerHTML = `
      <section class="readout">
        <div>
          <h1>${esc(model || "Perangkat")}</h1>
          <p>${esc(brand)}, Android ${esc(android)} (SDK ${esc(sdk)})</p>
          <div class="verdict" data-s="${a.level}"><b>${a.score}</b><span>${a.verdict}</span></div>
          <dl class="meta">
            ${meta("RAM", mem ? `${gb(mem.avail)} bebas dari ${gb(mem.total)}` : "-")}
            ${meta("Penyimpanan", storage ? `${gb(storage.used)} dari ${gb(storage.total)}` : "-")}
            ${meta("Suhu baterai", bat.temp != null ? bat.temp.toFixed(1) + " °C" : "-")}
            ${meta("Kesehatan baterai", bat.health)}
            ${meta("Security patch", patch || "-")}
            ${meta("Serial", id || "-")}
            ${meta("IP WiFi", wifiIp)}
          </dl>
        </div>
        <div class="batt"><b>${level}%</b><div class="segs" role="img" aria-label="Baterai ${level} persen">${segs}</div></div>
      </section>
      <div class="tiles">${tiles}</div>
      <div class="stats">
        <div><b>1</b><span>Perangkat terhubung</span></div>
        <div><b>Aktif</b><span>ADB</span></div>
        <div><b>${storage ? storage.percent + "%" : "-"}</b><span>Penyimpanan terpakai</span></div>
        <div><b>${a.reasons.length}</b><span>Temuan</span></div>
      </div>
      <h2>Kondisi perangkat</h2>
      <ul class="rows">${rowsHtml}</ul>
      <h2 class="gap">Pantauan langsung</h2>
      <div id="live" class="live"></div>
      <h2>Sebelum dan sesudah servis</h2>
      <div id="cmp" class="card"></div>
      <div class="row">
        <button id="snapBefore">Simpan sebagai Sebelum</button>
        <button id="snapAfter">Simpan sebagai Sesudah</button>
        <button id="report" class="primary">Laporan pelanggan</button>
        <button id="refresh">Refresh</button>
      </div>`;
    const drawCmp = () => {
      const b = last("before"), f = last("after");
      $("#cmp").innerHTML = b || f ? cmpTable(b, f) : `<p class="muted">Belum ada. Simpan kondisi sebelum servis, lalu sesudahnya untuk dibandingkan. Data tersimpan di browser ini saja.</p>`;
    };
    drawCmp();
    $("#snapBefore").onclick = () => { addSnap(id, snap("before")); drawCmp(); };
    $("#snapAfter").onclick = () => { addSnap(id, snap("after")); drawCmp(); };
    $("#report").onclick = () => {
      let shop = "";
      try { shop = localStorage.getItem("nexa-shop") ?? ""; } catch {}
      if (!shop) {
        shop = prompt("Nama toko untuk laporan (boleh kosong)") || "";
        try { localStorage.setItem("nexa-shop", shop); } catch {}
      }
      const rows = [
        ["Merek dan model", `${brand} ${model}`], ["Android", `${android} (SDK ${sdk})`],
        ["Baterai", `${level}%, ${bat.health}`], ["Suhu baterai", bat.temp != null ? bat.temp.toFixed(1) + " °C" : "-"],
        ["Penyimpanan", storage ? `${gb(storage.used)} dari ${gb(storage.total)} (${storage.percent}%)` : "-"],
        ["RAM", mem ? `${gb(mem.avail)} bebas dari ${gb(mem.total)}` : "-"],
        ["Security patch", patch || "-"], ["Serial", id || "-"],
      ];
      const html = buildReport({ shop, rows, a, before: last("before"), after: last("after") });
      window.open(URL.createObjectURL(new Blob([html], { type: "text/html" })), "_blank");
    };
    $("#refresh").onclick = () => go("dashboard");
    stopLive = startLive($("#live"), async () => parseBattery(await sh("dumpsys battery")));
  },

  triase(view) {
    renderTriase(view, { go });
  },

  async info(view) {
    const [raw, imei] = await Promise.all([sh("getprop"), readImei()]);
    const rows = [...raw.matchAll(/^\[(.+?)\]: \[(.*)\]$/gm)].map((m) => [m[1], m[2]]);
    view.innerHTML = `
      <div class="card"><h2>IMEI</h2>
        ${imei
          ? `<p><b>${esc(imei)}</b></p>`
          : `<p class="muted">IMEI tidak bisa dibaca lewat ADB di HP ini (Android 10 ke atas memblokirnya). Tekan <b>*#06#</b> di aplikasi telepon HP, atau lihat di Pengaturan, Tentang ponsel.</p>`}
      </div>
      <div class="card"><h2>Properti sistem (${rows.length})</h2>
        <div class="row"><input id="q" placeholder="Cari properti…" /></div>
        <table id="tbl"></table></div>`;
    const draw = (q = "") => {
      const f = q.toLowerCase();
      $("#tbl").innerHTML = rows
        .filter(([k, v]) => !f || k.toLowerCase().includes(f) || v.toLowerCase().includes(f))
        .map(([k, v]) => `<tr><td class="muted">${esc(k)}</td><td>${esc(v)}</td></tr>`).join("");
    };
    draw();
    $("#q").oninput = (e) => draw(e.target.value);
  },

  async hardware(view) {
    view.innerHTML = `<div class="row"><button id="run" class="primary">▶ Jalankan semua pemeriksaan</button></div><div class="card"><table id="res"><tr><th>Pemeriksaan</th><th>Status</th><th>Nilai</th><th>Detail</th></tr></table></div><div id="manual"></div>`;
    $("#run").onclick = runHardwareTests;
    renderManualTests($("#manual"), { sh, esc });
    await runHardwareTests();
  },

  async battery(view) {
    keep("battery", await renderBattery(view, { sh, getId }));
  },

  async components(view) {
    keep("components", await renderComponents(view, { sh, getId }));
  },

  async storage(view) {
    await renderStorage(view, { sh, getId });
  },

  async service(view) {
    keep("service", await renderService(view, { sh, getId, connected: () => !!adb }));
  },

  async security(view) {
    const [vb, locked, crypto, selinux, patch, debuggable, su, setup, prov, build] = await Promise.all([
      prop("ro.boot.verifiedbootstate"), prop("ro.boot.flash.locked"), prop("ro.crypto.state"),
      sh("getenforce"), prop("ro.build.version.security_patch"), prop("ro.debuggable"),
      sh("ls /system/bin/su /system/xbin/su /sbin/su 2>/dev/null"),
      sh("settings get secure user_setup_complete"), sh("settings get global device_provisioned"),
      prop("ro.build.tags"),
    ]);
    const age = patch ? Math.floor((Date.now() - new Date(patch).getTime()) / 86400000) : null;
    const rows = [
      ["Verified boot", vb || "-", vb === "green" ? "PASS" : vb ? "WARN" : "INFO"],
      ["Bootloader", locked === "1" ? "Terkunci" : locked === "0" ? "Terbuka" : "-", locked === "1" ? "PASS" : locked === "0" ? "WARN" : "INFO"],
      ["Enkripsi", crypto || "-", crypto === "encrypted" ? "PASS" : crypto ? "WARN" : "INFO"],
      ["SELinux", selinux || "-", selinux === "Enforcing" ? "PASS" : selinux ? "WARN" : "INFO"],
      ["Security patch", patch ? `${patch} (${age} hari lalu)` : "-", age == null ? "INFO" : age > 365 ? "WARN" : "PASS"],
      ["Build debuggable", debuggable || "-", debuggable === "1" ? "WARN" : "PASS"],
      ["Root (file su)", su ? "Ditemukan" : "Tidak ditemukan (Magisk bisa lolos)", su ? "WARN" : "INFO"],
      ["Setup wizard selesai", setup || "-", "INFO"],
      ["Device provisioned", prov || "-", "INFO"],
      ["Build tags", build || "-", "INFO"],
    ];
    view.innerHTML = `<div class="card"><h2>Security Check</h2><table>
      ${rows.map(([k, v, s]) => `<tr><td>${k}</td><td class="${statusClass(s)}">${s}</td><td>${esc(v)}</td></tr>`).join("")}
    </table></div>`;
  },

  async apps(view) {
    const [user, system] = await Promise.all([sh("pm list packages -3"), sh("pm list packages -s")]);
    const toList = (t) => t.split("\n").map((l) => l.replace("package:", "").trim()).filter(Boolean).sort();
    const u = toList(user), s = toList(system);
    view.innerHTML = `
      <div class="card"><h2>Aplikasi</h2>
        <div class="row">
          <button id="tUser" class="active">Pihak ketiga (${u.length})</button>
          <button id="tSys">Sistem (${s.length})</button>
        </div>
        <div class="row"><input id="q" placeholder="Cari paket…" /></div>
        <p class="muted">Untuk menghentikan, menonaktifkan, mencopot, atau memasang aplikasi, pakai halaman <b>Perbaikan</b>.</p>
        <table id="tbl"></table>
        <pre id="detail" style="display:none;margin-top:10px"></pre></div>`;
    let list = u;
    const draw = () => {
      const f = $("#q").value.toLowerCase();
      $("#tbl").innerHTML = list.filter((p) => p.toLowerCase().includes(f))
        .map((p) => `<tr><td>${esc(p)}</td><td><span class="link" data-pkg="${esc(p)}">detail</span></td></tr>`).join("");
    };
    $("#tUser").onclick = () => { list = u; $("#tUser").classList.add("active"); $("#tSys").classList.remove("active"); draw(); };
    $("#tSys").onclick = () => { list = s; $("#tSys").classList.add("active"); $("#tUser").classList.remove("active"); draw(); };
    $("#q").oninput = draw;
    $("#tbl").onclick = async (e) => {
      const pkg = e.target.dataset?.pkg;
      if (!pkg || !PKG_NAME_RE.test(pkg)) return;
      const d = $("#detail");
      d.style.display = "block";
      d.textContent = "Memuat…";
      const out = await sh(`dumpsys package ${pkg} | grep -E "versionName|versionCode|firstInstallTime|lastUpdateTime|installerPackageName"`);
      d.textContent = `${pkg}\n${out || "(tidak ada data)"}`;
    };
    draw();
  },

  async files(view, path = "/sdcard") {
    // /sdcard adalah symlink; tanpa garis miring di akhir, ls hanya menampilkan symlink-nya.
    // Nama folder berasal dari HP pelanggan: kutip tunggal supaya $(...) atau backtick di nama folder tidak dieksekusi.
    const out = await sh(`ls -la ${sq(path.replace(/\/$/, "") + "/")}`);
    const entries = out.split("\n").slice(1).map((l) => {
      const p = l.trim().split(/\s+/);
      if (p.length < 8) return null;
      let name = p.slice(7).join(" ");
      if (p[0].startsWith("l") && name.includes(" -> ")) name = name.split(" -> ")[0];
      return { dir: p[0].startsWith("d") || p[0].startsWith("l"), size: p[4], date: `${p[5]} ${p[6]}`, name };
    }).filter((e) => e && e.name !== "." && e.name !== "..");
    entries.sort((a, b) => Number(b.dir) - Number(a.dir) || a.name.localeCompare(b.name));
    const parent = path.replace(/\/[^/]+\/?$/, "") || "/";
    view.innerHTML = `
      <div class="card"><h2>${esc(path)}</h2>
        <p class="muted">Untuk backup folder atau mengunduh file besar, pakai halaman <b>Perbaikan</b>, bagian Penyimpanan.</p>
        <div class="row"><button id="up">⬆ Naik</button></div>
        <table>${entries.map((e) => `<tr><td>${e.dir ? "📁" : "📄"} ${e.dir ? `<span class="link" data-dir="${esc(e.name)}">${esc(e.name)}</span>` : esc(e.name)}</td><td class="muted">${e.dir ? "" : esc(e.size)}</td><td class="muted">${esc(e.date)}</td></tr>`).join("") || `<tr><td class="muted">(kosong / tidak ada izin)</td></tr>`}</table></div>
      <div id="xfer"></div>`;
    $("#up").onclick = () => PAGE_RENDER.files(view, parent);
    view.querySelectorAll("[data-dir]").forEach((el) => {
      el.onclick = () => PAGE_RENDER.files(view, path.replace(/\/$/, "") + "/" + el.dataset.dir);
    });
    renderTransfer($("#xfer"), { getAdb: () => adb, sh, dir: path });
  },

  async repair(view) {
    await renderRepair(view, { sh, getAdb: () => adb, esc });
    attachPkgPicker(view, { sh, esc });
  },

  async mirror(view) {
    renderMirror(view, { sh, getAdb: () => adb, helpHtml: MIRROR_HELP });
    extendMirror(view);
  },

  async terminal(view) {
    view.innerHTML = `
      <div id="loga"></div>
      <div class="card"><h2>Terminal ADB shell</h2>
        <p class="muted">Perintah di sini bisa mengubah HP. Konfirmasi hanya muncul untuk kata kunci tertentu, jadi periksa perintahmu sendiri.</p>
        <div class="row"><input id="cmd" placeholder="mis. getprop ro.product.model" /><button id="exec" class="primary">Jalankan</button></div>
        <div class="row">
          <button data-c="logcat -d -t 300">Logcat 300 baris</button>
          <button data-c="logcat -d -b crash -t 100">Crash log</button>
          <button data-c="dumpsys battery">Battery</button>
          <button data-c="dumpsys meminfo | head -40">Meminfo</button>
          <button data-c="df -h">Storage</button>
        </div>
        <pre id="out">(hasil muncul di sini)</pre></div>`;
    renderAnalyzer($("#loga"), { sh });
    const DANGER = /(\brm\b|\bwipe\b|\bformat\b|\bdd\b|\breboot\b|\bflash|\bmkfs|\bsetprop\b|\bpm (clear|uninstall|disable|disable-user|enable)\b|\bam force-stop\b|\bsvc\b|\bcmd package\b|\bsettings put\b)/;
    const run = async (c) => {
      if (!c.trim()) return;
      if (DANGER.test(c) && !confirm(`Perintah ini bisa mengubah/menghapus data di HP:\n\n${c}\n\nLanjutkan?`)) return;
      $("#out").textContent = "Menjalankan…";
      $("#out").textContent = (await sh(c)) || "(tidak ada output)";
    };
    $("#exec").onclick = () => run($("#cmd").value);
    $("#cmd").onkeydown = (e) => { if (e.key === "Enter") run(e.target.value); };
    view.querySelectorAll("button[data-c]").forEach((b) => (b.onclick = () => { $("#cmd").value = b.dataset.c; run(b.dataset.c); }));
  },
};

// ---------------------------------------------------------------
// Hardware tests (pembacaan saja; logika ditiru dari core/hardware_test.py)
// Uji yang butuh dirasakan/ditekan (getaran, suara, tombol) ada di manual-tests.js
// ---------------------------------------------------------------
async function runHardwareTests() {
  const tbl = $("#res");
  if (!tbl) return;
  tbl.innerHTML = `<tr><th>Pemeriksaan</th><th>Status</th><th>Nilai</th><th>Detail</th></tr>`;
  try {
    await runHardwareChecks(tbl);
  } catch (e) {
    tbl.insertAdjacentHTML("beforeend",
      `<tr><td>Pemeriksaan terhenti</td><td class="fail">FAIL</td><td>-</td><td class="muted">${esc(e?.message || e)}. Hubungkan HP lagi lalu jalankan ulang.</td></tr>`);
  }
}

async function runHardwareChecks(tbl) {
  // Di sini sh = shx: koneksi putus harus tampil sebagai kegagalan, bukan hasil "kosong = baik".
  const sh = shx;
  const prop = (k) => shx(`getprop ${k}`);
  const parseStorage = async () => {
    const out = await shx("df -k /data");
    const line = out.split("\n").filter(Boolean).pop() || "";
    const p = line.trim().split(/\s+/);
    const total = Number(p[1]) * 1024, used = Number(p[2]) * 1024;
    return total ? { total, used, percent: Math.round((used / total) * 100) } : null;
  };
  const parseMemory = async () => {
    const raw = await shx("cat /proc/meminfo");
    const kb = (k) => Number((raw.match(new RegExp(`^${k}:\\s+(\\d+)`, "m")) || [])[1] || 0);
    const total = kb("MemTotal") * 1024, avail = kb("MemAvailable") * 1024;
    return total ? { total, avail, percentFree: (avail / total) * 100 } : null;
  };
  const features = await sh("pm list features");
  const hasFeature = (f) => features.includes(f);
  const add = (name, status, value, detail) => {
    tbl.insertAdjacentHTML("beforeend",
      `<tr><td>${esc(name)}</td><td class="${statusClass(status)}">${status}</td><td>${esc(value)}</td><td class="muted">${esc(detail)}</td></tr>`);
  };

  const bat = parseBattery(await sh("dumpsys battery"));
  if (bat.healthCode === 2) add("Battery health", "PASS", bat.health, "Kondisi baterai baik.");
  else if (bat.healthCode === 1) add("Battery health", "INFO", bat.health, "Status tidak diketahui.");
  else if (bat.healthCode === 7) add("Battery health", "WARN", bat.health, "Baterai terlalu dingin; ukur ulang setelah suhunya normal.");
  else if (bat.healthCode) add("Battery health", "FAIL", bat.health, "Indikasi masalah fisik baterai.");
  else add("Battery health", "INFO", "-", "Data tidak tersedia.");

  if (bat.temp != null) {
    add("Suhu baterai", bat.temp >= 50 ? "FAIL" : bat.temp >= 42 ? "WARN" : "PASS", `${bat.temp.toFixed(1)} °C`, "Batas wajar < 42 °C.");
  }

  const thermal = await sh("dumpsys thermalservice");
  if (!thermal) add("Thermal", "INFO", "No data", "Thermal service tidak mengembalikan data.");
  else {
    const m = thermal.match(/mStatus\s*=\s*(\d+)/);
    const code = m ? Number(m[1]) : null;
    const low = thermal.toLowerCase();
    if (low.includes("shutdown") || low.includes("emergency") || (code != null && code >= 6)) add("Thermal", "FAIL", "Critical", "Device pernah/sedang thermal shutdown.");
    else if (low.includes("severe") || low.includes("critical") || (code != null && code >= 3)) add("Thermal", "WARN", "Throttling", "Thermal throttling tingkat tinggi.");
    else add("Thermal", "PASS", "Normal", "Tidak ada indikasi throttling parah.");
  }

  const mem = await parseMemory();
  if (mem) add("RAM", mem.percentFree < 5 ? "WARN" : "PASS", `${gb(mem.avail)} bebas dari ${gb(mem.total)}`, mem.percentFree < 5 ? "RAM hampir habis." : "Penggunaan RAM wajar.");

  const st = await parseStorage();
  if (st) add("Penyimpanan", st.percent >= 95 ? "FAIL" : st.percent >= 85 ? "WARN" : "PASS", `${st.percent}% terpakai`, `${gb(st.used)} dari ${gb(st.total)}`);

  const wifi = await sh("dumpsys wifi | grep -m1 'Wi-Fi is'");
  add("WiFi radio", wifi.includes("enabled") ? "PASS" : wifi ? "WARN" : "INFO", wifi || "-", "Status radio WiFi.");

  for (const [name, feat] of [
    ["Bluetooth", "android.hardware.bluetooth"], ["GPS", "android.hardware.location.gps"], ["NFC", "android.hardware.nfc"],
    ["Fingerprint", "android.hardware.fingerprint"], ["Kamera belakang", "android.hardware.camera"], ["Kamera depan", "android.hardware.camera.front"],
    ["Accelerometer", "android.hardware.sensor.accelerometer"], ["Gyroscope", "android.hardware.sensor.gyroscope"],
    ["Proximity", "android.hardware.sensor.proximity"], ["Light sensor", "android.hardware.sensor.light"],
  ]) {
    add(name, "INFO", hasFeature(feat) ? "Ada di spesifikasi" : "Tidak tercantum", "HP mengaku punya komponen ini; belum tentu berfungsi. Uji nyata ada di Uji Komponen.");
  }

  const sim = await prop("gsm.sim.state");
  const op = await prop("gsm.operator.alpha");
  add("Modem / SIM", /READY/.test(sim) ? "PASS" : sim ? "WARN" : "INFO", `${sim || "-"} ${op ? "· " + op : ""}`, "Status registrasi SIM/jaringan.");

  const log = await sh("logcat -d -t 3000");
  if (!log) {
    // Log kosong/tidak terbaca BUKAN berarti stabil.
    add("Stabilitas software", "INFO", "-", "Logcat tidak terbaca (HP tidak memberi izin atau log kosong); stabilitas tidak bisa dinilai.");
  } else {
    const crashes = (log.match(/FATAL EXCEPTION/g) || []).length;
    const anrs = (log.match(/ANR in /g) || []).length;
    add("Stabilitas software", crashes + anrs >= 10 ? "WARN" : "PASS", `${crashes} crash, ${anrs} ANR`, "Dari 3000 baris logcat terakhir.");
  }
}

// ---------------------------------------------------------------
needDevice();
go("dashboard");
autoConnect();
// unduh server scrcpy di latar belakang supaya tombol Mulai di Mirror langsung siap
prefetchServer().catch(() => {});
