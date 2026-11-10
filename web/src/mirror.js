// Screen Mirror (scrcpy) untuk versi web.
// Dipisah dari main.js supaya alur start bisa dioptimalkan sendiri:
//  - server scrcpy diunduh di latar belakang saat halaman dibuka (bukan saat tombol Mulai ditekan)
//  - server dikirim ke HP lewat `head -c <ukuran> > file`: proses di HP berhenti sendiri setelah
//    jumlah byte terpenuhi, jadi tidak perlu menutup stdin (di ADB, menutup stdin = menutup seluruh socket,
//    yang membuat `cat > file` menggantung atau file terpotong)
//  - kalau jalur utama gagal/macet, prosesnya DIMATIKAN dulu baru jalur sync (cadangan) dicoba
//  - server tidak dikirim ulang ke HP kalau file yang sama sudah ada
//  - tiap tahap punya batas waktu dan dicatat lamanya, supaya yang lambat kelihatan
//  - profil kualitas Ringan / Normal / Tajam
//  - tata letak dua kolom: layar HP dalam bingkai ponsel + panel kontrol (lihat mirror.css)
import "./mirror.css";
import { AdbScrcpyClient, AdbScrcpyOptions5_0_1 } from "@yume-chan/adb-scrcpy";
import { DefaultServerPath } from "@yume-chan/scrcpy";
import { BitmapVideoFrameRenderer, WebCodecsVideoDecoder } from "@yume-chan/scrcpy-decoder-webcodecs";
import { SCRCPY_SERVER_SHA256, sha256Hex } from "./verify.js";

const SCRCPY_SERVER_URL = "/scrcpy-server.bin";
const PROFILE_KEY = "nexa-mirror-profile";

const PROFILES = {
  ringan: { label: "Ringan (720p, tercepat)", maxSize: 720, maxFps: 24, videoBitRate: 2_000_000 },
  normal: { label: "Normal (1024p)", maxSize: 1024, maxFps: 30, videoBitRate: 4_000_000 },
  tajam: { label: "Tajam (1600p)", maxSize: 1600, maxFps: 30, videoBitRate: 12_000_000 },
  asli: { label: "Asli (resolusi penuh, paling jelas)", maxSize: 0, maxFps: 30, videoBitRate: 16_000_000 },
};

// Ikon garis sederhana (stroke mengikuti warna teks tombol)
const IC = {
  back: '<path d="M15 5l-7 7 7 7"/>',
  home: '<circle cx="12" cy="12" r="7"/>',
  recents: '<rect x="6" y="6" width="12" height="12" rx="2"/>',
  volm: '<path d="M4 10v4h4l5 4V6L8 10H4z"/><path d="M16 12h5"/>',
  volp: '<path d="M4 10v4h4l5 4V6L8 10H4z"/><path d="M16 12h5M18.5 9.5v5"/>',
  power: '<path d="M12 3v9"/><path d="M6.5 7a8 8 0 1 0 11 0"/>',
  bell: '<path d="M6 16v-5a6 6 0 0 1 12 0v5l2 2H4z"/><path d="M10 21h4"/>',
  rotate: '<path d="M20 12a8 8 0 1 1-3-6.2"/><path d="M20 4v5h-5"/>',
  shot: '<rect x="3" y="6" width="18" height="14" rx="2"/><circle cx="12" cy="13" r="3.5"/><path d="M9 6l1.5-2h3L15 6"/>',
  phone: '<rect x="7" y="2" width="10" height="20" rx="2.5"/><path d="M11 18h2"/>',
};
const icon = (k) => `<svg class="ic" viewBox="0 0 24 24" aria-hidden="true">${IC[k]}</svg>`;
const keyBtn = (k, ic, label) => `<button class="mx-btn" data-k="${k}">${icon(ic)}<span>${label}</span></button>`;

const $ = (sel) => document.querySelector(sel);
const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

