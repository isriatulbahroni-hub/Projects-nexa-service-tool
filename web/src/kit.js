// Alat bantu bersama untuk halaman Baterai, Uji Komponen, Penyimpanan, Servis, dan Analisis log.

export const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// Kutip tunggal: aman untuk karakter apa pun ($, `, ;, spasi, dll.) di sh.
export const sq = (v) => `'${String(v).replace(/'/g, `'\\''`)}'`;

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export const num = (v) => {
  const s = String(v ?? "").trim();
  if (!s) return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
};

export const CLS = { PASS: "pass", WARN: "warn", FAIL: "fail", INFO: "info" };
export const LABEL = { PASS: "Normal", WARN: "Perlu dicek", FAIL: "Bermasalah", INFO: "Belum diuji" };

export function download(name, text, type = "text/plain;charset=utf-8") {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type }));
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 4000);
}

// Papan 20 segmen; warna mengikuti ambang (ok >= warn, warn >= bad, selebihnya bad).
export function gauge(pct, { warn = 80, bad = 60 } = {}) {
  const on = Math.max(0, Math.min(20, Math.round((pct ?? 0) / 5)));
  const tone = pct == null ? "" : pct >= warn ? "ok" : pct >= bad ? "warn" : "bad";
  const cells = Array.from({ length: 20 }, (_, i) => `<i${i < on ? ' class="on"' : ""}></i>`).join("");
  return `<div class="gg" data-t="${tone}" role="img" aria-label="${pct == null ? "tidak ada data" : pct + " persen"}">${cells}</div>`;
}

// Grafik garis kecil (SVG), bentuknya sama dengan pantauan di Dashboard.
export function spark(title, arr, unit = "", { max = 40, lo, hi, digits = 0 } = {}) {
  const last = arr[arr.length - 1];
  let pts = "";
  if (arr.length > 1) {
    const min = lo ?? Math.min(...arr) - 1;
    const top = hi ?? Math.max(...arr) + 1;
    pts = arr
      .map((v, i) => `${((i / (max - 1)) * 200).toFixed(1)},${(48 - ((v - min) / (top - min || 1)) * 44).toFixed(1)}`)
      .join(" ");
  }
  const line = pts ? `<polyline points="${pts}" fill="none" stroke="currentColor" stroke-width="2" vector-effect="non-scaling-stroke"/>` : "";
  return `<div class="spark"><small>${esc(title)}</small> <b>${last != null ? Number(last).toFixed(digits) + unit : "-"}</b>` +
    `<svg viewBox="0 0 200 50" preserveAspectRatio="none" role="img" aria-label="${esc(title)}">${line}</svg>` +
    `${arr.length < 2 ? "<small>Mengumpulkan data…</small>" : ""}</div>`;
}

// Hasil uji per HP, disimpan di browser ini dan dipakai laporan servis.
const tkey = (id) => `nexa-tests:${id || "unknown"}`;

export function getTests(id) {
  try { return JSON.parse(localStorage.getItem(tkey(id))) || {}; } catch { return {}; }
}

export function saveTest(id, key, data) {
  const all = getTests(id);
  all[key] = { ...data, t: Date.now() };
  try { localStorage.setItem(tkey(id), JSON.stringify(all)); } catch {}
}
