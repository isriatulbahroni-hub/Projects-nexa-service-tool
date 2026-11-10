// Uji manual / interaktif untuk halaman Hardware Test (versi web).
// Pemeriksaan otomatis di main.js hanya membaca data; komponen seperti getaran, suara,
// layar, dan tombol fisik harus dirasakan atau ditekan langsung oleh teknisi.

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
// Pola pesan galat dari perintah shell Android. "can't find service" muncul di HP yang tidak punya
// layanan itu (mis. vibrator_manager di Android 11 ke bawah) dan dulu lolos sebagai "berhasil".
const BAD = /unknown|usage|error|exception|not found|inaccessible|no such|permission|denied|invalid|unsupported|can't find|cannot find|not exist|aborted|no service/i;

// Semua panggilan ke HP diberi batas waktu supaya satu perintah macet tidak mengunci semua tombol.
function withTimeout(promise, ms, message) {
  let t;
  return Promise.race([
    promise,
    new Promise((_, reject) => { t = setTimeout(() => reject(new Error(message)), ms); }),
  ]).finally(() => clearTimeout(t));
}

const snippet = (s, n = 100) => String(s ?? "").trim().split("\n")[0].slice(0, n) || "(kosong)";

const TESTS = [
  {
    id: "vib",
    name: "Getaran (motor vibrator)",
    hint: "Pegang HP lalu rasakan getarannya. Lepas casing kalau perlu.",
    actions: [["short", "Getar 1 detik"], ["pattern", "Pola 3×"], ["phone", "Uji di layar HP"]],
    confirm: true,
  },
  {
    id: "snd",
    name: "Suara (speaker)",
    hint: "Memunculkan notifikasi uji. Pastikan HP tidak mode senyap dan volume notifikasi tidak nol.",
    actions: [["play", "Bunyikan"], ["phone", "Uji di layar HP"]],
    confirm: true,
  },
  {
    id: "bri",
    name: "Kecerahan layar",
    hint: "Layar akan terang penuh, redup, lalu kembali ke pengaturan semula.",
    actions: [["run", "Uji terang–redup"]],
    confirm: true,
  },
  {
    id: "key",
    name: "Tombol fisik (Vol+, Vol−, Power)",
    hint: "Tekan tombol yang diminta dalam 8 detik. Layar bisa mati saat Power ditekan.",
    actions: [["run", "Mulai uji tombol"]],
    confirm: false,
  },
  {
    id: "usb",
    name: "Port USB / pengisian",
    hint: "Membaca status daya dari kabel yang sedang terpasang.",
    actions: [["run", "Cek"], ["phone", "Uji di layar HP"]],
    confirm: true,
  },
];

// Hash kartu di halaman /hwtest.html yang dibuka di HP.
const PHONE_HASH = { vib: "getar", snd: "bunyi", usb: "usb" };
// Layar pengaturan Android yang dibuka lewat ADB (daftar tetap, bukan input bebas).
const SETTINGS = {
  bt: "android.settings.BLUETOOTH_SETTINGS",
  nfc: "android.settings.NFC_SETTINGS",
  loc: "android.settings.LOCATION_SOURCE_SETTINGS",
  sec: "android.settings.SECURITY_SETTINGS",
};

const CLS = { PASS: "pass", WARN: "warn", FAIL: "fail", INFO: "info" };

// ---------------------------------------------------------------
// Getaran
// ---------------------------------------------------------------
// Sintaks berbeda antar versi Android; coba berurutan sampai salah satu diterima.
const vibCommands = (ms) => [
  `cmd vibrator_manager synced -f oneshot ${ms}`,
  `cmd vibrator_manager synced -f oneshot -a ${ms} 255`,
  `cmd vibrator_manager synced -f -d nexa oneshot ${ms}`,
  `cmd vibrator vibrate -f ${ms} nexa`,
  `cmd vibrator vibrate ${ms} nexa`,
];