let running = false;
let client = null;
let decoder = null;

export const isMirrorRunning = () => running;

export async function stopMirror() {
  running = false;
  const c = client;
  const d = decoder;
  client = null;
  decoder = null;
  try { d?.dispose(); } catch {}
  try { await c?.close(); } catch {}
}

// Dipakai saat tab ditutup (tidak bisa menunggu async).
export function closeMirrorSync() {
  try { client?.close(); } catch {}
}

// ---------------------------------------------------------------
// Unduh server scrcpy sekali saja (cache di memori + cache browser)
// ---------------------------------------------------------------
let serverPromise = null;

async function loadServerBytes(cache) {
  const res = await fetch(SCRCPY_SERVER_URL, { cache });
  if (!res.ok) throw new Error(`File server scrcpy tidak ditemukan (${res.status}).`);
  const bytes = new Uint8Array(await res.arrayBuffer());
  // jar = zip, harus diawali "PK"
  if (!(bytes[0] === 0x50 && bytes[1] === 0x4b)) throw new Error("File server scrcpy tidak valid.");
  return bytes;
}

export function prefetchServer() {
  if (!serverPromise) {
    serverPromise = (async () => {
      // File ini dikirim dan DIJALANKAN di HP pelanggan, jadi isinya harus persis rilis resmi
      // (SHA-256 yang sama dengan skrip build). Kalau cache browser berisi versi lain, ambil ulang dari jaringan.
      let bytes = await loadServerBytes("force-cache");
      if ((await sha256Hex(bytes)) !== SCRCPY_SERVER_SHA256) {
        bytes = await loadServerBytes("reload");
        if ((await sha256Hex(bytes)) !== SCRCPY_SERVER_SHA256) {
          throw new Error("Checksum server scrcpy tidak cocok dengan rilis resmi; file ditolak.");
        }
      }
      return bytes;
    })().catch((e) => {
      serverPromise = null; // boleh dicoba lagi
      throw e;
    });
  }
  return serverPromise;
}

function withTimeout(promise, ms, message) {
  let t;
  return Promise.race([
    promise,
    new Promise((_, reject) => { t = setTimeout(() => reject(new Error(message)), ms); }),
  ]).finally(() => clearTimeout(t));
}

async function readAll(stream) {
  const reader = stream.getReader();
  const dec = new TextDecoder();
  let s = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    s += dec.decode(value, { stream: true });
  }
  return s;
}

// Kirim sebagai potongan 64 KB untuk jalur sync (cadangan).
function chunkedStream(bytes, size = 64 * 1024) {
  let off = 0;
  return new ReadableStream({
    pull(controller) {
      if (off >= bytes.length) { controller.close(); return; }
      controller.enqueue(bytes.subarray(off, off + size));
      off += size;
    },
  });
}

// Ukuran file di HP: `stat` dulu (paling andal), `ls -l` sebagai cadangan.
async function remoteSize(sh, path) {
  const a = (await sh(`stat -c %s ${path} 2>/dev/null`)).trim();
  if (/^\d+$/.test(a)) return Number(a);
  const out = await sh(`ls -l ${path} 2>/dev/null`);
  const m = out.match(/\s(\d+)\s+\d{4}-\d{2}-\d{2}/);
  return m ? Number(m[1]) : null;
}

// SHA-256 file di HP. null = HP tidak punya `sha256sum` atau file tidak terbaca (tidak bisa diverifikasi).
async function remoteSha256(sh, path) {
  const out = await sh(`sha256sum ${path} 2>/dev/null`);
  const m = out.trim().match(/^([0-9a-f]{64})\b/i);
  return m ? m[1].toLowerCase() : null;
}

