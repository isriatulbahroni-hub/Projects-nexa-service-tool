// Halaman Servis dan Laporan: tiket servis, foto sebelum/sesudah, riwayat per HP, dan laporan siap cetak.
// PDF dibuat lewat dialog cetak browser (pilih "Simpan sebagai PDF"), jadi tanpa pustaka tambahan.
// Data tersimpan di browser ini saja (localStorage); gunakan Ekspor untuk cadangan.
import { esc, getTests, download } from "./kit.js";
import { cmpTable } from "./report.js";
import { listSnaps } from "./store.js";

const KEY = "nexa-tickets:v1";
const SHOP_KEY = "nexa-shop";
const STATUSES = ["Diterima", "Dikerjakan", "Selesai", "Sudah diambil"];
const MAX_PHOTOS = 3;
const FIELDS = ["customer", "phone", "model", "imei", "serial", "status", "complaint", "actions", "parts", "cost", "warranty", "notes"];
const TEST_ORDER = ["battery", "storage", "sensor", "camera", "audio", "display", "touch"];
const TEST_LABEL = { PASS: "Normal", WARN: "Perlu dicek", FAIL: "Bermasalah", INFO: "Info" };

// Foto hanya boleh berupa data URL gambar (hasil shrink() di bawah). Data dari file cadangan atau
// penyimpanan tidak dipercaya: nilai lain (mis. berisi tanda kutip atau "javascript:") ditolak,
// supaya tidak bisa menyisipkan atribut/script ke <img> di halaman ini maupun di laporan cetak.
const PHOTO_RE = /^data:image\/(?:jpeg|png|webp);base64,[A-Za-z0-9+/]+={0,2}$/;
const safePhoto = (s) => typeof s === "string" && s.length <= 400000 && PHOTO_RE.test(s);

// Bersihkan satu tiket dari file cadangan: hanya field yang dikenal, semuanya string pendek,
// status harus salah satu STATUSES, foto lolos safePhoto. Mengembalikan null kalau bukan tiket.
function cleanTicket(t) {
  if (!t || typeof t !== "object" || typeof t.id !== "string" || !t.id.trim()) return null;
  const out = { id: t.id.trim().slice(0, 40), createdAt: Number(t.createdAt) || 0, updatedAt: Number(t.updatedAt) || 0 };
  for (const n of FIELDS) if (t[n] != null) out[n] = String(t[n]).slice(0, 4000);
  if (out.status != null && !STATUSES.includes(out.status)) out.status = "Diterima";
  const ph = t.photos && typeof t.photos === "object" ? t.photos : {};
  out.photos = {
    before: (Array.isArray(ph.before) ? ph.before : []).filter(safePhoto).slice(0, MAX_PHOTOS),
    after: (Array.isArray(ph.after) ? ph.after : []).filter(safePhoto).slice(0, MAX_PHOTOS),
  };
  return out;
}

const loadTickets = () => {
  try { const v = JSON.parse(localStorage.getItem(KEY)); return Array.isArray(v) ? v : []; } catch { return []; }
};
const saveTickets = (list) => {
  try { localStorage.setItem(KEY, JSON.stringify(list)); return true; } catch { return false; }
};
const rupiah = (n) => "Rp " + (Number(String(n ?? "").replace(/\D/g, "")) || 0).toLocaleString("id-ID");
const tgl = (t) => new Date(t).toLocaleString("id-ID", { dateStyle: "long", timeStyle: "short" });
const tglPendek = (t) => new Date(t).toLocaleDateString("id-ID", { day: "numeric", month: "short", year: "numeric" });

function newId(list) {
  const d = new Date();
  const ymd = `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, "0")}${String(d.getDate()).padStart(2, "0")}`;
  let n = list.filter((t) => String(t.id).startsWith(`NX-${ymd}`)).length + 1;
  while (list.some((t) => t.id === `NX-${ymd}-${String(n).padStart(3, "0")}`)) n++;
  return `NX-${ymd}-${String(n).padStart(3, "0")}`;
}