let lastVibCmdIndex = 0;
async function vibrate(sh, ms) {
  const cmds = vibCommands(ms);
  // mulai dari perintah yang terakhir berhasil
  const order = [...cmds.slice(lastVibCmdIndex), ...cmds.slice(0, lastVibCmdIndex)];
  const tried = [];
  for (const c of order) {
    const out = await sh(c);
    if (!BAD.test(out)) {
      lastVibCmdIndex = cmds.indexOf(c);
      return { ok: true, cmd: c };
    }
    tried.push(snippet(out, 80));
  }
  return { ok: false, tried };
}

async function vibratorInfo(sh) {
  const list = await sh("cmd vibrator_manager list");
  const dump = await sh("dumpsys vibrator_manager | head -30");
  const sys = await sh("ls /sys/class/timed_output /sys/class/leds/vibrator 2>/dev/null");
  return [`# cmd vibrator_manager list\n${list || "(kosong)"}`, `# dumpsys vibrator_manager\n${dump || "(kosong)"}`, `# /sys\n${sys || "(tidak ada)"}`].join("\n\n");
}

// ---------------------------------------------------------------
// Render
// ---------------------------------------------------------------
export function renderManualTests(root, { sh: rawSh, esc }) {
  if (!root) return;

  // sh bawaan main.js menelan semua galat dan mengembalikan "" (sama dengan "berhasil tanpa output").
  // Bungkus dengan batas waktu, lalu cek dulu bahwa HP benar-benar menjawab sebelum tiap uji.
  const sh = (cmd, ms = 8000) =>
    withTimeout(Promise.resolve(rawSh(cmd)), ms, `HP tidak merespons (${String(cmd).split(" ")[0]}).`);
  const ensureLink = async () => {
    const pong = String(await sh("echo nexa_ok", 5000));
    if (!pong.includes("nexa_ok")) {
      throw new Error("Koneksi ADB ke HP tidak merespons. Hubungkan ulang HP, lalu coba lagi.");
    }
  };

  // Buka halaman uji (public/hwtest.html) di browser HP. Uji berjalan di HP itu sendiri,
  // jadi tidak bergantung pada perintah shell yang dibatasi sebagian merek.
  const openOnPhone = async (hash) => {
    const url = `${location.origin}/hwtest.html${hash ? "#" + hash : ""}`;
    await sh("input keyevent 224");
    const r = await sh(`am start -a android.intent.action.VIEW -d "${url}"`);
    return { url, failed: /error|exception|unable|not found/i.test(r), reply: snippet(r, 120) };
  };

  root.innerHTML = `
    <div class="card"><h2>Uji manual (interaktif)</h2>
      <p class="muted">Pemeriksaan di atas hanya membaca data. Komponen di bawah harus dirasakan atau ditekan langsung. Setelah tes jalan, tekan <b>Normal</b> atau <b>Bermasalah</b> sesuai yang kamu rasakan. Kalau perintah lewat ADB tidak berefek di HP ini, pakai <b>Uji di layar HP</b>.</p>
      <table id="mtbl">
        <tr><th>Uji</th><th>Status</th><th>Aksi</th></tr>
        ${TESTS.map((t) => `
        <tr data-t="${t.id}">
          <td><b>${esc(t.name)}</b><br><span class="muted">${esc(t.hint)}</span></td>
          <td class="mt-st info">Belum diuji</td>
          <td>
            <div class="row">${t.actions.map(([a, l]) => `<button data-t="${t.id}" data-a="${a}">${esc(l)}</button>`).join("")}</div>
            ${t.confirm ? `<div class="row mt-confirm" style="display:none"><button data-t="${t.id}" data-ok="1">✔ Normal</button><button data-t="${t.id}" data-ok="0">✖ Bermasalah</button></div>` : ""}
            <div class="muted mt-note"></div>
          </td>
        </tr>`).join("")}
      </table>
      <details class="help" style="margin-top:10px"><summary><b>Detail teknis getaran</b></summary><pre id="vibinfo">Tekan tombol di bawah untuk membaca info vibrator.</pre><div class="row"><button id="vibinfoBtn">Baca info vibrator</button></div></details>
    </div>
    <div class="card" id="phcard"><h2>Uji langsung di HP</h2>
      <p class="muted">Membuka halaman uji di browser HP pelanggan (HP harus menyala, tidak terkunci, dan punya internet). Ketuk tombol di layar HP; hasilnya tampil di HP. Aplikasi Chrome dianjurkan.</p>
      <div class="row">
        <button data-ph="">Buka semua uji di HP</button>
        <button data-ph="mic">Mikrofon</button>
        <button data-ph="bt">Bluetooth</button>
        <button data-ph="gps">GPS</button>
        <button data-ph="nfc">NFC</button>
      </div>
      <p class="muted" style="margin-top:12px">Pintasan pengaturan di HP, untuk memastikan komponen menyala dan dikenali:</p>
      <div class="row">
        <button data-set="bt">Pengaturan Bluetooth</button>
        <button data-set="nfc">Pengaturan NFC</button>
        <button data-set="loc">Pengaturan Lokasi</button>
        <button data-set="sec">Keamanan (sidik jari)</button>
      </div>
      <p class="muted" style="margin-top:12px"><b>Uji sidik jari:</b> tekan <b>Matikan layar</b>, lalu tempelkan jari yang sudah terdaftar ke sensor. Layar harus menyala dan terbuka. Perlu ada sidik jari terdaftar di HP.</p>
      <div class="row"><button data-sleep="1">Matikan layar</button></div>
      <div class="muted" id="phout" style="margin-top:10px"></div>
    </div>`;

  const row = (id) => root.querySelector(`tr[data-t="${id}"]`);
  const setStatus = (id, status, note) => {
    const r = row(id);
    if (!r) return;
    const st = r.querySelector(".mt-st");
    st.className = `mt-st ${CLS[status] || "info"}`;
    st.textContent = status === "INFO" ? "Berjalan…" : status;
    if (note !== undefined) r.querySelector(".mt-note").textContent = note;
  };
  const showConfirm = (id, on) => {
    const c = row(id)?.querySelector(".mt-confirm");
    if (c) c.style.display = on ? "" : "none";
  };
  const note = (id, t) => { const n = row(id)?.querySelector(".mt-note"); if (n) n.textContent = t; };

  let busy = false;
  const lock = (on) => { busy = on; root.querySelectorAll("button").forEach((b) => { b.disabled = on; }); };

  const RUN = {
    async vib(a) {
      setStatus("vib", "INFO", "Getar dikirim…");
      if (a === "short") {
        const r = await vibrate(sh, 1000);
        if (!r.ok) { setStatus("vib", "WARN", `Perintah getar ditolak HP ini (jawaban HP: ${r.tried.join(" | ")}). Pakai Uji di layar HP.`); return; }
        note("vib", "Perintah getar terkirim. Terasa? Kalau tidak terasa, coba Uji di layar HP.");
      } else {
        let r;
        for (let i = 0; i < 3; i++) {
          r = await vibrate(sh, 350);
          if (!r.ok) break;
          await sleep(700);
        }
        if (!r.ok) { setStatus("vib", "WARN", `Perintah getar ditolak HP ini (jawaban HP: ${r.tried.join(" | ")}). Pakai Uji di layar HP.`); return; }
        note("vib", "3 getaran terkirim. Terasa semuanya? Kalau tidak terasa, coba Uji di layar HP.");
      }
      setStatus("vib", "INFO");
      row("vib").querySelector(".mt-st").textContent = "Menunggu penilaian";
      showConfirm("vib", true);
    },

    async snd() {
      setStatus("snd", "INFO", "Memunculkan notifikasi…");
      const out = await sh('cmd notification post -S bigtext -t "Nexa Service Tool" nexa_test "Uji suara speaker"');
      if (BAD.test(out)) { setStatus("snd", "WARN", `HP menolak perintah notifikasi (jawaban HP: ${snippet(out, 120)}). Pakai Uji di layar HP.`); return; }
      row("snd").querySelector(".mt-st").textContent = "Menunggu penilaian";
      note("snd", "Notifikasi terkirim. Terdengar bunyinya? Notifikasi sering senyap bila izin notifikasi shell dibatasi; kalau tidak terdengar, coba Uji di layar HP.");
      showConfirm("snd", true);
    },

    async bri() {
      setStatus("bri", "INFO", "Mengubah kecerahan…");
      const oldVal = (await sh("settings get system screen_brightness")).trim();
      const oldMode = (await sh("settings get system screen_brightness_mode")).trim();
      if (!/^\d+$/.test(oldVal)) {
        setStatus("bri", "WARN", "HP tidak mengizinkan membaca/mengubah kecerahan lewat ADB. Uji kecerahan manual lewat Mirror.");
        return;
      }
      let putOut = "";
      try {
        putOut += await sh("settings put system screen_brightness_mode 0");
        putOut += await sh("settings put system screen_brightness 255");
        note("bri", "Terang penuh…");
        await sleep(1500);
        putOut += await sh("settings put system screen_brightness 15");
        note("bri", "Redup…");
        await sleep(1500);
      } finally {
        // kembalikan pengaturan semula walau ada galat di tengah jalan
        try {
          await sh(`settings put system screen_brightness ${oldVal}`);
          if (/^\d+$/.test(oldMode)) await sh(`settings put system screen_brightness_mode ${oldMode}`);
        } catch {}
      }
      if (BAD.test(putOut)) {
        setStatus("bri", "WARN", "HP menolak perubahan kecerahan (izin WRITE_SETTINGS). Uji kecerahan manual lewat Mirror.");
        return;
      }
      row("bri").querySelector(".mt-st").textContent = "Menunggu penilaian";
      note("bri", "Pengaturan dikembalikan. Layar berubah terang lalu redup dengan mulus?");
      showConfirm("bri", true);
    },

    async key() {
      const keys = [
        ["Volume +", /KEY_VOLUMEUP/],
        ["Volume −", /KEY_VOLUMEDOWN/],
        ["Power", /KEY_POWER/],
      ];
      const results = [];
      let unsupported = false;
      let lastOut = "";
      for (const [label, re] of keys) {
        setStatus("key", "INFO", `Tekan ${label} sekarang (8 detik)…`);
        const out = await sh("timeout 8 getevent -lq", 15000);
        lastOut = out;
        if (/not found|inaccessible|permission denied|can't find|unknown option|usage/i.test(out)) { unsupported = true; break; }
        results.push([label, re.test(out)]);
      }
      if (unsupported) { setStatus("key", "WARN", `HP ini tidak mengizinkan getevent lewat ADB (jawaban HP: ${snippet(lastOut, 120)}). Uji tombol manual: pakai Mirror, lalu tekan tombol fisik dan lihat layar bereaksi.`); return; }
      if (results.every(([, ok]) => !ok)) {
        // Tidak satu tombol pun terbaca: bisa tombol rusak, bisa juga HP tidak mengirim event lewat ADB.
        setStatus("key", "WARN", `Tidak ada tombol yang terbaca (keluaran HP: ${snippet(lastOut, 80)}). Pastikan tombol benar-benar ditekan; kalau tetap kosong, HP ini mungkin tidak mengirim event tombol lewat ADB. Cek manual: tekan Vol+/Vol− dan lihat slider volume muncul, tekan Power dan lihat layar mati.`);
        return;
      }
      const failed = results.filter(([, ok]) => !ok).map(([l]) => l);
      setStatus("key", failed.length ? "FAIL" : "PASS",
        failed.length ? `Tidak terdeteksi: ${failed.join(", ")}.` : "Semua tombol terdeteksi.");
    },

    async usb() {
      setStatus("usb", "INFO", "Membaca…");
      const raw = await sh("dumpsys battery");
      if (!raw || !/level:/.test(raw)) {
        setStatus("usb", "WARN", "Data baterai tidak terbaca dari HP. Hubungkan ulang lalu coba lagi.");
        return;
      }
      const usb = /USB powered: true/.test(raw);
      const ac = /AC powered: true/.test(raw);
      const wireless = /Wireless powered: true/.test(raw);
      if (usb || ac || wireless) setStatus("usb", "PASS", `Menerima daya (${[usb && "USB", ac && "AC", wireless && "Wireless"].filter(Boolean).join(", ")}).`);
      else setStatus("usb", "WARN", "HP tidak menerima daya dari kabel. Coba kabel/port lain; kalau tetap, curiga port pengisian atau konektor rusak. Catatan: HP yang dicolok ke komputer lewat kabel data kadang hanya mengisi sangat pelan.");
    },
  };

  const phout = () => root.querySelector("#phout");

  root.onclick = async (e) => {
    const btn = e.target.closest("button");
    if (!btn || busy) return;

    // --- kartu "Uji langsung di HP" ---
    if (btn.dataset.ph != null || btn.dataset.set || btn.dataset.sleep) {
      lock(true);
      const out = phout();
      try {
        out.textContent = "Memeriksa koneksi ke HP…";
        await ensureLink();
        if (btn.dataset.ph != null) {
          const o = await openOnPhone(btn.dataset.ph);
          out.textContent = o.failed
            ? `HP tidak bisa membuka browser (jawaban HP: ${o.reply}). Buka alamat ini di browser HP: ${o.url}`
            : `Halaman uji dibuka di HP: ${o.url}. Kalau tidak muncul, pastikan layar HP terbuka kunci dan HP punya internet.`;
        } else if (btn.dataset.set) {
          const action = SETTINGS[btn.dataset.set];
          if (!action) return;
          const r = await sh(`am start -a ${action}`);
          out.textContent = BAD.test(r)
            ? `HP menolak membuka layar itu (jawaban HP: ${snippet(r, 120)}). Buka manual lewat Pengaturan.`
            : "Layar pengaturan dibuka di HP.";
        } else {
          await sh("input keyevent 223");
          out.textContent = "Layar dimatikan. Tempelkan jari terdaftar ke sensor; layar harus menyala dan terbuka.";
        }
      } catch (err) {
        out.textContent = `Gagal: ${err?.message || err}`;
      } finally {
        lock(false);
      }
      return;
    }

    if (btn.id === "vibinfoBtn") {
      lock(true);
      const pre = root.querySelector("#vibinfo");
      try {
        pre.textContent = "Membaca…";
        await ensureLink();
        pre.textContent = await vibratorInfo(sh);
      } catch (err) {
        pre.textContent = `Gagal: ${err?.message || err}`;
      } finally { lock(false); }
      return;
    }
    const id = btn.dataset.t;
    if (!id) return;
    if (btn.dataset.ok != null) {
      setStatus(id, btn.dataset.ok === "1" ? "PASS" : "FAIL");
      showConfirm(id, false);
      return;
    }
    const action = btn.dataset.a;

    // --- "Uji di layar HP": uji berjalan di browser HP, hasilnya dinilai di sini ---
    if (action === "phone" && PHONE_HASH[id]) {
      lock(true);
      showConfirm(id, false);
      try {
        setStatus(id, "INFO", "Membuka halaman uji di HP…");
        await ensureLink();
        const o = await openOnPhone(PHONE_HASH[id]);
        if (o.failed) {
          setStatus(id, "WARN", `HP tidak bisa membuka browser (jawaban HP: ${o.reply}). Buka alamat ini di browser HP: ${o.url}`);
        } else {
          row(id).querySelector(".mt-st").className = "mt-st info";
          row(id).querySelector(".mt-st").textContent = "Uji di HP";
          note(id, "Halaman uji dibuka di HP. Ketuk tombol uji di layar HP, lalu nilai hasilnya di sini.");
          showConfirm(id, true);
        }
      } catch (err) {
        setStatus(id, "WARN", `Gagal: ${err?.message || err}`);
      } finally {
        lock(false);
      }
      return;
    }

    if (!action || !RUN[id]) return;
    lock(true);
    showConfirm(id, false);
    try {
      setStatus(id, "INFO", "Memeriksa koneksi ke HP…");
      await ensureLink();
      await RUN[id](action);
    } catch (err) {
      setStatus(id, "WARN", `Gagal: ${err?.message || err}`);
    } finally {
      lock(false);
    }
  };
}
