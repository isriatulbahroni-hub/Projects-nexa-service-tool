// Halaman Penyimpanan: isi memori, umur flash (bila terbaca), kecepatan tulis, dan error di log.
import { esc, num, saveTest } from "./kit.js";

const CATS = [
  ["App", "Aplikasi"], ["App Data", "Data aplikasi"], ["Photos", "Foto"], ["Videos", "Video"],
  ["Audio", "Audio"], ["Downloads", "Unduhan"], ["System", "Sistem"], ["Other", "Lainnya"],
];

export function parseDiskstats(text) {
  const t = String(text || "");
  const lat = (t.match(/Latency:\s*(\d+)\s*ms/i) || [])[1];
  const fr = t.match(/Data-Free:\s*(\d+)K\s*\/\s*(\d+)K total/i);
  const sizes = {};
  for (const m of t.matchAll(/^\s*(App Data|App Cache|App|Photos|Videos|Audio|Downloads|System|Other) Size:\s*(\d+)/gim)) sizes[m[1]] = Number(m[2]);
  return {
    latencyMs: lat ? Number(lat) : null,
    freeKb: fr ? Number(fr[1]) : null,
    totalKb: fr ? Number(fr[2]) : null,
    sizes,
  };
}

// Angka umur flash: 0x01 = 0-10% terpakai ... 0x0A = 90-100%, 0x0B = melewati batas.
export function lifeText(n) {
  if (n === 0) return "belum dilaporkan";
  if (n >= 11) return "melewati 100%";
  return `${(n - 1) * 10} sampai ${n * 10}% terpakai`;
}

export function parseLife(text) {
  const out = [];
  for (const line of String(text || "").split("\n")) {
    const i = line.indexOf("=");
    if (i < 1) continue;
    const path = line.slice(0, i);
    const vals = [...line.slice(i + 1).matchAll(/0x[0-9a-f]+|\b\d+\b/gi)].map((m) => Number(m[0]));
    if (!vals.length) continue;
    if (/pre_eol_info/.test(path)) out.push({ label: "Cadangan blok (pre-EOL)", kind: "eol", n: vals[0] });
    else if (/life_time_estimation_b|life_time$/.test(path) && vals.length > 1) {
      out.push({ label: "Umur flash tipe A", kind: "life", n: vals[0] });
      out.push({ label: "Umur flash tipe B", kind: "life", n: vals[1] });
    } else if (/life_time_estimation_a/.test(path)) out.push({ label: "Umur flash tipe A", kind: "life", n: vals[0] });
    else if (/life_time_estimation_b/.test(path)) out.push({ label: "Umur flash tipe B", kind: "life", n: vals[0] });
    else if (/life_time$/.test(path)) out.push({ label: "Umur flash", kind: "life", n: vals[0] });
  }
  return out;
}

export function parseSpeed(text, fallbackSec) {
  const m = String(text || "").match(/copied,?\s*([\d.]+)\s*s/i);
  const sec = m ? Number(m[1]) : fallbackSec;
  return sec > 0 ? 64 / sec : null;
}

const LIFE_CMD = 'for f in /sys/class/mmc_host/mmc0/mmc0:*/life_time /sys/class/mmc_host/mmc0/mmc0:*/pre_eol_info /sys/devices/platform/soc/*.ufshc/health_descriptor/life_time_estimation_a /sys/devices/platform/soc/*.ufshc/health_descriptor/life_time_estimation_b /sys/devices/platform/*ufshc*/health_descriptor/life_time_estimation_a /sys/devices/platform/*ufshc*/health_descriptor/life_time_estimation_b; do [ -r "$f" ] && echo "$f=$(cat "$f" 2>/dev/null)"; done';

const fmtGb = (kb) => (kb / 1024 / 1024).toFixed(1) + " GB";
const fmtBytes = (b) => (b >= 1024 ** 3 ? (b / 1024 ** 3).toFixed(1) + " GB" : (b / 1024 ** 2).toFixed(0) + " MB");

