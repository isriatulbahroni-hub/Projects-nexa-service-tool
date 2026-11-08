// Analisis log otomatis: membaca logcat, dropbox, dan alasan boot, lalu menyimpulkan kemungkinan penyebab.
// Aturannya berbasis pola teks, jadi hasilnya petunjuk untuk teknisi, bukan vonis.
import { esc, download } from "./kit.js";

const SYSTEM_PKG = /^(android|com\.android\.|com\.google\.android\.(gms|gsf|apps\.nexuslauncher)|com\.(miui|samsung|oppo|vivo|transsion|mediatek|huawei)\.)/;

export function parseDropbox(text) {
  const tags = {};
  for (const line of String(text || "").split("\n")) {
    const m = line.match(/^\s*\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\s+(\S+)\s+\((?:text|data|empty)/i);
    if (m) tags[m[1]] = (tags[m[1]] || 0) + 1;
  }
  return tags;
}

const bootMeaning = (r) => {
  const s = String(r || "").toLowerCase();
  if (!s) return null;
  if (/panic|kpanic/.test(s)) return { level: "bad", text: "Kernel panic: kernel berhenti karena error fatal. Penyebab umum: memori, firmware, atau board." };
  if (/watchdog|wdt/.test(s)) return { level: "bad", text: "Watchdog: sistem macet lalu direstart paksa." };
  if (/thermal|overheat|over_temp|temperature/.test(s)) return { level: "bad", text: "HP mati karena terlalu panas." };
  if (/battery|lowbat|low_batt/.test(s)) return { level: "warn", text: "HP mati karena baterai (habis atau tegangan jatuh)." };
  if (/cold|normal|userrequested|reboot$|shutdown$|\bpwrkey|power_key/.test(s)) return { level: "ok", text: "Boot terakhir normal (dinyalakan atau direstart biasa)." };
  return { level: "info", text: "Alasan boot tidak dikenali." };
};

export function analyze({ log = "", boot = "", dropbox = "" }) {
  const out = [];
  const add = (level, title, detail, tip) => out.push({ level, title, detail, tip });
  const n = (re) => (log.match(re) || []).length;

  // aplikasi crash dan ANR
  const crashes = {};
  for (const m of log.matchAll(/FATAL EXCEPTION[\s\S]{0,260}?Process:\s*([\w.]+),\s*PID/g)) crashes[m[1]] = (crashes[m[1]] || 0) + 1;
  for (const [pkg, c] of Object.entries(crashes).sort((a, b) => b[1] - a[1]).slice(0, 5)) {
    const sys = SYSTEM_PKG.test(pkg);
    if (c >= 3 || sys) add(sys && c >= 3 ? "bad" : "warn", `${pkg} berhenti mendadak ${c} kali`, sys ? "Aplikasi sistem ikut crash. Bisa dari update rusak atau data korup." : "Aplikasi ini sering crash di log terakhir.", sys ? "Hapus data atau cache aplikasi, atau flash ulang firmware bila terus berulang." : "Hapus data atau copot aplikasi di halaman Perbaikan, lalu uji lagi.");
  }
  const anrs = {};
  for (const m of log.matchAll(/ANR in ([\w.]+)/g)) anrs[m[1]] = (anrs[m[1]] || 0) + 1;
  for (const [pkg, c] of Object.entries(anrs).sort((a, b) => b[1] - a[1]).slice(0, 3)) add("warn", `${pkg} tidak merespons (ANR) ${c} kali`, "Aplikasi macet saat dipakai. Biasanya tanda memori penuh, RAM sempit, atau aplikasi berat.", "Bersihkan penyimpanan lalu coba lagi.");

  // crash native
  const native = {};
  for (const m of log.matchAll(/Fatal signal \d+ \(SIG\w+\)[^\n]*?>>>\s*(\S+)\s*<<</g)) native[m[1]] = (native[m[1]] || 0) + 1;
  for (const [p, c] of Object.entries(native).sort((a, b) => b[1] - a[1]).slice(0, 3)) add(c >= 3 ? "bad" : "warn", `Crash native pada ${p} (${c}x)`, "Crash tingkat rendah. Bisa dari driver, firmware, atau memori yang bermasalah.", "Kalau berulang pada banyak proses, curigai RAM atau firmware.");

  // sistem
  if (n(/WATCHDOG KILLING SYSTEM PROCESS|Watchdog:[^\n]*Blocked in/g)) add("bad", "Watchdog sistem terpicu", "Layanan inti sistem macet sampai Android direstart paksa.", "Sering terjadi saat memori flash rusak atau firmware korup.");
  const lmk = n(/lowmemorykiller|lmkd[^\n]*[Kk]ill|Low on memory/g);
  if (lmk > 40) add("warn", "RAM sering habis", `${lmk} catatan proses dimatikan karena RAM kurang.`, "Kurangi aplikasi latar belakang atau cek kondisi RAM.");
  const nospace = n(/No space left on device|ENOSPC/g);
  if (nospace) add("bad", "Penyimpanan penuh", `${nospace} pesan "No space left".`, "Kosongkan penyimpanan. Ini sering penyebab aplikasi crash dan gagal update.");
  const ioerr = n(/I\/O error|EXT4-fs error|f2fs[^\n]*(?:error|corrupt)|Input\/output error|mmc\d+:[^\n]*error/gi);
  if (ioerr) add("bad", "Error baca atau tulis memori", `${ioerr} pesan error penyimpanan.`, "Indikasi memori flash rusak. Backup data segera, lalu cek di halaman Penyimpanan.");
  if (n(/(?:thermal|Thermal)[^\n]*(?:SHUTDOWN|CRITICAL|EMERGENCY)|shutdown,thermal/g)) add("bad", "Suhu mencapai batas kritis", "Sistem sempat mencatat status panas kritis.", "Cek baterai kembung, charger, dan pasta termal bila HP pernah dibongkar.");
  if (n(/rild[^\n]*(?:died|crash|restart)|RIL[^\n]*died|Modem[^\n]*(?:crash|reset)|Radio[^\n]*crash/gi)) add("warn", "Modem sempat restart", "Layanan sinyal terputus atau restart di log.", "Cek SIM, IMEI, dan sinyal. Kalau berulang, curigai modem atau antena.");
  if (n(/CameraService[^\n]*(?:error|died|disconnect)|Camera(?:Device|Provider)[^\n]*(?:died|DEAD)|Failed to open camera/gi)) add("warn", "Kamera bermasalah", "Layanan kamera mencatat error atau terputus.", "Coba Uji Komponen lalu cek flexible dan modul kamera.");
  if (n(/GPU hang|gpu fault|SurfaceFlinger[^\n]*(?:timeout|hang)|Adreno[^\n]*(?:hang|fault)|Mali[^\n]*fault/gi)) add("warn", "Masalah tampilan atau GPU", "Ada catatan GPU hang atau timeout tampilan.", "Bisa dari driver, layar, atau panas berlebih.");

  // dropbox
  const d = parseDropbox(dropbox);
  const restarts = d.SYSTEM_RESTART || 0;
  if (restarts >= 3) add("bad", `Sistem restart ${restarts} kali`, "Dropbox mencatat restart sistem berulang. Pola ini mirip bootloop ringan.", "Cek alasan boot di bawah, lalu uji baterai dan penyimpanan.");
  if (d.system_server_crash) add("bad", `System server crash (${d.system_server_crash}x)`, "Inti Android pernah crash.", "Biasanya firmware korup atau memori bermasalah.");
  if (d.SYSTEM_TOMBSTONE) add("warn", `${d.SYSTEM_TOMBSTONE} tombstone (crash native)`, "Ada catatan crash tingkat rendah.", "Perhatikan kalau jumlahnya bertambah.");
  if (d.SYSTEM_LAST_KMSG) add("bad", "Ada catatan kernel dari boot sebelumnya", "Biasanya muncul setelah kernel panic.", "Cek alasan boot di bawah.");

  const bm = bootMeaning(boot);
  if (bm) add(bm.level, `Alasan boot terakhir: ${boot}`, bm.text, bm.level === "bad" ? "Cocokkan dengan temuan lain di atas." : undefined);

  const order = { bad: 0, warn: 1, info: 2, ok: 3 };
  out.sort((a, b) => order[a.level] - order[b.level]);
  const bad = out.filter((x) => x.level === "bad").length;
  const warn = out.filter((x) => x.level === "warn").length;
  if (!bad && !warn) add("ok", "Tidak ada pola kerusakan yang jelas", "Log terakhir tidak menunjukkan crash berulang, error memori, atau restart paksa.", "Kalau keluhan masih ada, ulangi analisis tepat setelah masalahnya terjadi.");
  return { findings: out, bad, warn };
}

export function toText(res, meta) {
  const head = `Analisis log Nexa Service Tool\n${meta}\n\n`;
  return head + res.findings.map((f) => `[${f.level.toUpperCase()}] ${f.title}\n  ${f.detail}${f.tip ? "\n  Saran: " + f.tip : ""}`).join("\n\n") + "\n";
}

export function renderAnalyzer(box, { sh }) {
  if (!box) return;
  box.innerHTML = `
    <div class="card"><h2>Analisis log otomatis</h2>
      <p class="muted">Membaca 8.000 baris log terakhir, catatan crash sistem, dan alasan boot, lalu merangkum kemungkinan penyebab. Jalankan tepat setelah masalahnya terjadi supaya jejaknya masih ada.</p>
      <div class="row">
        <button id="anGo" class="primary">Analisis sekarang</button>
        <button id="anLog">Unduh logcat lengkap (.txt)</button>
        <button id="anRep" disabled>Unduh hasil analisis (.txt)</button>
      </div>
      <div id="anOut"></div>
    </div>`;
  const $ = (s) => box.querySelector(s);
  let last = null;
  const stamp = () => new Date().toISOString().slice(0, 16).replace(/[:T]/g, "-");

  $("#anGo").onclick = async () => {
    const btn = $("#anGo");
    const out = $("#anOut");
    btn.disabled = true;
    out.innerHTML = `<p class="muted">Membaca log… bisa sampai 10 detik.</p>`;
    try {
      const [log, b1, b2, dropbox, model] = await Promise.all([
        sh("logcat -d -t 8000"),
        sh("getprop ro.boot.bootreason"),
        sh("getprop sys.boot.reason"),
        sh("dumpsys dropbox"),
        sh("getprop ro.product.model"),
      ]);
      if (!log) { out.innerHTML = `<p class="warn">Log kosong atau tidak bisa dibaca. Cabut dan colok kabel USB lalu coba lagi.</p>`; return; }
      const res = analyze({ log, boot: b1 || b2, dropbox });
      last = { res, meta: `${model || "HP"}, ${new Date().toLocaleString("id-ID")}` };
      $("#anRep").disabled = false;
      const lab = { bad: "Bermasalah", warn: "Perlu dicek", ok: "Baik", info: "Info" };
      out.innerHTML = `<p><b>${res.bad}</b> temuan serius, <b>${res.warn}</b> perlu dicek, dari ${log.split("\n").length.toLocaleString("id-ID")} baris log.</p>
        <ul class="rows">${res.findings.map((f) => `<li data-s="${f.level}"><span class="mk"></span><div>${esc(f.title)}<em>${esc(f.detail)}${f.tip ? " " + esc(f.tip) : ""}</em></div><span class="st">${lab[f.level]}</span></li>`).join("")}</ul>`;
    } catch (e) {
      out.innerHTML = `<p class="fail">Gagal: ${esc(e?.message || e)}</p>`;
    } finally {
      btn.disabled = false;
    }
  };
  $("#anLog").onclick = async () => {
    const btn = $("#anLog");
    btn.disabled = true;
    try {
      const log = await sh("logcat -d");
      if (!log) { $("#anOut").innerHTML = `<p class="warn">Log kosong atau tidak bisa dibaca.</p>`; return; }
      download(`logcat-${stamp()}.txt`, log);
    } finally { btn.disabled = false; }
  };
  $("#anRep").onclick = () => { if (last) download(`analisis-log-${stamp()}.txt`, toText(last.res, last.meta)); };
}
