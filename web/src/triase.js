import "./triase.css";

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// Nama vendor dari kode USB (indikasi saja, bukan kepastian).
const VENDORS = {
  0x18d1: "Google", 0x04e8: "Samsung", 0x2717: "Xiaomi", 0x22d9: "OPPO atau realme", 0x2a70: "OnePlus",
  0x12d1: "Huawei", 0x0bb4: "HTC", 0x19d2: "ZTE", 0x1004: "LG", 0x0fce: "Sony", 0x2d95: "vivo",
  0x05c6: "Qualcomm", 0x0e8d: "MediaTek", 0x1782: "Spreadtrum atau Unisoc", 0x0b05: "ASUS", 0x22b8: "Motorola",
};

const MODES = {
  adb: { level: "ok", label: "Mode normal dengan ADB", meaning: "HP menyala dan menawarkan antarmuka ADB.",
    steps: ["Aktifkan USB debugging dan izinkan komputer di layar HP jika diminta.", "Tekan Hubungkan HP (USB) di bagian atas, lalu pakai Dashboard."] },
  fastboot: { level: "warn", label: "Fastboot (bootloader)", meaning: "HP berhenti di bootloader. Bisa disengaja, bisa juga karena sistem gagal boot.",
    steps: ["Alat ini tidak mengirim perintah apa pun ke mode ini.", "Untuk keluar: tahan tombol power sekitar 10 sampai 20 detik, atau jalankan fastboot reboot dari komputer.", "Jika selalu kembali ke fastboot, kemungkinan sistem atau partisi boot bermasalah."] },
  edl: { level: "bad", label: "Qualcomm EDL (9008)", meaning: "Mode darurat chip Qualcomm. Biasanya muncul saat bootloader rusak atau HP dipaksa masuk.",
    steps: ["Pemulihan butuh firmware dan programmer yang cocok dengan tipe HP, dan banyak merek mewajibkan otorisasi pabrikan.", "Gunakan alat dan layanan resmi merek tersebut. Alat web ini tidak bisa melakukannya.", "Jangan memakai file dari sumber yang tidak jelas."] },
  mtk: { level: "bad", label: "MediaTek BROM atau Preloader", meaning: "Mode level rendah chip MediaTek. Preloader normal muncul sebentar saat HP dinyalakan.",
    steps: ["Jika terus muncul tanpa HP boot, firmware atau memori kemungkinan rusak.", "Pemulihan lewat flash firmware resmi dengan alat flash yang sesuai. Alat web ini tidak melakukannya.", "Pastikan baterai terisi dan kabel bagus sebelum flash."] },
  samsungdl: { level: "warn", label: "Samsung Download Mode", meaning: "Mode untuk flash firmware lewat Odin. Bukan kerusakan dengan sendirinya.",
    steps: ["Untuk keluar umumnya tahan Volume Bawah dan Power sekitar 10 detik.", "Jika terus kembali ke layar ini atau muncul peringatan, firmware kemungkinan bermasalah."] },
  spd: { level: "warn", label: "Spreadtrum atau Unisoc (mode boot)", meaning: "Mode boot chip Unisoc.",
    steps: ["Pemulihan butuh firmware dan alat flash yang sesuai dengan tipe HP."] },
  unknown: { level: "warn", label: "Mode tidak dikenali", meaning: "Kode USB ini tidak ada di daftar alat.",
    steps: ["Catat kode vendor dan produk di atas, lalu cari di dokumentasi merek atau forum teknisi.", "Coba kabel dan port lain, lalu deteksi ulang."] },
};
const STATUS = { ok: "Normal", warn: "Perlu tindakan", bad: "Mode darurat" };

export function classify({ vendorId: v, productId: p, interfaces = [] }) {
  const has = (sub, proto) => interfaces.some((i) => i.cls === 0xff && i.sub === sub && i.proto === proto);
  if (has(0x42, 0x01)) return "adb";
  if (has(0x42, 0x03)) return "fastboot";
  if (v === 0x05c6 && p === 0x9008) return "edl";
  if (v === 0x0e8d && [0x0003, 0x2000, 0x2001].includes(p)) return "mtk";
  if (v === 0x04e8 && p === 0x685d) return "samsungdl";
  if (v === 0x1782 && p === 0x4d00) return "spd";
  return "unknown";
}

function ownerForm() {
  const line = (t) => `<p>${t}: ______________________________________________</p>`;
  const box = (t) => `<p>&#9633; ${t}</p>`;
  return `<!doctype html><html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Formulir verifikasi kepemilikan</title>
<style>body{font:16px/1.6 system-ui,sans-serif;max-width:720px;margin:24px auto;padding:0 16px;color:#17231f}h1{margin:0 0 4px}h2{margin:22px 0 6px;font-size:1.1rem}p{margin:6px 0}small{color:#5b6a64}
.sig{display:flex;gap:40px;margin-top:40px}.sig div{flex:1;border-top:1px solid #17231f;padding-top:6px}button{margin-top:24px;padding:10px 18px;font:inherit}@media print{.noprint{display:none}}</style></head><body>
<h1>Formulir verifikasi kepemilikan dan persetujuan</h1><small>Isi dengan tulisan tangan atau cetak lalu isi.</small>
${line("Nama toko")}${line("Tanggal")}
<h2>Data pemilik</h2>${line("Nama pemilik")}${line("Kontak")}
<h2>Data HP</h2>${line("Merek dan model")}${line("IMEI (dari dus, label, atau *#06#)")}
<h2>Bukti kepemilikan yang diperlihatkan</h2>
${box("Nota atau bukti pembelian")}${box("Dus dengan IMEI yang cocok")}${box("Akun terdaftar atas nama pemilik dan pemilik dapat membuktikannya")}${box("Identitas pemilik")}
<h2>Pernyataan</h2>
<ol><li>Saya menyatakan HP ini milik saya dan saya berhak meminta layanan ini.</li>
<li>Saya paham reset pabrik dapat menghapus seluruh data, dan data tanpa cadangan tidak dapat dikembalikan.</li>
<li>Saya paham setelah reset, HP dapat meminta akun yang sebelumnya terdaftar sebagai perlindungan perangkat, dan toko tidak bertanggung jawab atas akun yang saya lupa.</li>
<li>Saya paham toko hanya memakai jalur resmi pabrikan dan tidak membuka akses di luar jalur tersebut.</li></ol>
<div class="sig"><div>Pemilik</div><div>Teknisi</div></div>
<p><small>Formulir contoh, sesuaikan dengan kebijakan toko. Aplikasi tidak menyimpan isi formulir.</small></p>
<button class="noprint" onclick="window.print()">Cetak atau simpan PDF</button></body></html>`;
}