// Jalur utama: `head -c <ukuran> > file`. Proses di HP berhenti sendiri tepat setelah <ukuran> byte,
// jadi stdin TIDAK ditutup (menutup stdin di ADB menutup seluruh socket dan bisa memotong file).
// Kalau macet, proses dimatikan supaya tidak menahan file dan koneksi USB untuk jalur berikutnya.
async function pushViaShell(adb, sh, bytes, path, ms) {
  // SEMUA panggilan ke HP diberi batas waktu: sebelumnya `rm`, `kill`, `chmod`, dan `stat` tanpa batas,
  // jadi kalau jalur USB macet tampilan diam di "Mengirim server ke HP" sampai berminggu-minggu.
  await withTimeout(sh(`rm -f ${path}`), 4000, "HP tidak merespons perintah awal (rm).");
  const proc = await withTimeout(
    adb.subprocess.noneProtocol.spawn(`head -c ${bytes.length} > ${path}`),
    4000,
    "HP tidak membuka shell untuk menerima server.",
  );
  const finished = readAll(proc.output).catch(() => "");
  const work = (async () => {
    const writer = proc.stdin.getWriter();
    try {
      await writer.write(bytes);
    } finally {
      try { writer.releaseLock(); } catch {}
    }
    await finished; // socket ditutup HP setelah `head` selesai
  })();
  work.catch(() => {}); // cegah unhandled rejection kalau timeout lebih dulu
  try {
    await withTimeout(work, ms, "Pengiriman ke HP macet.");
  } catch (e) {
    // jangan menunggu kill selesai: kalau USB macet, kill pun ikut macet
    try { Promise.resolve(proc.kill()).catch(() => {}); } catch {}
    throw e;
  }
  await withTimeout(sh(`chmod 644 ${path}`), 4000, "HP tidak merespons (chmod).");
  const size = await withTimeout(remoteSize(sh, path), 4000, "HP tidak merespons (cek ukuran).");
  if (size !== bytes.length) {
    throw new Error(`Ukuran file di HP tidak cocok (${size ?? "tidak ada"} dari ${bytes.length}).`);
  }
}

// Jalur paling andal: kirim lewat perintah shell kecil (base64 per potongan, `printf >> file`).
// Tidak memakai aliran data besar (stdin/sync) yang di sebagian HP/kabel/port USB macet.
function toBase64(bytes) {
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  }
  return btoa(bin);
}

async function pushViaBase64(adb, sh, bytes, path, onProgress) {
  const b64 = toBase64(bytes);
  const tmp = `${path}.b64`;
  // potongan mengikuti batas payload ADB yang dinegosiasikan (HP baru jauh lebih besar), minimal aman 3000
  const mp = Number(adb.maxPayloadSize) || 4096;
  const CH = Math.max(3000, Math.min(48000, mp - 400));
  const run = (cmd) => withTimeout(
    adb.subprocess.noneProtocol.spawn(cmd).wait(),
    5000,
    "HP tidak merespons saat menerima potongan server.",
  );
  await run(`rm -f ${path} ${tmp}`);
  const total = Math.ceil(b64.length / CH);
  for (let i = 0; i < total; i++) {
    await run(`printf %s '${b64.slice(i * CH, (i + 1) * CH)}' >> ${tmp}`);
    if (onProgress) onProgress(Math.round(((i + 1) / total) * 100));
  }
  await run(`base64 -d ${tmp} > ${path}; rm -f ${tmp}; chmod 644 ${path}`);
  const size = await withTimeout(remoteSize(sh, path), 4000, "HP tidak merespons (cek ukuran).");
  if (size !== bytes.length) {
    throw new Error(`Ukuran file di HP tidak cocok (${size ?? "tidak ada"} dari ${bytes.length}). HP mungkin tidak punya perintah base64.`);
  }
}

// ---------------------------------------------------------------
// Halaman Mirror
// ---------------------------------------------------------------
const placeholderHtml = () => `
  <div class="mx-ph">
    <div class="shape">${icon("phone")}</div>
    <p><b>Layar HP belum tampil</b><span>Tekan <b style="display:inline">Mulai</b> untuk menampilkan dan mengendalikan layar HP dari sini.</span></p>
  </div>`;

