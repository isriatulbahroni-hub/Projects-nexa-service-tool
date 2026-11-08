// Screen Mirror (scrcpy) untuk versi web.
// Dipisah dari main.js supaya alur start bisa dioptimalkan sendiri:
//  - server scrcpy diunduh di latar belakang saat halaman dibuka (bukan saat tombol Mulai ditekan)
//  - server tidak dikirim ulang ke HP kalau file yang sama sudah ada
//  - tiap tahap punya batas waktu, jadi tidak menggantung selamanya di "Mengirim server ke HP..."
//  - kalau push lewat sync macet, otomatis pindah ke push lewat shell (base64)
//  - profil kualitas Ringan / Normal / Tajam
import { AdbScrcpyClient, AdbScrcpyOptions5_0_1 } from "@yume-chan/adb-scrcpy";
import { DefaultServerPath } from "@yume-chan/scrcpy";
import { BitmapVideoFrameRenderer, WebCodecsVideoDecoder } from "@yume-chan/scrcpy-decoder-webcodecs";

const SCRCPY_SERVER_URL = "/scrcpy-server.bin";
const PROFILE_KEY = "nexa-mirror-profile";

const PROFILES = {
  ringan: { label: "Ringan (720p, tercepat)", maxSize: 720, maxFps: 24, videoBitRate: 2_000_000 },
  normal: { label: "Normal (1024p)", maxSize: 1024, maxFps: 30, videoBitRate: 4_000_000 },
  tajam: { label: "Tajam (1600p)", maxSize: 1600, maxFps: 30, videoBitRate: 8_000_000 },
};

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
export function prefetchServer() {
  if (!serverPromise) {
    serverPromise = (async () => {
      const res = await fetch(SCRCPY_SERVER_URL, { cache: "force-cache" });
      if (!res.ok) throw new Error(`File server scrcpy tidak ditemukan (${res.status}).`);
      const bytes = new Uint8Array(await res.arrayBuffer());
      // jar = zip, harus diawali "PK"
      if (!(bytes[0] === 0x50 && bytes[1] === 0x4b)) throw new Error("File server scrcpy tidak valid.");
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

// Kirim sebagai potongan kecil supaya tidak menyumbat buffer USB.
function chunkedStream(bytes, size = 32 * 1024) {
  let off = 0;
  return new ReadableStream({
    pull(controller) {
      if (off >= bytes.length) { controller.close(); return; }
      controller.enqueue(bytes.subarray(off, off + size));
      off += size;
    },
  });
}

function toBase64(bytes) {
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  }
  return btoa(bin);
}

async function remoteSize(sh, path) {
  const out = await sh(`ls -l ${path} 2>/dev/null`);
  const m = out.match(/\s(\d+)\s+\d{4}-\d{2}-\d{2}/);
  return m ? Number(m[1]) : null;
}

// Cadangan: tulis file lewat shell (base64). Lambat-lambat tapi tidak bergantung pada protokol sync.
async function pushViaShell(sh, bytes, path, onProgress) {
  await sh(`rm -f ${path}`);
  const STEP = 6000;
  for (let off = 0; off < bytes.length; off += STEP) {
    const b64 = toBase64(bytes.subarray(off, off + STEP));
    await sh(`echo '${b64}' | base64 -d >> ${path}`);
    onProgress?.(Math.min(100, Math.round(((off + STEP) / bytes.length) * 100)));
  }
  await sh(`chmod 644 ${path}`);
  const size = await remoteSize(sh, path);
  if (size !== bytes.length) throw new Error("Push lewat shell tidak lengkap (ukuran file di HP tidak cocok).");
}

// ---------------------------------------------------------------
// Halaman Mirror
// ---------------------------------------------------------------
export function renderMirror(view, { sh, getAdb, helpHtml }) {
  let saved = "ringan";
  try { saved = localStorage.getItem(PROFILE_KEY) || "ringan"; } catch {}
  if (!PROFILES[saved]) saved = "ringan";

  view.innerHTML = `
    <div class="card"><h2>Screen Mirror (scrcpy)</h2>
      <div class="row">
        <button id="start" class="primary">▶ Mulai</button>
        <button id="stop">⏹ Stop</button>
        <select id="profile" aria-label="Kualitas mirror">
          ${Object.entries(PROFILES).map(([k, p]) => `<option value="${k}"${k === saved ? " selected" : ""}>${esc(p.label)}</option>`).join("")}
        </select>
        <span id="mstat" class="muted"></span>
      </div>
      <div id="stage"></div>
      <div class="row" id="navbar" style="display:none">
        <button data-k="4">◀ Back</button>
        <button data-k="3">⚪ Home</button>
        <button data-k="187">▢ Recents</button>
        <button data-k="26">⏻ Power</button>
        <button data-k="25">🔉 Vol−</button>
        <button data-k="24">🔊 Vol+</button>
        <button data-fn="notif">🔔 Notifikasi</button>
        <button data-fn="rotate">⟳ Putar</button>
        <button id="shot">📷 Screenshot</button>
      </div>
      <div class="row" id="typebar" style="display:none">
        <input id="typetxt" placeholder="Ketik teks untuk dikirim ke HP…" />
        <button id="typego">Kirim teks</button>
      </div>
      <p class="muted" id="kbhint" style="display:none">Klik layar HP di atas, lalu ketik dengan keyboard komputer dan scroll dengan roda mouse. Untuk HP dengan keyboard layar, kotak "Ketik teks" lebih andal.</p>
      <p class="muted">Kalau mirror terasa berat atau lambat, pilih kualitas <b>Ringan</b>. Pertama kali dipakai butuh beberapa detik untuk memasang server di HP; berikutnya lebih cepat.</p>
      ${helpHtml}</div>`;

  // mulai unduh server sekarang, supaya saat Mulai ditekan sudah siap
  prefetchServer().catch(() => {});

  const stat = (t) => { const el = $("#mstat"); if (el) el.textContent = t; };
  const ACTION = { Down: 0, Up: 1, Move: 2 };
  const FINGER = -2n; // pointer id "finger" milik scrcpy
  const KEYMAP = { Enter: 66, Backspace: 67, Delete: 112, Tab: 61, ArrowUp: 19, ArrowDown: 20, ArrowLeft: 21, ArrowRight: 22, Escape: 4, Home: 3 };
  const hideControls = () => {
    for (const id of ["#navbar", "#typebar", "#kbhint"]) {
      const el = $(id);
      if (el) el.style.display = "none";
    }
  };

  $("#profile").onchange = (e) => {
    try { localStorage.setItem(PROFILE_KEY, e.target.value); } catch {}
  };

  $("#stop").onclick = async () => {
    await stopMirror();
    hideControls();
    stat("Berhenti.");
  };

  $("#start").onclick = async () => {
    if (running) return;
    running = true;
    const adb = getAdb();
    const profile = PROFILES[$("#profile").value] || PROFILES.ringan;
    const t0 = performance.now();
    let step = "Menyiapkan…";
    const tick = setInterval(() => stat(`${step} (${Math.round((performance.now() - t0) / 1000)} dtk)`), 400);
    const setStep = (s) => { step = s; stat(`${s} (${Math.round((performance.now() - t0) / 1000)} dtk)`); };
    const alive = () => running;

    try {
      if (!adb) throw new Error("HP belum terhubung.");
      if (typeof VideoDecoder === "undefined") throw new Error("Browser ini tidak mendukung WebCodecs. Pakai Chrome atau Edge terbaru.");

      // 1) unduh server, bersihkan sisa sesi lama, dan cek file di HP: semuanya paralel
      setStep("Menyiapkan server scrcpy");
      const [server, , existing] = await Promise.all([
        prefetchServer(),
        // sisa server dari sesi sebelumnya (mis. setelah refresh) bisa menahan koneksi
        sh('pkill -f "[c]om.genymobile.scrcpy.Server"'),
        remoteSize(sh, DefaultServerPath),
      ]);
      if (!alive()) return;

      // 2) kirim server hanya kalau belum ada di HP
      if (existing === server.length) {
        setStep("Server sudah ada di HP, lewati pengiriman");
      } else {
        setStep("Mengirim server ke HP");
        try {
          await withTimeout(
            AdbScrcpyClient.pushServer(adb, chunkedStream(server), DefaultServerPath),
            10000,
            "Push sync macet.",
          );
        } catch (e) {
          setStep("Push cepat macet, memakai jalur cadangan");
          await pushViaShell(sh, server, DefaultServerPath, (p) => setStep(`Mengirim server (cadangan) ${p}%`));
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
      if (!alive()) { await started.close(); return; }
      client = started;

      // output server harus dikuras agar koneksi ADB tidak macet
      started.output.pipeTo(new WritableStream({ write() {} })).catch(() => {});
      started.exited.then(() => {
        if (client === started) {
          client = null;
          running = false;
          stat("scrcpy berhenti.");
        }
      }).catch(() => {});

      setStep("Menunggu gambar dari HP");
      const { metadata, stream } = await withTimeout(
        started.videoStream,
        10000,
        "HP tidak mengirim gambar. Pastikan layar HP menyala dan USB debugging diizinkan.",
      );
      const stage = $("#stage");
      if (!stage) return;
      const canvas = document.createElement("canvas");
      canvas.className = "screen";
      canvas.tabIndex = 0;
      canvas.style.touchAction = "none";
      canvas.style.maxWidth = "100%";
      canvas.style.maxHeight = "75vh";
      canvas.style.cursor = "pointer";
      canvas.style.outline = "none";
      stage.replaceChildren(canvas);

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
      canvas.addEventListener("pointerdown", (e) => {
        e.preventDefault();
        canvas.focus();
        pressed = true;
        canvas.setPointerCapture(e.pointerId);
        touch(ACTION.Down, e);
      });
      canvas.addEventListener("pointermove", (e) => { if (pressed) touch(ACTION.Move, e); });
      const release = (e) => { if (pressed) { pressed = false; touch(ACTION.Up, e); } };
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
      const nb = $("#navbar");
      nb.style.display = "";
      nb.querySelectorAll("button[data-k]").forEach((b) => {
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
      nb.querySelectorAll("button[data-fn]").forEach((b) => {
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
      $("#typebar").style.display = "";
      $("#kbhint").style.display = "";
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

      const took = Math.round((performance.now() - t0) / 100) / 10;
      clearInterval(tick);
      stat(`Terhubung · menunggu gambar… (siap dalam ${took} dtk)`);
      await sleep(1500);
      if (client === started) stat(`Terhubung · ${canvas.width}×${canvas.height} · siap dalam ${took} dtk`);
    } catch (e) {
      await stopMirror();
      stat("");
      hideControls();
      const stage = $("#stage");
      if (stage) stage.innerHTML = `<pre class="fail">${esc(e.message || e)}</pre>`;
    } finally {
      clearInterval(tick);
    }
  };
}
