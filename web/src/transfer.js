// Kirim file ke HP (halaman File) dan tombol Tempel clipboard di panel Mirror.
import { esc, sq } from "./kit.js";

const SAFE = /[^A-Za-z0-9._()-]/g;
const DIR_OK = /^\/(sdcard|storage\/emulated\/0)(\/[A-Za-z0-9._ ()-]+)*$/;
// Segmen "." atau ".." lolos regex di atas (titik diizinkan), jadi ditolak terpisah.
const dirOk = (p) => DIR_OK.test(p) && !p.split("/").some((seg) => seg === "." || seg === "..");
const fmt = (n) => (n >= 1024 ** 3 ? (n / 1024 ** 3).toFixed(2) + " GB" : n >= 1024 ** 2 ? (n / 1024 ** 2).toFixed(1) + " MB" : Math.max(1, Math.round(n / 1024)) + " KB");

async function readAll(stream) {
  const reader = stream.getReader();
  let n = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    n += value.length;
  }
  return n;
}

// Kirim sebagai satu aliran ke `head -c <ukuran> > file`. Proses di HP berhenti sendiri setelah
// ukuran terpenuhi, jadi stdin tidak perlu ditutup (menutup stdin menutup seluruh socket ADB).
async function sendFile(adb, sh, file, path, onProgress) {
  const q = sq(path);
  if (file.size === 0) { await sh(`: > ${q}`); return; }
  const proc = await adb.subprocess.noneProtocol.spawn(`head -c ${file.size} > ${q}`);
  const finished = readAll(proc.output).catch(() => 0);
  let lastMove = performance.now();
  let stall;
  const stalled = new Promise((_, reject) => {
    stall = setInterval(() => {
      if (performance.now() - lastMove > 20000) reject(new Error("Pengiriman macet lebih dari 20 detik. Cabut dan colok kabel USB lalu coba lagi."));
    }, 1000);
  });
  const work = (async () => {
    const reader = file.stream().getReader();
    const writer = proc.stdin.getWriter();
    let sent = 0;
    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        await writer.write(value);
        sent += value.length;
        lastMove = performance.now();
        onProgress(sent);
      }
    } finally {
      try { writer.releaseLock(); } catch {}
    }
    await finished;
  })();
  work.catch(() => {});
  try {
    await Promise.race([work, stalled]);
  } catch (e) {
    try { await proc.kill(); } catch {}
    throw e;
  } finally {
    clearInterval(stall);
  }
  const size = Number((await sh(`stat -c %s ${q} 2>/dev/null`)).trim());
  if (size !== file.size) throw new Error(`Ukuran di HP tidak cocok (${Number.isFinite(size) ? size : "tidak ada"} dari ${file.size}).`);
}

export function renderTransfer(box, { getAdb, sh, dir }) {
  if (!box) return;
  const dirs = ["/sdcard/Download", "/sdcard/DCIM", "/sdcard/Documents", "/sdcard/Pictures", "/sdcard/Music"];
  const here = String(dir || "").replace(/\/$/, "");
  if (dirOk(here) && !dirs.includes(here)) dirs.unshift(here);
  box.innerHTML = `
    <div class="card"><h2>Kirim file ke HP</h2>
      <p class="muted">Kirim file dari perangkat ini ke penyimpanan HP lewat USB. Nama file dirapikan: spasi dan simbol diganti garis bawah.</p>
      <div class="row"><input type="file" id="xf" /><select id="xd" aria-label="Folder tujuan">${dirs.map((d) => `<option value="${esc(d)}">${esc(d)}</option>`).join("")}</select></div>
      <div class="row"><button id="xg" class="primary">Kirim ke HP</button></div>
      <div class="pbar" hidden><i></i></div><p id="xs" class="muted"></p>
    </div>`;
  const $ = (s) => box.querySelector(s);
  const stat = (t, cls = "muted") => { const el = $("#xs"); el.className = cls; el.textContent = t; };
  $("#xg").onclick = async () => {
    const file = $("#xf").files?.[0];
    const adb = getAdb();
    if (!adb) return stat("HP belum terhubung.", "fail");
    if (!file) return stat("Pilih file dulu.", "warn");
    const name = file.name.replace(SAFE, "_");
    if (!name || /^\.+$/.test(name)) return stat("Nama file tidak valid.", "fail");
    const destDir = $("#xd").value;
    if (!dirOk(destDir)) return stat("Folder tujuan tidak valid.", "fail");
    const path = `${destDir}/${name}`;
    const exists = (await sh(`stat -c %s ${sq(path)} 2>/dev/null`)).trim();
    if (/^\d+$/.test(exists) && !confirm(`${name} sudah ada di folder itu (${fmt(Number(exists))}). Timpa?`)) return;
    const btn = $("#xg");
    const bar = box.querySelector(".pbar");
    btn.disabled = true;
    bar.hidden = false;
    const t0 = performance.now();
    try {
      await sendFile(adb, sh, file, path, (sent) => {
        const sec = (performance.now() - t0) / 1000;
        bar.firstElementChild.style.width = `${Math.round((sent / file.size) * 100)}%`;
        stat(`Mengirim ${fmt(sent)} dari ${fmt(file.size)} (${(sent / 1048576 / Math.max(sec, 0.1)).toFixed(1)} MB/s)`);
      });
      bar.firstElementChild.style.width = "100%";
      stat(`Terkirim: ${path} (${fmt(file.size)} dalam ${((performance.now() - t0) / 1000).toFixed(1)} detik)`, "pass");
    } catch (e) {
      stat("Gagal: " + (e?.message || e), "fail");
    } finally {
      btn.disabled = false;
    }
  };
}

// Tombol di panel Mirror: tempel teks dari clipboard komputer ke HP (memakai kotak ketik yang sudah ada).
export function extendMirror(view) {
  const type = view.querySelector("#typebar .mx-type");
  if (!type) return;
  const btn = document.createElement("button");
  btn.className = "mx-wide";
  btn.textContent = "Tempel dari clipboard komputer";
  btn.onclick = async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (!text) return;
      const input = view.querySelector("#typetxt");
      input.value = text.slice(0, 300);
      view.querySelector("#typego").click();
      if (text.length > 300) alert("Hanya 300 karakter pertama yang ditempel. Batas dari scrcpy.");
    } catch {
      alert("Izinkan akses clipboard di browser, lalu coba lagi.");
    }
  };
  type.after(btn);
}