export function renderMirror(view, { sh, getAdb, helpHtml }) {
  let saved = "ringan";
  try { saved = localStorage.getItem(PROFILE_KEY) || "ringan"; } catch {}
  if (!PROFILES[saved]) saved = "ringan";

  view.innerHTML = `
    <div class="mx" id="mx">
      <section class="mx-main">
        <div class="mx-bar">
          <h2>Screen Mirror <small>scrcpy</small></h2>
          <select id="profile" aria-label="Kualitas mirror">
            ${Object.entries(PROFILES).map(([k, p]) => `<option value="${k}"${k === saved ? " selected" : ""}>${esc(p.label)}</option>`).join("")}
          </select>
          <button id="start" class="primary">▶ Mulai</button>
          <button id="stop">⏹ Stop</button>
        </div>
        <div class="mx-status"><span class="led"></span><span id="mstat">Belum berjalan</span></div>
        <div class="mx-stage"><div id="stage">${placeholderHtml()}</div></div>
        <p class="mx-err" id="merr"></p>
      </section>

      <aside class="mx-panel" id="navbar" aria-label="Kontrol HP">
        <div class="mx-sec">
          <h3>Navigasi</h3>
          <div class="mx-grid">
            ${keyBtn(4, "back", "Back")}
            ${keyBtn(3, "home", "Home")}
            ${keyBtn(187, "recents", "Recents")}
          </div>
        </div>
        <div class="mx-sec">
          <h3>Tombol fisik</h3>
          <div class="mx-grid">
            ${keyBtn(25, "volm", "Vol−")}
            ${keyBtn(24, "volp", "Vol+")}
            ${keyBtn(26, "power", "Power")}
          </div>
        </div>
        <div class="mx-sec">
          <h3>Aksi</h3>
          <div class="mx-grid">
            <button class="mx-btn" data-fn="notif">${icon("bell")}<span>Notifikasi</span></button>
            <button class="mx-btn" data-fn="rotate">${icon("rotate")}<span>Putar</span></button>
            <button class="mx-btn" id="shot">${icon("shot")}<span>Screenshot</span></button>
          </div>
        </div>
        <div class="mx-sec" id="typebar">
          <h3>Ketik teks</h3>
          <div class="mx-type">
            <input id="typetxt" placeholder="Ketik lalu Enter…" />
            <button id="typego">Kirim</button>
          </div>
          <p class="mx-hint" id="kbhint">Klik layar HP, lalu ketik dengan keyboard komputer dan scroll dengan roda mouse. Untuk HP dengan keyboard layar, kotak ini lebih andal.</p>
        </div>
        <p class="mx-tip">Terasa berat? Pilih kualitas <b>Ringan</b>. Pemasangan pertama butuh beberapa detik; berikutnya lebih cepat.</p>
      </aside>
    </div>
    ${helpHtml}`;

  // mulai unduh server sekarang, supaya saat Mulai ditekan sudah siap
  prefetchServer().catch(() => {});

  const ws = $("#mx");
  const stat = (t) => { const el = $("#mstat"); if (el) el.textContent = t; };
  const showErr = (t) => { const el = $("#merr"); if (el) el.textContent = t || ""; };
  const resetStage = () => { const s = $("#stage"); if (s) s.innerHTML = placeholderHtml(); };
  const ACTION = { Down: 0, Up: 1, Move: 2 };
  const FINGER = -2n; // pointer id "finger" milik scrcpy
  const KEYMAP = { Enter: 66, Backspace: 67, Delete: 112, Tab: 61, ArrowUp: 19, ArrowDown: 20, ArrowLeft: 21, ArrowRight: 22, Escape: 4, Home: 3 };
  const setLive = (on) => ws?.classList.toggle("live", on);

  $("#profile").onchange = (e) => {
    try { localStorage.setItem(PROFILE_KEY, e.target.value); } catch {}
  };

  $("#stop").onclick = async () => {
    await stopMirror();
    setLive(false);
    resetStage();
    showErr("");
    stat("Berhenti.");
  };

  $("#start").onclick = async () => {
    if (running) return;
    running = true;
    showErr("");
    const adb = getAdb();
    const profile = PROFILES[$("#profile").value] || PROFILES.ringan;
    const t0 = performance.now();
    let step = "Menyiapkan…";
    const tick = setInterval(() => stat(`${step} (${Math.round((performance.now() - t0) / 1000)} dtk)`), 400);
    const setStep = (s) => { step = s; stat(`${s} (${Math.round((performance.now() - t0) / 1000)} dtk)`); };
    const alive = () => running;

    // catat lama tiap tahap supaya kelihatan mana yang lambat
    const laps = [];
    let lapAt = t0;
    const lap = (name) => { const now = performance.now(); laps.push(`${name} ${((now - lapAt) / 1000).toFixed(1)}`); lapAt = now; };

    try {
      if (!adb) throw new Error("HP belum terhubung.");
      if (typeof VideoDecoder === "undefined") throw new Error("Browser ini tidak mendukung WebCodecs. Pakai Chrome atau Edge terbaru.");

      // 1) unduh server, bersihkan sisa sesi lama, dan cek file di HP: semuanya paralel
      setStep("Menyiapkan server scrcpy");
      const [server, , existing] = await withTimeout(
        Promise.all([
          prefetchServer(),
          // sisa server dari sesi sebelumnya (mis. setelah refresh) bisa menahan koneksi
          sh('pkill -f "[c]om.genymobile.scrcpy.Server"'),
          remoteSize(sh, DefaultServerPath),
        ]),
        20000,
        "Gagal menyiapkan server scrcpy (unduhan atau HP tidak merespons). Cek koneksi internet dan kabel USB.",
      );
      lap("siapkan");
      if (!alive()) return;

      // 2) kirim server hanya kalau belum ada di HP: ukuran harus sama DAN, kalau HP bisa menghitung
      //    SHA-256 (sha256sum), checksum-nya harus cocok. File berukuran sama tapi isinya beda tidak dipercaya.
      let upToDate = existing === server.length;
      if (upToDate) {
        const remoteHash = await withTimeout(remoteSha256(sh, DefaultServerPath), 6000, "HP tidak merespons (cek checksum).").catch(() => null);
        if (remoteHash && remoteHash !== SCRCPY_SERVER_SHA256) upToDate = false;
      }
      if (upToDate) {
        setStep("Server sudah ada di HP, lewati pengiriman");
        lap("kirim (lewati)");
      } else {
        setStep("Mengirim server ke HP");
        const sendAll = async () => {
          const errs = [];
          const tryWay = async (name, fn) => {
            try { await fn(); lap(`kirim (${name})`); return true; }
            catch (e) { errs.push(`${name}: ${e?.message || e}`); lap(`${name}-gagal`); return false; }
          };
          if (await tryWay("shell", () => pushViaBase64(adb, sh, server, DefaultServerPath, (pct) => setStep(`Mengirim server ke HP ${pct}%`)))) return;
          setStep("Jalur shell gagal, mencoba jalur head");
          if (await tryWay("head", () => pushViaShell(adb, sh, server, DefaultServerPath, 8000))) return;
          setStep("Jalur head gagal, mencoba jalur sync");
          if (await tryWay("sync", () => withTimeout(
            AdbScrcpyClient.pushServer(adb, chunkedStream(server), DefaultServerPath),
            12000,
            "sync macet.",
          ))) return;
          throw new Error(`Server tidak bisa dikirim ke HP. ${errs.join(" | ")}. Cabut dan colok kabel USB, lalu coba lagi.`);
        };
        // batas keras seluruh tahap kirim (jalur utama + cadangan) supaya tidak pernah menggantung
        await withTimeout(
          sendAll(),
          60000,
          "Pengiriman server ke HP macet (USB tidak merespons). Cabut dan colok kabel USB (pakai kabel data & port langsung, bukan hub), tutup aplikasi lain yang memakai ADB (adb.exe, scrcpy, Android Studio), lalu Hubungkan ulang.",
        );
        // pastikan file yang sampai di HP persis sama (kalau HP punya sha256sum)
        const sentHash = await withTimeout(remoteSha256(sh, DefaultServerPath), 6000, "HP tidak merespons (cek checksum).").catch(() => null);
        if (sentHash && sentHash !== SCRCPY_SERVER_SHA256) {
          throw new Error("Checksum server di HP tidak cocok setelah dikirim (file rusak atau terpotong). Cabut dan colok kabel USB, lalu coba lagi.");
        }
      }
      if (!alive()) return;

      // 3) jalankan scrcpy
      setStep("Memulai scrcpy");
      const started = await withTimeout(
        AdbScrcpyClient.start(
          adb,
          DefaultServerPath,
          new AdbScrcpyOptions5_0_1({
            audio: false,
            control: true,
            maxSize: profile.maxSize,
            maxFps: profile.maxFps,
            videoBitRate: profile.videoBitRate,
          }),
        ),
        15000,
        "scrcpy tidak merespons di HP. Cabut dan colok kabel USB, lalu coba lagi.",
      );
      lap("mulai");
      if (!alive()) { await started.close(); return; }
      client = started;

      // output server harus dikuras agar koneksi ADB tidak macet
      started.output.pipeTo(new WritableStream({ write() {} })).catch(() => {});
      started.exited.then(() => {
        if (client === started) {
          client = null;
          running = false;
          setLive(false);
          stat("scrcpy berhenti.");
        }
      }).catch(() => {});

      setStep("Menunggu gambar dari HP");
      const { metadata, stream } = await withTimeout(
        started.videoStream,
        10000,
        "HP tidak mengirim gambar. Pastikan layar HP menyala dan USB debugging diizinkan.",
      );
      lap("gambar");
      const stage = $("#stage");
      if (!stage) return;
      const canvas = document.createElement("canvas");
      canvas.tabIndex = 0;
      const frame = document.createElement("div");
      frame.className = "mx-frame";
      frame.appendChild(canvas);
      stage.replaceChildren(frame);

      const dec = new WebCodecsVideoDecoder({
        codec: metadata.codec,
        renderer: new BitmapVideoFrameRenderer({ canvas }),
      });
      decoder = dec;
      stream.pipeTo(dec.writable).catch(() => {});

      const ctrl = () => client?.controller;
      const report = (e) => stat("Gagal: " + (e?.message || e));
      const rel = (e) => {
        const rect = canvas.getBoundingClientRect();
        return [
          Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width)),
          Math.min(1, Math.max(0, (e.clientY - rect.top) / rect.height)),
        ];
      };

      // --- kontrol sentuh ---
      let pressed = false;
      const touch = (action, e) => {
        const c = ctrl();
        if (!c || !canvas.width || !canvas.height) return;
        const [x, y] = rel(e);
        c.injectTouch({
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
      // gerakan sentuh digabung per frame layar (maks 1 kiriman per frame) supaya USB tidak kebanjiran
      let pendingMove = null;
      let moveRaf = 0;
      canvas.addEventListener("pointerdown", (e) => {
        e.preventDefault();
        canvas.focus();
        pressed = true;
        canvas.setPointerCapture(e.pointerId);
        touch(ACTION.Down, e);
      });
      canvas.addEventListener("pointermove", (e) => {
        if (!pressed) return;
        pendingMove = e;
        if (!moveRaf) {
          moveRaf = requestAnimationFrame(() => {
            moveRaf = 0;
            const ev = pendingMove;
            pendingMove = null;
            if (ev && pressed) touch(ACTION.Move, ev);
          });
        }
      });
      const release = (e) => {
        if (!pressed) return;
        pressed = false;
        pendingMove = null;
        touch(ACTION.Up, e);
      };
      canvas.addEventListener("pointerup", release);
      canvas.addEventListener("pointercancel", release);

      // --- scroll roda mouse ---
      canvas.addEventListener("wheel", (e) => {
        const c = ctrl();
        if (!c || !canvas.width || !canvas.height) return;
        e.preventDefault();
        const [x, y] = rel(e);
        const clamp = (v) => Math.max(-1, Math.min(1, v));
        c.injectScroll({
          pointerX: Math.round(x * canvas.width),
          pointerY: Math.round(y * canvas.height),
          videoWidth: canvas.width,
          videoHeight: canvas.height,
          scrollX: clamp(-e.deltaX / 100),
          scrollY: clamp(-e.deltaY / 100),
          buttons: 0,
        }).catch(() => {});
      }, { passive: false });

      // --- keyboard komputer ---
      canvas.addEventListener("keydown", (e) => {
        const c = ctrl();
        if (!c || e.ctrlKey || e.metaKey || e.altKey) return;
        if (e.key.length === 1) {
          e.preventDefault();
          c.injectText(e.key).catch(report);
          return;
        }
        const keyCode = KEYMAP[e.key];
        if (keyCode) {
          e.preventDefault();
          (async () => {
            await c.injectKeyCode({ action: 0, keyCode, repeat: 0, metaState: 0 });
            await c.injectKeyCode({ action: 1, keyCode, repeat: 0, metaState: 0 });
          })().catch(report);
        }
      });

      // --- tombol navigasi, fungsi, dan screenshot ---
      view.querySelectorAll("button[data-k]").forEach((b) => {
        b.onclick = async () => {
          const c = ctrl();
          if (!c) return;
          const keyCode = Number(b.dataset.k);
          try {
            await c.injectKeyCode({ action: 0, keyCode, repeat: 0, metaState: 0 });
            await c.injectKeyCode({ action: 1, keyCode, repeat: 0, metaState: 0 });
          } catch (e) { report(e); }
        };
      });
      view.querySelectorAll("button[data-fn]").forEach((b) => {
        b.onclick = async () => {
          const c = ctrl();
          if (!c) return;
          try {
            if (b.dataset.fn === "notif") await c.expandNotificationPanel();
            else if (b.dataset.fn === "rotate") await c.rotateDevice();
          } catch (e) { report(e); }
        };
      });
      $("#shot").onclick = async () => {
        const blob = await decoder?.snapshot();
        if (!blob) return;
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = `screenshot-${Date.now()}.png`;
        a.click();
        setTimeout(() => URL.revokeObjectURL(a.href), 1000);
      };

      // --- kirim teks ---
      const sendText = async () => {
        const input = $("#typetxt");
        const c = ctrl();
        if (!c || !input.value) return;
        try {
          await c.injectText(input.value);
          input.value = "";
        } catch (e) { report(e); }
      };
      $("#typego").onclick = sendText;
      $("#typetxt").onkeydown = (e) => { if (e.key === "Enter") sendText(); };

      setLive(true);
      const took = Math.round((performance.now() - t0) / 100) / 10;
      clearInterval(tick);
      const breakdown = `siap ${took} dtk (${laps.join(" · ")})`;
      stat(`Terhubung · menunggu gambar… ${breakdown}`);
      await sleep(1500);
      if (client === started) stat(`Terhubung · ${canvas.width}×${canvas.height} · ${breakdown}`);
    } catch (e) {
      await stopMirror();
      setLive(false);
      resetStage();
      stat(`Gagal memulai. (${laps.join(" · ") || "tahap awal"})`);
      showErr(e.message || String(e));
    } finally {
      clearInterval(tick);
    }
  };
}
