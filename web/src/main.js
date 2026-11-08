import "./style.css";
import { Adb, adbDaemonAuthenticate } from "@yume-chan/adb";
import { AdbDaemonWebUsbDeviceManager } from "@yume-chan/adb-daemon-webusb";
import { AdbWebCryptoCredentialManager, TangoLocalStorage } from "@yume-chan/adb-credential-web";
import { AdbScrcpyClient, AdbScrcpyOptions5_0_1 } from "@yume-chan/adb-scrcpy";
import { DefaultServerPath } from "@yume-chan/scrcpy";
import { BitmapVideoFrameRenderer, WebCodecsVideoDecoder } from "@yume-chan/scrcpy-decoder-webcodecs";
import { renderRepair } from "./repair.js";

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
let mirrorRunning = false;
let scrcpyClient = null;
let scrcpyDecoder = null;
let currentPage = "dashboard";

const ADB_KEY_STORAGE = "nexa-service-web-adb-key";

// scrcpy-server diunduh saat build ke public/ (lihat scripts/fetch-scrcpy-server.mjs)
const SCRCPY_SERVER_URL = "/scrcpy-server.bin";

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

const PAGES = [
  ["dashboard", "Dashboard"],
  ["info", "Info Device"],
  ["hardware", "Hardware Test"],
  ["security", "Security"],
  ["apps", "Aplikasi"],
  ["files", "File"],
  ["repair", "Perbaikan"],
  ["mirror", "Mirror"],
  ["terminal", "Terminal & Log"],
];

async function sh(cmd) {
  if (!adb) throw new Error("Device belum terhubung.");
  try {
    return (await adb.subprocess.noneProtocol.spawn(cmd).wait().toString()).trim();
  } catch (e) {
    return "";
  }
}
async function shBytes(cmd) {
  return adb.subprocess.noneProtocol.spawn(cmd).wait();
}
const prop = (k) => sh(`getprop ${k}`);

function statusClass(s) {
  return { PASS: "pass", WARN: "warn", FAIL: "fail", INFO: "info" }[s] || "info";
}

async function stopMirror() {
  mirrorRunning = false;
  const client = scrcpyClient;
  const decoder = scrcpyDecoder;
  scrcpyClient = null;
  scrcpyDecoder = null;
  try { decoder?.dispose(); } catch {}
  try { await client?.close(); } catch {}
}

// ---------------------------------------------------------------
// Layout
// ---------------------------------------------------------------
$("#app").innerHTML = `
  <header>
    <h1>🛠️ Nexa <span>Service Tool</span> Web</h1>
    <span id="conn" class="badge muted">Belum terhubung</span>
    <button id="btnConnect" class="primary">Hubungkan HP (USB)</button>
    <button id="btnDisconnect" style="display:none">Putuskan</button>
  </header>
  <nav id="nav"></nav>
  <main id="view"></main>
`;

$("#nav").innerHTML = PAGES.map(([k, l]) => `<button data-page="${k}">${l}</button>`).join("");
$("#nav").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-page]");
  if (b) go(b.dataset.page);
});
$("#btnConnect").onclick = connect;
$("#btnDisconnect").onclick = disconnect;

function setConn(text, ok) {
  $("#conn").textContent = text;
  $("#conn").className = "badge " + (ok ? "pass" : "muted");
  $("#btnConnect").style.display = ok ? "none" : "";
  $("#btnDisconnect").style.display = ok ? "" : "none";
}

