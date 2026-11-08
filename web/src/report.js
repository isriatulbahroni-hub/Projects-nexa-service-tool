const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

export function cmpTable(b, f) {
  const v = (s, k, u = "") => (s && s[k] != null ? `${k === "temp" ? Number(s[k]).toFixed(1) : s[k]}${u}` : "-");
  const row = (n, k, u) => `<tr><td>${n}</td><td>${v(b, k, u)}</td><td>${v(f, k, u)}</td></tr>`;
  return `<table><tr><th></th><th>Sebelum</th><th>Sesudah</th></tr>${row("Skor", "score")}${row("Baterai", "level", "%")}${row("Suhu baterai", "temp", " °C")}${row("Penyimpanan terpakai", "storage", "%")}${row("RAM bebas", "ram", "%")}</table>`;
}

export function buildReport({ shop, rows, a, before, after }) {
  const tgl = new Date().toLocaleString("id-ID", { dateStyle: "long", timeStyle: "short" });
  const finds = a.reasons.length
    ? `<ul>${a.reasons.map((r) => `<li><b>${esc(r.title)}</b>: ${esc(r.detail)}</li>`).join("")}</ul>`
    : `<p>Tidak ada temuan pada pemeriksaan otomatis.</p>`;
  return `<!doctype html><html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Laporan kondisi perangkat</title>
<style>body{font:16px/1.5 system-ui,sans-serif;max-width:720px;margin:24px auto;padding:0 16px;color:#17231f}h1{margin:0}h2{margin:24px 0 8px;font-size:1.1rem}
table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:7px 8px;border-bottom:1px solid #c3cbc4}th{color:#5b6a64;font-weight:500}
.v{display:inline-block;margin:8px 0;padding:6px 14px;border-left:6px solid ${a.level === "ok" ? "#1d7a5a" : a.level === "warn" ? "#e9b300" : "#b83224"};background:#f3f5f1}
.v b{font-size:1.6rem;margin-right:8px}small{color:#5b6a64}button{margin-top:20px;padding:10px 18px;font:inherit}@media print{.noprint{display:none}}</style></head><body>
<h1>${esc(shop || "Laporan kondisi perangkat")}</h1><small>${esc(tgl)}</small>
<div class="v"><b>${a.score}</b>${esc(a.verdict)}</div>
<h2>Data perangkat</h2><table>${rows.map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`).join("")}</table>
<h2>Temuan</h2>${finds}
${before && after ? `<h2>Sebelum dan sesudah servis</h2>${cmpTable(before, after)}` : ""}
<p><small>Laporan dibuat otomatis dari data baca-saja pada HP. Skor bersifat perkiraan dan tidak menguji layar, kamera, atau audio.</small></p>
<button class="noprint" onclick="window.print()">Cetak atau simpan PDF</button></body></html>`;
}