export async function renderStorage(view, { sh, getId }) {
  const state = { latency: null, freePct: null, life: null, speed: null, ioErr: null };
  const save = () => {
    const bad = [];
    const warn = [];
    const notes = [];
    if (state.latency != null) { notes.push(`latensi tulis ${state.latency} ms`); if (state.latency > 100) bad.push(1); else if (state.latency > 30) warn.push(1); }
    if (state.freePct != null) { notes.push(`${state.freePct}% kosong`); if (state.freePct < 5) bad.push(1); else if (state.freePct < 15) warn.push(1); }
    if (state.life != null) { notes.push(`umur flash ${lifeText(state.life)}`); if (state.life >= 9) bad.push(1); else if (state.life >= 7) warn.push(1); }
    if (state.speed != null) { notes.push(`tulis ${state.speed.toFixed(0)} MB/s`); if (state.speed < 15) bad.push(1); else if (state.speed < 50) warn.push(1); }
    if (state.ioErr != null) { notes.push(`${state.ioErr} error I/O di log`); if (state.ioErr > 0) bad.push(1); }
    if (!notes.length) return;
    saveTest(getId(), "storage", { name: "Penyimpanan", status: bad.length ? "FAIL" : warn.length ? "WARN" : "PASS", note: notes.join(", ") });
  };

  view.innerHTML = `
    <div class="card"><h2>Isi penyimpanan</h2><div id="sbox"><p class="muted">Membaca… bisa 5 sampai 15 detik.</p></div></div>
    <div class="cols">
      <section class="card"><h2>Umur memori flash</h2><div id="life"><p class="muted">Membaca…</p></div></section>
      <section class="card"><h2>Kecepatan tulis</h2>
        <p class="muted">Menulis file 64 MB sementara ke HP, mengukur waktunya, lalu menghapusnya. Memori yang rusak atau penuh akan terasa sangat lambat.</p>
        <div class="row"><button id="spd" class="primary">Mulai uji 64 MB</button></div><div id="spdout"></div></section>
      <section class="card"><h2>Error penyimpanan di log</h2>
        <p class="muted">Mencari pesan I/O error, kerusakan filesystem, dan "No space left" di 8.000 baris log terakhir.</p>
        <div class="row"><button id="err">Cari error</button></div><div id="errout"></div></section>
    </div>`;
  const $ = (s) => view.querySelector(s);

  // 1) isi penyimpanan
  (async () => {
    const [disk, df] = await Promise.all([sh("dumpsys diskstats"), sh("df -k /data")]);
    const d = parseDiskstats(disk);
    let freeKb = d.freeKb, totalKb = d.totalKb;
    if (totalKb == null) {
      const p = (df.split("\n").filter(Boolean).pop() || "").trim().split(/\s+/);
      if (num(p[1])) { totalKb = Number(p[1]); freeKb = Number(p[3]); }
    }
    const box = $("#sbox");
    if (!box) return;
    if (!totalKb) { box.innerHTML = `<p class="warn">HP tidak membuka data penyimpanan.</p>`; return; }
    state.freePct = Math.round((freeKb / totalKb) * 100);
    state.latency = d.latencyMs;
    const cats = CATS.map(([k, label]) => [label, k === "App" ? (d.sizes.App || 0) : (d.sizes[k] || 0)]).filter(([, v]) => v > 0);
    const used = cats.reduce((a, [, v]) => a + v, 0);
    const stack = cats.length
      ? `<div class="stack" role="img" aria-label="Pembagian isi penyimpanan">${cats.map(([l, v], i) => `<span class="c${i}" style="flex:${v}" title="${esc(l)}"></span>`).join("")}</div>
         <ul class="legend">${cats.map(([l, v], i) => `<li><i class="c${i}"></i>${esc(l)}<b>${fmtBytes(v)}</b></li>`).join("")}</ul>`
      : `<p class="muted">Rincian per jenis tidak tersedia di HP ini.</p>`;
    box.innerHTML = `<dl class="kv">
        <div><dt>Total</dt><dd>${fmtGb(totalKb)}</dd></div>
        <div><dt>Kosong</dt><dd>${fmtGb(freeKb)} (${state.freePct}%)</dd></div>
        <div><dt>Latensi tulis</dt><dd>${d.latencyMs == null ? "tidak terbaca" : d.latencyMs + " ms"}</dd></div>
      </dl>${stack}` +
      (state.freePct < 5 ? `<p class="fail">Hampir penuh. Ini sering menjadi penyebab HP lemot, aplikasi crash, dan gagal update.</p>` : state.freePct < 15 ? `<p class="warn">Ruang kosong sempit. Sisakan minimal 15% supaya HP lancar.</p>` : "") +
      (d.latencyMs != null && d.latencyMs > 100 ? `<p class="fail">Latensi tulis ${d.latencyMs} ms terlalu tinggi. Normalnya di bawah 30 ms. Curigai memori flash yang aus.</p>` : d.latencyMs != null && d.latencyMs > 30 ? `<p class="warn">Latensi tulis ${d.latencyMs} ms agak tinggi. Ulangi setelah mengosongkan memori.</p>` : "");
    save();
  })().catch(() => {});

  // 2) umur flash
  (async () => {
    const items = parseLife(await sh(LIFE_CMD));
    const box = $("#life");
    if (!box) return;
    if (!items.length) {
      box.innerHTML = `<p class="muted">HP ini tidak membuka data umur flash tanpa root. Itu normal untuk kebanyakan merek, dan bukan tanda kerusakan.</p>`;
      return;
    }
    const life = items.filter((i) => i.kind === "life").map((i) => i.n);
    state.life = life.length ? Math.max(...life) : null;
    box.innerHTML = `<dl class="kv">${items.map((i) => `<div><dt>${esc(i.label)}</dt><dd>${i.kind === "eol" ? ({ 1: "Normal", 2: "Peringatan (80% cadangan terpakai)", 3: "Kritis (90% cadangan terpakai)" }[i.n] || "Tidak diketahui") : esc(lifeText(i.n))}</dd></div>`).join("")}</dl>`;
    save();
  })().catch(() => {});

  // 3) kecepatan tulis
  $("#spd").onclick = async () => {
    const btn = $("#spd");
    const out = $("#spdout");
    btn.disabled = true;
    try {
      const free = (await sh("df -k /data")).split("\n").filter(Boolean).pop() || "";
      const avail = Number(free.trim().split(/\s+/)[3]);
      if (avail && avail < 300 * 1024) { out.innerHTML = `<p class="warn">Ruang kosong kurang dari 300 MB. Kosongkan dulu supaya uji aman.</p>`; return; }
      out.innerHTML = `<p class="muted">Menulis 64 MB…</p>`;
      const f = "/data/local/tmp/nexa_speed.bin";
      let t0 = performance.now();
      let raw = await sh(`dd if=/dev/zero of=${f} bs=1048576 count=64 conv=fsync 2>&1`);
      if (/bad|unknown|invalid|conv/i.test(raw) && !/copied/i.test(raw)) {
        t0 = performance.now();
        raw = await sh(`dd if=/dev/zero of=${f} bs=1048576 count=64 2>&1; sync`);
      }
      const wall = (performance.now() - t0) / 1000;
      await sh(`rm -f ${f}`);
      const mbps = parseSpeed(raw, wall);
      if (!mbps) { out.innerHTML = `<p class="warn">Hasil tidak terbaca.</p><pre>${esc(raw)}</pre>`; return; }
      state.speed = mbps;
      const cls = mbps >= 50 ? "pass" : mbps >= 15 ? "warn" : "fail";
      const msg = mbps >= 50 ? "Cepat. Memori sehat." : mbps >= 15 ? "Lambat untuk HP modern. Ulangi setelah mengosongkan memori." : "Sangat lambat. Curigai memori aus atau hampir penuh.";
      out.innerHTML = `<p class="${cls}"><b>${mbps.toFixed(0)} MB/s</b> tulis. ${msg}</p><p class="muted">Pembanding kasar: eMMC lama 30 sampai 100 MB/s, UFS di atas 200 MB/s.</p>`;
      save();
    } catch (e) {
      out.innerHTML = `<p class="fail">Gagal: ${esc(e?.message || e)}</p>`;
    } finally {
      btn.disabled = false;
    }
  };

  // 4) error di log
  $("#err").onclick = async () => {
    const btn = $("#err");
    const out = $("#errout");
    btn.disabled = true;
    out.innerHTML = `<p class="muted">Mencari…</p>`;
    try {
      const log = await sh("logcat -d -t 8000");
      const io = (log.match(/I\/O error|EXT4-fs error|f2fs[^\n]*(?:error|corrupt)|Input\/output error|mmc\d+:[^\n]*error/gi) || []).length;
      const full = (log.match(/No space left on device|ENOSPC/g) || []).length;
      state.ioErr = io;
      out.innerHTML = (io ? `<p class="fail"><b>${io} error I/O</b> ditemukan. Indikasi memori atau filesystem bermasalah.</p>` : `<p class="pass">Tidak ada error I/O di log terakhir.</p>`) +
        (full ? `<p class="warn">${full} pesan "No space left": memori sempat penuh.</p>` : "");
      save();
    } catch (e) {
      out.innerHTML = `<p class="fail">Gagal: ${esc(e?.message || e)}</p>`;
    } finally {
      btn.disabled = false;
    }
  };
}