function needDevice() {
  $("#view").innerHTML = `
    <div class="card">
      <h2>Hubungkan HP dulu</h2>
      <p>Colokkan HP lewat kabel USB, aktifkan <b>USB debugging</b>, lalu tekan <b>Hubungkan HP (USB)</b> dan pilih perangkatnya.</p>
      <p class="muted">Syarat: browser Chrome/Edge (desktop) atau Chrome Android dengan kabel OTG, halaman HTTPS.
      Kalau gagal "Access denied": di komputer jalankan <code>adb kill-server</code> (ADB server bawaan merebut koneksi USB) dan tutup aplikasi lain yang memakai ADB.</p>
      <div class="row"><button id="forgetKey">Hapus kunci ADB browser ini</button></div>
      <p class="muted">Kunci ADB tersimpan di browser ini supaya HP tidak minta izin berulang. Hapus kalau perangkat ini dipinjamkan atau dipakai bersama.</p>
    </div>`;
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
  currentPage = page;
  document.querySelectorAll("nav button").forEach((b) => b.classList.toggle("active", b.dataset.page === page));
  if (!adb) return needDevice();
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
async function connect() {
  const manager = AdbDaemonWebUsbDeviceManager.BROWSER;
  if (!manager) {
    alert("Browser ini tidak mendukung WebUSB. Pakai Chrome atau Edge.");
    return;
  }
  try {
    setConn("Memilih perangkat…", false);
    device = await manager.requestDevice();
    if (!device) return setConn("Belum terhubung", false);

    setConn("Menghubungkan… (cek layar HP, izinkan USB debugging)", false);
    const connection = await device.connect();
    const transport = await adbDaemonAuthenticate({
      serial: device.serial,
      connection,
      credentialManager: new AdbWebCryptoCredentialManager(
        new TangoLocalStorage(ADB_KEY_STORAGE),
        "Nexa Service Tool Web",
      ),
    });
    adb = new Adb(transport);
    transport.disconnected.then(() => {
      adb = null;
      stopMirror();
      setConn("Terputus", false);
      go(currentPage);
    });

    const model = await prop("ro.product.model");
    setConn(`Terhubung: ${model || device.serial}`, true);
    go("dashboard");
  } catch (e) {
    adb = null;
    setConn("Gagal terhubung", false);
    $("#view").innerHTML = `<div class="card"><h2 class="fail">Gagal terhubung</h2><pre>${esc(e.message || e)}</pre>
      <p class="muted">Kalau pesannya soal "Access denied" / "claimInterface": jalankan <code>adb kill-server</code> di komputer lalu coba lagi.</p></div>`;
  }
}

async function disconnect() {
  await stopMirror();
  try { await adb?.close(); } catch {}
  adb = null;
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
    const stat = (k, v) => `<div class="stat"><div class="k">${k}</div><div class="v">${esc(v)}</div></div>`;
    view.innerHTML = `
      <div class="card"><h2>Perangkat</h2><div class="grid">
        ${stat("Merek / Model", `${brand} ${model}`)}
        ${stat("Android", `${android} (SDK ${sdk})`)}
        ${stat("Security patch", patch || "-")}
        ${stat("Serial", serial || device?.serial || "-")}
      </div></div>
      <div class="card"><h2>Kondisi</h2><div class="grid">
        ${stat("Baterai", `${bat.level ?? "?"}% · ${bat.health}`)}
        ${stat("Suhu baterai", bat.temp != null ? bat.temp.toFixed(1) + " °C" : "-")}
        ${stat("Penyimpanan", storage ? `${gb(storage.used)} / ${gb(storage.total)} (${storage.percent}%)` : "-")}
        ${stat("RAM", mem ? `${gb(mem.avail)} bebas dari ${gb(mem.total)}` : "-")}
        ${stat("IP WiFi", wifiIp)}
      </div></div>
      <div class="row"><button id="refresh">🔄 Refresh</button></div>`;
    $("#refresh").onclick = () => go("dashboard");
  },

  async info(view) {
    const raw = await sh("getprop");
    const rows = [...raw.matchAll(/^\[(.+?)\]: \[(.*)\]$/gm)].map((m) => [m[1], m[2]]);
    view.innerHTML = `
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
    view.innerHTML = `<div class="row"><button id="run" class="primary">▶ Jalankan semua pemeriksaan</button></div><div class="card"><table id="res"><tr><th>Pemeriksaan</th><th>Status</th><th>Nilai</th><th>Detail</th></tr></table></div>`;
    $("#run").onclick = runHardwareTests;
    await runHardwareTests();
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
    view.innerHTML = `<div class="card"><h2>Security Check (baca saja)</h2><table>
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
      if (!pkg) return;
      const d = $("#detail");
      d.style.display = "block";
      d.textContent = "Memuat…";
      const out = await sh(`dumpsys package ${pkg} | grep -E "versionName|versionCode|firstInstallTime|lastUpdateTime|installerPackageName"`);
      d.textContent = `${pkg}\n${out || "(tidak ada data)"}`;
    };
    draw();
  },

  async files(view, path = "/sdcard") {
    const out = await sh(`ls -la "${path}"`);
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
        <table>${entries.map((e) => `<tr><td>${e.dir ? "📁" : "📄"} ${e.dir ? `<span class="link" data-dir="${esc(e.name)}">${esc(e.name)}</span>` : esc(e.name)}</td><td class="muted">${e.dir ? "" : esc(e.size)}</td><td class="muted">${esc(e.date)}</td></tr>`).join("") || `<tr><td class="muted">(kosong / tidak ada izin)</td></tr>`}</table></div>`;
    $("#up").onclick = () => PAGE_RENDER.files(view, parent);
    view.querySelectorAll("[data-dir]").forEach((el) => {
      el.onclick = () => PAGE_RENDER.files(view, path.replace(/\/$/, "") + "/" + el.dataset.dir);
    });
  },

  async repair(view) {
    await renderRepair(view, { sh, getAdb: () => adb, esc });
  },

  async mirror(view) {
    view.innerHTML = `
      <div class="card"><h2>Screen Mirror (scrcpy)</h2>
        <div class="row">
          <button id="start" class="primary">▶ Mulai</button>
          <button id="stop">⏹ Stop</button>
          <span id="mstat" class="muted"></span>
        </div>
        <div id="stage"></div>
        <div class="row" id="navbar" style="display:none">
          <button data-k="4">◀ Back</button>
          <button data-k="3">⚪ Home</button>
          <button data-k="187">▢ Recents</button>
          <button id="shot">📷 Screenshot</button>
        </div>
        ${MIRROR_HELP}</div>`;

    const stat = (t) => { const el = $("#mstat"); if (el) el.textContent = t; };
    const ACTION = { Down: 0, Up: 1, Move: 2 };
    const FINGER = -2n; // pointer id "finger" milik scrcpy

    $("#stop").onclick = async () => {
      await stopMirror();
      const nb = $("#navbar");
      if (nb) nb.style.display = "none";
      stat("Berhenti.");
    };

    $("#start").onclick = async () => {
      if (mirrorRunning) return;
      mirrorRunning = true;
      try {
        if (typeof VideoDecoder === "undefined") throw new Error("Browser ini tidak mendukung WebCodecs. Pakai Chrome atau Edge terbaru.");

        stat("Mengunduh server scrcpy…");
        const res = await fetch(SCRCPY_SERVER_URL);
        if (!res.ok) throw new Error(`File server scrcpy tidak ditemukan (${res.status}).`);
        const server = new Uint8Array(await res.arrayBuffer());
        // jar = zip, harus diawali "PK"
        if (!(server[0] === 0x50 && server[1] === 0x4b)) throw new Error("File server scrcpy tidak valid.");

        stat("Mengirim server ke HP…");
        await AdbScrcpyClient.pushServer(
          adb,
          new ReadableStream({ start(c) { c.enqueue(server); c.close(); } }),
        );

        stat("Memulai scrcpy…");
        const client = await AdbScrcpyClient.start(
          adb,
          DefaultServerPath,
          new AdbScrcpyOptions5_0_1({ audio: false, control: true, maxSize: 1024, maxFps: 30 }),
        );
        if (!mirrorRunning) { await client.close(); return; }
        scrcpyClient = client;

        // output server harus dikuras agar koneksi ADB tidak macet
        client.output.pipeTo(new WritableStream({ write() {} })).catch(() => {});
        client.exited.then(() => {
          if (scrcpyClient === client) {
            scrcpyClient = null;
            mirrorRunning = false;
            stat("scrcpy berhenti.");
          }
        }).catch(() => {});

        const { metadata, stream } = await client.videoStream;
        const stage = $("#stage");
        if (!stage) return;
        const canvas = document.createElement("canvas");
        canvas.className = "screen";
        canvas.style.touchAction = "none";
        canvas.style.maxWidth = "100%";
        canvas.style.maxHeight = "75vh";
        canvas.style.cursor = "pointer";
        stage.replaceChildren(canvas);

        const decoder = new WebCodecsVideoDecoder({
          codec: metadata.codec,
          renderer: new BitmapVideoFrameRenderer({ canvas }),
        });
        scrcpyDecoder = decoder;
        stream.pipeTo(decoder.writable).catch(() => {});

        // --- kontrol sentuh ---
        let pressed = false;
        const touch = (action, e) => {
          const ctrl = scrcpyClient?.controller;
          if (!ctrl || !canvas.width || !canvas.height) return;
          const rect = canvas.getBoundingClientRect();
          const x = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
          const y = Math.min(1, Math.max(0, (e.clientY - rect.top) / rect.height));
          ctrl.injectTouch({
            action,
            pointerId: FINGER,
            pointerX: Math.round(x * canvas.width),
            pointerY: Math.round(y * canvas.height),
            videoWidth: canvas.width,
            videoHeight: canvas.height,
            pressure: action === ACTION.Up ? 0 : 1,
            actionButton: 0,
            buttons: action === ACTION.Up ? 0 : 1,
          }).catch(() => {});
        };
        canvas.addEventListener("pointerdown", (e) => {
          e.preventDefault();
          pressed = true;
          canvas.setPointerCapture(e.pointerId);
          touch(ACTION.Down, e);
        });
        canvas.addEventListener("pointermove", (e) => { if (pressed) touch(ACTION.Move, e); });
        const release = (e) => { if (pressed) { pressed = false; touch(ACTION.Up, e); } };
        canvas.addEventListener("pointerup", release);
        canvas.addEventListener("pointercancel", release);

        // --- tombol navigasi & screenshot ---
        const nb = $("#navbar");
        nb.style.display = "";
        nb.querySelectorAll("button[data-k]").forEach((b) => {
          b.onclick = async () => {
            const ctrl = scrcpyClient?.controller;
            if (!ctrl) return;
            const keyCode = Number(b.dataset.k);
            try {
              await ctrl.injectKeyCode({ action: 0, keyCode, repeat: 0, metaState: 0 });
              await ctrl.injectKeyCode({ action: 1, keyCode, repeat: 0, metaState: 0 });
            } catch {}
          };
        });
        $("#shot").onclick = async () => {
          const blob = await scrcpyDecoder?.snapshot();
          if (!blob) return;
          const a = document.createElement("a");
          a.href = URL.createObjectURL(blob);
          a.download = `screenshot-${Date.now()}.png`;
          a.click();
          setTimeout(() => URL.revokeObjectURL(a.href), 1000);
        };

        stat(`Terhubung · ${canvas.width}×${canvas.height}`);
      } catch (e) {
        await stopMirror();
        stat("");
        const stage = $("#stage");
        if (stage) stage.innerHTML = `<pre class="fail">${esc(e.message || e)}</pre>`;
      }
    };
  },

  async terminal(view) {
    view.innerHTML = `
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
// ---------------------------------------------------------------
async function runHardwareTests() {
  const tbl = $("#res");
  if (!tbl) return;
  tbl.innerHTML = `<tr><th>Pemeriksaan</th><th>Status</th><th>Nilai</th><th>Detail</th></tr>`;
  const features = await sh("pm list features");
  const hasFeature = (f) => features.includes(f);
  const add = (name, status, value, detail) => {
    tbl.insertAdjacentHTML("beforeend",
      `<tr><td>${esc(name)}</td><td class="${statusClass(status)}">${status}</td><td>${esc(value)}</td><td class="muted">${esc(detail)}</td></tr>`);
  };

  const bat = parseBattery(await sh("dumpsys battery"));
  if (bat.healthCode === 2) add("Battery health", "PASS", bat.health, "Kondisi baterai baik.");
  else if (bat.healthCode) add("Battery health", bat.healthCode === 1 ? "INFO" : "FAIL", bat.health, "Indikasi masalah fisik baterai.");
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
    add(name, "INFO", hasFeature(feat) ? "Ada di spesifikasi" : "Tidak tercantum", "HP mengaku punya komponen ini; belum tentu berfungsi.");
  }

  const sim = await prop("gsm.sim.state");
  const op = await prop("gsm.operator.alpha");
  add("Modem / SIM", /READY/.test(sim) ? "PASS" : sim ? "WARN" : "INFO", `${sim || "-"} ${op ? "· " + op : ""}`, "Status registrasi SIM/jaringan.");

  const log = await sh("logcat -d -t 3000");
  const crashes = (log.match(/FATAL EXCEPTION/g) || []).length;
  const anrs = (log.match(/ANR in /g) || []).length;
  add("Stabilitas software", crashes + anrs >= 10 ? "WARN" : "PASS", `${crashes} crash, ${anrs} ANR`, "Dari 3000 baris logcat terakhir.");
}

// ---------------------------------------------------------------
needDevice();
go("dashboard");