const blank = (serial) => ({
  id: null, createdAt: 0, updatedAt: 0, status: "Diterima",
  customer: "", phone: "", model: "", imei: "", serial: serial || "",
  complaint: "", actions: "", parts: "", cost: "", warranty: "7", notes: "",
  photos: { before: [], after: [] },
});

// Foto dikecilkan supaya muat di penyimpanan browser (sekitar 50 sampai 90 KB per foto).
async function shrink(file, max = 720, quality = 0.65) {
  const bmp = await createImageBitmap(file);
  const s = Math.min(1, max / Math.max(bmp.width, bmp.height));
  const c = document.createElement("canvas");
  c.width = Math.round(bmp.width * s);
  c.height = Math.round(bmp.height * s);
  c.getContext("2d").drawImage(bmp, 0, 0, c.width, c.height);
  if (bmp.close) bmp.close();
  return c.toDataURL("image/jpeg", quality);
}

export function reportHtml(t, shop) {
  const sid = t.serial || "";
  const tests = getTests(sid);
  const testRows = TEST_ORDER.filter((k) => tests[k]).map((k) => {
    const x = tests[k];
    return `<tr><td>${esc(x.name || k)}</td><td class="s-${esc(x.status)}">${esc(TEST_LABEL[x.status] || x.status)}</td><td>${esc(x.note || "")}</td></tr>`;
  }).join("");
  const snaps = listSnaps(sid);
  const pick = (re) => [...snaps].reverse().find((s) => re.test(String(s.tag || "")));
  const before = pick(/before|sebelum/i);
  const after = pick(/after|sesudah/i);
  const gallery = (kind, label) => {
    const imgs = (t.photos && Array.isArray(t.photos[kind]) ? t.photos[kind] : []).filter(safePhoto);
    return imgs.length
      ? `<div class="pg"><h3>${label}</h3><div class="pgrid">${imgs.map((s) => `<img src="${esc(s)}" alt="">`).join("")}</div></div>` : "";
  };
  const garansi = Number(t.warranty) > 0
    ? `Garansi servis ${Number(t.warranty)} hari sejak tanggal selesai, berlaku untuk pekerjaan dan suku cadang yang tercantum di atas.`
    : "Tanpa garansi servis.";
  const row = (k, v) => `<tr><td>${esc(k)}</td><td>${esc(v || "-")}</td></tr>`;
  return `<!doctype html><html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(t.id || "Laporan servis")}</title>
<style>
@page{size:A4;margin:14mm}
*{box-sizing:border-box}
body{font:14px/1.5 system-ui,"Segoe UI",sans-serif;color:#17231f;max-width:760px;margin:0 auto;padding:20px 16px}
header{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;padding:16px 18px;background:#0f4c4a;color:#eaf3f0;border-radius:2px 2px 2px 22px}
header h1{margin:0;font-size:1.35rem;line-height:1.15}
header p{margin:2px 0 0;opacity:.85;font-size:.85rem}
header .no{text-align:right;font-weight:800;font-size:1.1rem;font-variant-numeric:tabular-nums}
h2{margin:20px 0 6px;font-size:1rem;border-left:4px solid #e9b300;padding-left:8px}
h3{margin:10px 0 4px;font-size:.9rem;color:#5b6a64}
table{width:100%;border-collapse:collapse}
td,th{text-align:left;padding:6px 8px;border-bottom:1px solid #c3cbc4;vertical-align:top}
th{color:#5b6a64;font-weight:500}
td:first-child{width:34%;color:#5b6a64}
.t3 td:first-child{width:auto;color:inherit}
.s-PASS{color:#1d7a5a;font-weight:700}.s-WARN{color:#8f6400;font-weight:700}.s-FAIL{color:#b83224;font-weight:700}
.box{background:#f3f5f1;padding:8px 10px;white-space:pre-wrap}
.pgrid{display:flex;gap:8px;flex-wrap:wrap}.pgrid img{width:31%;aspect-ratio:1;object-fit:cover;border:1px solid #c3cbc4}
.pg{break-inside:avoid}
.sign{display:grid;grid-template-columns:1fr 1fr;gap:40px;margin-top:36px;text-align:center}
.sign div{padding-top:52px;border-top:1px solid #17231f}
small{color:#5b6a64}
button{margin-top:18px;padding:10px 18px;font:inherit}
@media print{.noprint{display:none}body{padding:0}}
</style></head><body>
<header><div><h1>${esc(shop || "Laporan servis")}</h1><p>Laporan servis perangkat</p></div><div class="no">${esc(t.id || "Draf")}<p>${esc(tgl(t.updatedAt || Date.now()))}</p></div></header>
<h2>Pelanggan dan perangkat</h2>
<table>${row("Nama pelanggan", t.customer)}${row("No. HP", t.phone)}${row("Merek dan model", t.model)}${row("IMEI", t.imei)}${row("Serial USB", t.serial)}${row("Status", t.status)}</table>
<h2>Keluhan</h2><div class="box">${esc(t.complaint || "-")}</div>
${testRows ? `<h2>Hasil pemeriksaan</h2><table class="t3"><tr><th>Pemeriksaan</th><th>Hasil</th><th>Catatan</th></tr>${testRows}</table>` : ""}
${before && after ? `<h2>Sebelum dan sesudah servis</h2>${cmpTable(before, after)}` : ""}
<h2>Tindakan</h2><div class="box">${esc(t.actions || "-")}</div>
<table style="margin-top:8px">${row("Suku cadang", t.parts)}${row("Biaya", rupiah(t.cost))}</table>
${t.notes ? `<h2>Catatan teknisi</h2><div class="box">${esc(t.notes)}</div>` : ""}
${gallery("before", "Foto sebelum servis")}${gallery("after", "Foto sesudah servis")}
<p><small>${esc(garansi)}</small></p>
<div class="sign"><div>Teknisi</div><div>Pelanggan</div></div>
<button class="noprint" onclick="window.print()">Cetak atau simpan sebagai PDF</button>
</body></html>`;
}