export function renderTriase(view, { go }) {
  view.innerHTML = `
    <div class="card"><h2>Deteksi mode USB</h2>
      <p>Colokkan HP yang bermasalah, lalu tekan tombol dan pilih perangkatnya. Alat ini hanya membaca identitas USB dan tidak mengirim perintah apa pun ke HP.</p>
      <div class="row"><button id="tDetect" class="primary">Deteksi perangkat USB</button></div>
      <div id="tOut"></div></div>
    <details><summary>HP tidak terdeteksi sama sekali</summary>
      <ol><li>Isi daya minimal 30 menit dengan charger dan kabel yang pasti baik, lalu coba port lain.</li>
      <li>Perhatikan lampu indikator, getar, atau logo saat dicolok.</li>
      <li>Pakai USB meter bila ada. Arus 0 mA dari awal mengarah ke konektor atau IC charging. Arus ada tapi HP tidak menyala mengarah ke baterai, papan, atau software.</li>
      <li>Tahan tombol power 20 sampai 30 detik, lalu coba kombinasi tombol recovery atau download milik merek tersebut.</li>
      <li>Periksa bekas jatuh atau terkena air sebelum membongkar.</li></ol></details>
    <details><summary>HP bootloop atau macet di logo</summary>
      <p>Jika HP sempat terdeteksi ADB, buka Terminal dan Log lalu jalankan Crash log untuk melihat penyebabnya.</p>
      <div class="row"><button id="tLog">Buka Terminal &amp; Log</button></div></details>
    <details><summary>HP menyala tapi pemilik lupa password</summary>
      <ol><li>Tanyakan akun yang terdaftar di HP (Google, Samsung, Xiaomi, OPPO atau realme, vivo). Dari akun itu pemilik bisa memakai fitur Cari Perangkat resmi merek untuk menghapus atau membuka kunci dari jarak jauh, bila HP online.</li>
      <li>Jika tidak bisa, arahkan ke service center resmi dengan bukti kepemilikan.</li>
      <li>Jika pemilik setuju reset pabrik, jelaskan bahwa data hilang. Setelah reset, HP bisa meminta akun lama sebagai proteksi perangkat.</li>
      <li>Catat IMEI dan bukti kepemilikan. Tolak bila bukti tidak ada atau mencurigakan, dan jangan memakai alat bypass.</li></ol>
      <div class="row"><button id="tForm">Buat formulir verifikasi kepemilikan</button></div></details>`;
  const q = (s) => view.querySelector(s);
  q("#tLog").onclick = () => go("terminal");
  q("#tForm").onclick = () => window.open(URL.createObjectURL(new Blob([ownerForm()], { type: "text/html" })), "_blank");
  q("#tDetect").onclick = async () => {
    const out = q("#tOut");
    if (!navigator.usb) { out.innerHTML = `<p class="fail">Browser ini tidak mendukung WebUSB. Pakai Chrome atau Edge.</p>`; return; }
    try {
      const d = await navigator.usb.requestDevice({ filters: [] });
      const interfaces = d.configurations.flatMap((c) => c.interfaces.flatMap((i) => i.alternates.map((a) => ({ cls: a.interfaceClass, sub: a.interfaceSubclass, proto: a.interfaceProtocol }))));
      const m = MODES[classify({ vendorId: d.vendorId, productId: d.productId, interfaces })];
      const hex = (n) => n.toString(16).padStart(4, "0");
      const who = VENDORS[d.vendorId] ? `${VENDORS[d.vendorId]}, ` : "";
      out.innerHTML = `<ul class="rows"><li data-s="${m.level}"><span class="mk"></span><div>${esc(m.label)}<em>${esc(who)}kode ${hex(d.vendorId)}:${hex(d.productId)}${d.productName ? ", " + esc(d.productName) : ""}</em></div><span class="st">${STATUS[m.level]}</span></li></ul>
        <p>${esc(m.meaning)}</p><ol>${m.steps.map((s) => `<li>${esc(s)}</li>`).join("")}</ol>
        <p class="muted">Daftar kode vendor dan mode ini indikasi dan bisa meleset pada model tertentu.</p>`;
    } catch (e) {
      out.innerHTML = e.name === "NotFoundError"
        ? `<p class="muted">Tidak ada perangkat yang dipilih. Jika daftar kosong, lihat bagian HP tidak terdeteksi di bawah.</p>`
        : `<p class="fail">${esc(e.message || e)}</p>`;
    }
  };
}