function openReport(t) {
  const html = reportHtml(t, localStorage.getItem(SHOP_KEY) || "");
  const url = URL.createObjectURL(new Blob([html], { type: "text/html" }));
  const w = window.open(url, "_blank");
  if (!w) alert("Pop-up diblokir. Izinkan pop-up untuk situs ini, lalu coba lagi.");
  setTimeout(() => URL.revokeObjectURL(url), 120000);
}

export async function renderService(view, { sh, getId, connected }) {
  let cur = blank(getId());
  view.innerHTML = `
    <div class="sv">
      <section class="card">
        <h2>Tiket servis</h2>
        <p class="muted" id="sv-meta"></p>
        <div class="fg">
          <label>Nama pelanggan<input name="customer" autocomplete="off" /></label>
          <label>No. HP atau WhatsApp<input name="phone" inputmode="tel" autocomplete="off" /></label>
          <label>Merek dan model<input name="model" /></label>
          <label>IMEI<input name="imei" inputmode="numeric" maxlength="17" placeholder="Ketik *#06# di HP" /></label>
          <label>Serial USB<input name="serial" /></label>
          <label>Status<select name="status">${STATUSES.map((s) => `<option>${s}</option>`).join("")}</select></label>
          <label class="wide">Keluhan pelanggan<textarea name="complaint" rows="2"></textarea></label>
          <label class="wide">Tindakan yang dilakukan<textarea name="actions" rows="2"></textarea></label>
          <label>Suku cadang<input name="parts" placeholder="mis. baterai, LCD" /></label>
          <label>Biaya (Rp)<input name="cost" inputmode="numeric" /></label>
          <label>Garansi servis (hari)<input name="warranty" inputmode="numeric" /></label>
          <label class="wide">Catatan teknisi<textarea name="notes" rows="2"></textarea></label>
        </div>
        <h3 class="sub">Foto sebelum servis</h3>
        <div class="ph" id="ph-before"></div>
        <div class="row"><input type="file" id="fb" accept="image/*" multiple /></div>
        <h3 class="sub">Foto sesudah servis</h3>
        <div class="ph" id="ph-after"></div>
        <div class="row"><input type="file" id="fa" accept="image/*" multiple /></div>
        <p class="muted">Maksimal ${MAX_PHOTOS} foto per bagian. Foto dikecilkan otomatis.</p>
        <div class="row">
          <button id="sv-save" class="primary">Simpan tiket</button>
          <button id="sv-print">Cetak laporan / PDF</button>
          <button id="sv-new">Tiket baru</button>
          <button id="sv-del" class="danger" hidden>Hapus tiket</button>
        </div>
      </section>
      <section class="card">
        <h2>Daftar tiket</h2>
        <p class="muted" id="sv-hist"></p>
        <div class="fg">
          <label class="wide">Cari (nama, nomor, model, IMEI)<input id="sv-q" autocomplete="off" /></label>
          <label class="wide">Nama toko di laporan<input id="sv-shop" autocomplete="off" /></label>
        </div>
        <ul class="tl" id="sv-list"></ul>
        <div class="row">
          <button id="sv-export">Ekspor cadangan (.json)</button>
          <button id="sv-import">Impor cadangan</button>
          <input type="file" id="sv-imp" accept=".json,application/json" hidden />
        </div>
        <p class="muted">Data tersimpan di browser ini saja. Ekspor cadangan secara berkala, terutama sebelum membersihkan data browser.</p>
      </section>
    </div>`;

  const $ = (s) => view.querySelector(s);
  const f = (n) => view.querySelector(`[name="${n}"]`);
  $("#sv-shop").value = localStorage.getItem(SHOP_KEY) || "";
  $("#sv-shop").onchange = (e) => { try { localStorage.setItem(SHOP_KEY, e.target.value.trim()); } catch {} };

  const meta = () => {
    $("#sv-meta").textContent = cur.id ? `${cur.id}, dibuat ${tgl(cur.createdAt)}` : "Tiket baru. Nomor dibuat saat disimpan.";
    $("#sv-del").hidden = !cur.id;
  };
  const drawPhotos = () => {
    for (const kind of ["before", "after"]) {
      const box = $(`#ph-${kind}`);
      const label = kind === "before" ? "sebelum" : "sesudah";
      box.innerHTML = cur.photos[kind].length
        ? cur.photos[kind].map((src, i) => `<figure><img src="${esc(src)}" alt="Foto ${label} ${i + 1}" /><button type="button" class="x" data-rm="${kind}:${i}" aria-label="Hapus foto ${label} ${i + 1}">×</button></figure>`).join("")
        : `<p class="muted">Belum ada foto.</p>`;
    }
  };
  const collect = () => { for (const n of FIELDS) cur[n] = f(n).value.trim(); return cur; };
  const fill = (t) => {
    const ph = (k) => (t.photos && Array.isArray(t.photos[k]) ? t.photos[k] : []).filter(safePhoto);
    cur = { ...blank(getId()), ...t, photos: { before: ph("before"), after: ph("after") } };
    for (const n of FIELDS) f(n).value = cur[n] == null ? "" : cur[n];
    $("#fb").value = "";
    $("#fa").value = "";
    drawPhotos();
    meta();
  };

  const drawList = () => {
    const q = ($("#sv-q").value || "").toLowerCase().trim();
    const all = loadTickets().sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0));
    const sid = getId();
    const mine = sid ? all.filter((t) => t.serial === sid).length : 0;
    $("#sv-hist").textContent = sid
      ? `${all.length} tiket tersimpan. HP yang tersambung punya ${mine} riwayat servis.`
      : `${all.length} tiket tersimpan.`;
    const shown = all.filter((t) => !q || [t.id, t.customer, t.phone, t.model, t.imei, t.serial].join(" ").toLowerCase().includes(q)).slice(0, 60);
    $("#sv-list").innerHTML = shown.length
      ? shown.map((t) => `<li><div><b>${esc(t.id)}</b> ${esc(t.customer || "Tanpa nama")}<em>${esc(t.model || "Model belum diisi")}, ${esc(t.status)}, ${esc(tglPendek(t.updatedAt || t.createdAt))}${sid && t.serial === sid ? ", HP ini" : ""}</em></div>
          <div class="row"><button data-open="${esc(t.id)}">Buka</button><button data-print="${esc(t.id)}">Cetak</button></div></li>`).join("")
      : `<li><span class="muted">${q ? "Tidak ada tiket yang cocok." : "Belum ada tiket. Isi formulir lalu tekan Simpan tiket."}</span></li>`;
  };

  const commit = () => {
    collect();
    if (!cur.customer && !cur.model) { alert("Isi minimal nama pelanggan atau model HP."); return null; }
    const list = loadTickets();
    const now = Date.now();
    const draft = { ...cur, photos: { before: [...cur.photos.before], after: [...cur.photos.after] } };
    if (!draft.id) { draft.id = newId(list); draft.createdAt = now; }
    draft.updatedAt = now;
    const i = list.findIndex((x) => x.id === draft.id);
    if (i >= 0) list[i] = draft; else list.push(draft);
    if (!saveTickets(list)) { alert("Penyimpanan browser penuh. Hapus tiket lama atau kurangi foto, lalu simpan lagi."); return null; }
    cur = draft;
    meta();
    drawList();
    return cur;
  };

  const addPhotos = async (kind, files) => {
    for (const file of files) {
      if (cur.photos[kind].length >= MAX_PHOTOS) break;
      try { cur.photos[kind].push(await shrink(file)); } catch {}
    }
    drawPhotos();
  };
  $("#fb").onchange = (e) => addPhotos("before", [...e.target.files]);
  $("#fa").onchange = (e) => addPhotos("after", [...e.target.files]);
  $("#sv-q").oninput = drawList;

  view.onclick = (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    if (b.dataset.rm) {
      const [kind, i] = b.dataset.rm.split(":");
      cur.photos[kind].splice(Number(i), 1);
      drawPhotos();
    } else if (b.dataset.open) {
      const t = loadTickets().find((x) => x.id === b.dataset.open);
      if (t) { fill(t); window.scrollTo({ top: 0, behavior: "smooth" }); }
    } else if (b.dataset.print) {
      const t = loadTickets().find((x) => x.id === b.dataset.print);
      if (t) openReport(t);
    } else if (b.id === "sv-save") {
      if (commit()) b.textContent = "Tersimpan";
      setTimeout(() => { b.textContent = "Simpan tiket"; }, 1400);
    } else if (b.id === "sv-print") {
      const t = commit();
      if (t) openReport(t);
    } else if (b.id === "sv-new") {
      fill(blank(getId()));
    } else if (b.id === "sv-del") {
      if (cur.id && confirm(`Hapus tiket ${cur.id}? Tindakan ini tidak bisa dibatalkan.`)) {
        saveTickets(loadTickets().filter((x) => x.id !== cur.id));
        fill(blank(getId()));
        drawList();
      }
    } else if (b.id === "sv-export") {
      const stamp = new Date().toISOString().slice(0, 10);
      download(`tiket-servis-${stamp}.json`, JSON.stringify(loadTickets()), "application/json");
    } else if (b.id === "sv-import") {
      $("#sv-imp").click();
    }
  };

  $("#sv-imp").onchange = async (e) => {
    const file = e.target.files && e.target.files[0];
    if (!file) return;
    try {
      const incoming = JSON.parse(await file.text());
      if (!Array.isArray(incoming)) throw new Error("format");
      const map = new Map(loadTickets().map((t) => [t.id, t]));
      let added = 0;
      for (const raw of incoming) {
        // isi file cadangan tidak dipercaya: hanya field dikenal yang masuk, foto divalidasi
        const t = cleanTicket(raw);
        if (!t) continue;
        const old = map.get(t.id);
        if (!old || (t.updatedAt || 0) > (old.updatedAt || 0)) { map.set(t.id, t); added++; }
      }
      if (!saveTickets([...map.values()])) throw new Error("penuh");
      drawList();
      alert(`${added} tiket diimpor.`);
    } catch {
      alert("File cadangan tidak valid atau penyimpanan browser penuh.");
    }
    e.target.value = "";
  };

  fill(blank(getId()));
  drawList();

  // isi model otomatis dari HP yang tersambung
  if (connected()) {
    try {
      const m = [await sh("getprop ro.product.brand"), await sh("getprop ro.product.model")].map((s) => s.trim()).filter(Boolean).join(" ");
      if (m && !f("model").value) f("model").value = m;
    } catch {}
  }
  return () => { view.onclick = null; };
}
