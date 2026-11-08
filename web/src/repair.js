// Halaman Perbaikan: aksi yang MENGUBAH HP, semuanya lewat ADB shell (tanpa root).
// Tidak ada fitur membuka kunci layar atau FRP. Aksi berisiko meminta konfirmasi.
// Catatan: perintah bisa berbeda antar versi Android/merek; hasil asli selalu ditampilkan di log.

const PKG_RE = /^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+$/;
// Path yang boleh disentuh: hanya penyimpanan bersama, tanpa karakter yang bisa ditafsirkan shell.
const PATH_RE = /^\/(sdcard|storage\/emulated\/0)(\/[^\x00-\x1f"'`$\\;|&<>*?()!{}\[\]~#%^]+)*\/?$/;
const shq = (p) => p.replace(/ /g, "\\ "); // spasi di-escape, tanpa tanda kutip

const PROTECTED = new Set([
  "android",
  "com.android.systemui",
  "com.android.settings",
  "com.android.phone",
  "com.android.shell",
  "com.android.vending",
  "com.google.android.gms",
  "com.google.android.packageinstaller",
  "com.android.packageinstaller",
]);

const RISK_LABEL = { low: "Rendah", mid: "Sedang", high: "Tinggi" };

async function confirmRisk(level, title, detail) {
  if (level === "low") return true;
  const body = `[Risiko ${RISK_LABEL[level]}] ${title}\n\n${detail || ""}`.trim();
  if (level === "mid") return confirm(`${body}\n\nLanjutkan?`);
  const t = prompt(`${body}\n\nKetik YA untuk melanjutkan.`);
  return (t || "").trim().toUpperCase() === "YA";
}

async function readText(stream) {
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

const fmtSize = (n) => {
  if (n >= 1024 ** 3) return (n / 1024 ** 3).toFixed(2) + " GB";
  if (n >= 1024 ** 2) return (n / 1024 ** 2).toFixed(1) + " MB";
  if (n >= 1024) return (n / 1024).toFixed(0) + " KB";
  return n + " B";
};

export async function renderRepair(view, ctx) {
  const { sh, getAdb, esc } = ctx;
  const q = (s) => view.querySelector(s);
  const logs = [];

  view.innerHTML = `
    <div class="card">
      <h2>Perbaikan</h2>
      <p class="muted">Aksi di halaman ini <b>mengubah HP</b>. Aksi berisiko meminta konfirmasi, hasil asli dicatat di log paling bawah.
      Tidak ada fitur membuka kunci layar atau FRP. Perbaikan fisik (layar pecah, baterai kembung, board) tetap harus ganti komponen.</p>
    </div>

    <div class="card">
      <h2>Cek kompatibilitas HP ini</h2>
      <p class="muted">Memeriksa apakah perintah yang dipakai halaman ini tersedia di HP yang terhubung. Tidak menjalankan aksi dan tidak mengubah HP.
      Hasilnya hanya menunjukkan perintah tersedia; hasil aksi sebenarnya tetap tampil di log setelah dijalankan.</p>
      <div class="row"><button id="compat" class="primary">Cek sekarang</button></div>
      <div id="compatres"></div>
    </div>

    <div class="card">
      <h2>1. Aplikasi</h2>
      <div class="row"><input id="pkg" list="pkgs" placeholder="nama paket, mis. com.whatsapp" /><datalist id="pkgs"></datalist></div>
      <div class="row">
        <button data-act="app-stop">Hentikan paksa</button>
        <button data-act="app-clear">Hapus data</button>
        <button data-act="app-disable">Nonaktifkan</button>
        <button data-act="app-enable">Aktifkan</button>
        <button data-act="app-uninstall">Copot</button>
        <button data-act="app-restore">Pulihkan yang dicopot</button>
      </div>
      <div class="row"><input type="file" id="apk" accept=".apk" /><button id="apkgo">Install APK</button><span id="apkstat" class="muted"></span></div>
    </div>

    <div class="card">
      <h2>2. Reboot</h2>
      <div class="row">
        <button data-act="reboot-system">Reboot sistem</button>
        <button data-act="reboot-recovery">Reboot ke Recovery</button>
        <button data-act="reboot-bootloader">Reboot ke Bootloader</button>
      </div>
      <p class="muted">Koneksi USB akan terputus setelah reboot; hubungkan lagi setelah HP menyala.</p>
    </div>

    <div class="card">
      <h2>3. Penyimpanan & backup</h2>
      <div class="row">
        <button data-act="trim-caches">Bersihkan cache semua aplikasi</button>
        <button id="scan">Cari file besar (&gt; 20 MB)</button>
      </div>
      <div id="large"></div>
      <div class="row" style="margin-top:10px">
        <input id="bkpath" value="/sdcard/DCIM" />
        <button id="bkgo" class="primary">Backup folder ke komputer/HP ini (.tar)</button>
      </div>
      <p id="bkstat" class="muted"></p>
    </div>

    <div class="card">
      <h2>4. HP lemot</h2>
      <div class="row">
        <button data-act="dexopt">Optimasi aplikasi</button>
        <button data-act="idle-maint">Jalankan maintenance (fstrim)</button>
      </div>
      <div class="row">
        <button data-act="anim-off">Animasi mati</button>
        <button data-act="anim-half">Animasi 0.5x</button>
        <button data-act="anim-normal">Animasi normal 1x</button>
      </div>
    </div>

    <div class="card">
      <h2>5. Jaringan</h2>
      <div class="row">
        <button data-act="wifi-on">Wi-Fi hidup</button><button data-act="wifi-off">Wi-Fi mati</button>
        <button data-act="data-on">Data hidup</button><button data-act="data-off">Data mati</button>
        <button data-act="air-on">Mode pesawat hidup</button><button data-act="air-off">Mode pesawat mati</button>
      </div>
    </div>

    <div class="card">
      <h2>6. Baterai</h2>
      <div class="row">
        <button data-act="bat-info">Lihat status baterai</button>
        <button data-act="bat-reset-stats">Reset statistik baterai</button>
        <button data-act="bat-reset-fake">Hapus simulasi baterai</button>
      </div>
    </div>

    <div class="card">
      <h2>7. Reset pabrik (terpandu)</h2>
      <p class="muted">Reset langsung lewat ADB tanpa root tidak andal, jadi alat ini mem-boot HP ke Recovery lalu kamu memilih <b>Wipe data / Factory reset</b> dengan tombol fisik.
      Pastikan pemilik setuju dan data sudah dibackup. HP yang masih terdaftar akun Google akan meminta akun itu lagi setelah reset.</p>
      <div class="row"><button id="fr" class="danger">Mulai reset pabrik terpandu</button></div>
    </div>

    <div class="card">
      <h2>8. Flash firmware</h2>
      <p class="muted">Flash firmware resmi lewat fastboot belum tersedia di versi web (berisiko tinggi). Pakai versi desktop (<code>core/firmware.py</code>) dan tool resmi merek HP.</p>
    </div>

    <div class="card">
      <h2>Log tindakan</h2>
      <div class="row"><button id="copylog">Salin log</button><button id="clearlog">Kosongkan</button></div>
      <pre id="log">(belum ada tindakan)</pre>
    </div>`;

  // --- util eksekusi ---------------------------------------------------
  async function exec(cmd) {
    const raw = await sh(`${cmd}; echo EXIT:$?`);
    const m = raw.match(/EXIT:(\d+)\s*$/);
    const code = m ? Number(m[1]) : null;
    const out = raw.replace(/EXIT:\d+\s*$/, "").trim();
    const failed = /^(Failure|Error|Exception|Unknown command|cmd: Can't find service)|: not found\s*$/im.test(out);
    return { ok: code === 0 && !failed, code, out };
  }

  function addLog(label, ok, out) {
    const t = new Date().toLocaleTimeString("id-ID");
    logs.push(`[${t}] ${ok ? "OK" : "GAGAL"} - ${label}${out ? "\n    " + String(out).split("\n").slice(0, 12).join("\n    ") : ""}`);
    const el = q("#log");
    if (el) el.textContent = logs.slice(-40).join("\n");
  }

  const needPkg = () => {
    const p = q("#pkg").value.trim();
    if (!PKG_RE.test(p)) throw new Error("Isi nama paket yang valid, mis. com.whatsapp.");
    return p;
  };
  const guardPkg = (p) => {
    if (PROTECTED.has(p) || p.startsWith("com.android.providers.")) {
      throw new Error(`${p} penting bagi sistem, diblokir.`);
    }
    return p;
  };
  const needPath = (p) => {
    if (!PATH_RE.test(p)) throw new Error("Path harus di /sdcard dan tanpa karakter khusus (kutip, $, ;, |, &, dll.).");
    return p.replace(/\/+$/, "");
  };

  const anim = (v) => `settings put global window_animation_scale ${v}; settings put global transition_animation_scale ${v}; settings put global animator_duration_scale ${v}`;

  // --- cek kompatibilitas (tidak mengubah HP) ----------------------------
  q("#compat").onclick = async () => {
    const box = q("#compatres");
    const btn = q("#compat");
    btn.disabled = true;
    box.innerHTML = `<p class="muted">Memeriksa…</p>`;
    try {
      const sdk = Number(await sh("getprop ro.build.version.sdk")) || 0;
      const bins = ["pm", "cmd", "am", "svc", "sm", "settings", "dumpsys", "tar", "find", "du", "cat", "rm", "reboot"];
      const probe = await sh(bins.map((b) => `command -v ${b} >/dev/null 2>&1 && echo OK:${b} || echo NO:${b}`).join("; "));
      const has = new Set(probe.split("\n").map((l) => l.trim()).filter((l) => l.startsWith("OK:")).map((l) => l.slice(3)));
      const svcList = await sh("cmd -l 2>/dev/null");
      const hasSvc = (n) => new RegExp(`^\\s*${n}\\s*$`, "m").test(svcList);
      const store = await sh("find /storage/emulated/0 -maxdepth 1 2>/dev/null | head -n 3");
      const need = (...b) => b.every((x) => has.has(x));
      const rows = [
        ["Aplikasi: hentikan, hapus data, nonaktifkan, copot", need("pm", "am") && sdk >= 21, "pm, am, Android 5+"],
        ["Install APK", need("cmd") && sdk >= 24, "cmd package install -S (Android 7+)"],
        ["Reboot", need("reboot"), "reboot"],
        ["Bersihkan cache", need("pm"), "pm trim-caches"],
        ["Cari file besar dan hapus", need("find", "rm") && !!store, store ? "find, akses /storage/emulated/0 OK" : "penyimpanan tidak terbaca (HP terkunci atau tanpa izin)"],
        ["Backup folder dan unduh file", need("tar", "du", "cat") && !!store, "tar, du, cat"],
        ["Optimasi aplikasi", need("cmd") && sdk >= 26, "cmd package bg-dexopt-job (Android 8+)"],
        ["Maintenance penyimpanan", need("sm"), "sm idle-maint"],
        ["Animasi sistem", need("settings"), "settings"],
        ["Wi-Fi dan data seluler", need("svc"), "svc"],
        ["Mode pesawat", need("cmd") && hasSvc("connectivity") && sdk >= 30, "cmd connectivity (Android 11+)"],
        ["Baterai", need("dumpsys"), "dumpsys"],
        ["Reset pabrik terpandu", need("reboot", "dumpsys"), "reboot recovery"],
      ];
      box.innerHTML = `<p class="muted">Android SDK ${sdk || "?"}</p><table>${rows.map(([name, ok, note]) =>
        `<tr><td>${esc(name)}</td><td class="${ok ? "pass" : "fail"}">${ok ? "Tersedia" : "Tidak tersedia"}</td><td class="muted">${esc(note)}</td></tr>`).join("")}</table>`;
      addLog("Cek kompatibilitas", true, rows.filter((r) => !r[1]).map((r) => `Tidak tersedia: ${r[0]}`).join("\n") || "Semua perintah tersedia.");
    } catch (e) {
      box.innerHTML = `<pre class="fail">${esc(e.message || e)}</pre>`;
    } finally {
      btn.disabled = false;
    }
  };

  // --- registri aksi -----------------------------------------------------
  const ACTIONS = {
    "app-stop": { risk: "low", label: "Hentikan paksa aplikasi", cmd: () => `am force-stop ${needPkg()}` },
    "app-clear": {
      risk: "high", label: "Hapus data aplikasi",
      detail: "Semua data, login, dan pengaturan aplikasi ini akan hilang dan tidak bisa dikembalikan.",
      cmd: () => `pm clear ${guardPkg(needPkg())}`,
    },
    "app-disable": {
      risk: "mid", label: "Nonaktifkan aplikasi",
      detail: "Aplikasi disembunyikan dan tidak berjalan. Bisa diaktifkan lagi.",
      cmd: () => `pm disable-user --user 0 ${guardPkg(needPkg())}`,
    },
    "app-enable": { risk: "low", label: "Aktifkan aplikasi", cmd: () => `pm enable ${needPkg()}` },
    "app-uninstall": {
      risk: "high", label: "Copot aplikasi (user 0)",
      detail: "Aplikasi dicopot untuk pengguna utama. Aplikasi bawaan bisa dipulihkan dengan tombol 'Pulihkan yang dicopot'; aplikasi pihak ketiga perlu dipasang ulang.",
      cmd: () => `pm uninstall --user 0 ${guardPkg(needPkg())}`,
    },
    "app-restore": { risk: "low", label: "Pulihkan aplikasi yang dicopot", cmd: () => `cmd package install-existing ${needPkg()}` },

    "reboot-system": {
      risk: "mid", label: "Reboot sistem", detail: "HP akan restart dan koneksi USB terputus.",
      cmd: () => "reboot", disconnects: true,
    },
    "reboot-recovery": {
      risk: "mid", label: "Reboot ke Recovery", detail: "HP masuk mode Recovery. Jangan pilih menu wipe kecuali memang mau reset.",
      cmd: () => "reboot recovery", disconnects: true,
    },
    "reboot-bootloader": {
      risk: "mid", label: "Reboot ke Bootloader", detail: "HP masuk mode Fastboot/Bootloader.",
      cmd: () => "reboot bootloader", disconnects: true,
    },

    "trim-caches": { risk: "low", label: "Bersihkan cache semua aplikasi", cmd: () => "pm trim-caches 999G" },

    "dexopt": {
      risk: "low", label: "Optimasi aplikasi (bg-dexopt-job)",
      detail: "Bisa memakan beberapa menit.", cmd: () => "cmd package bg-dexopt-job",
    },
    "idle-maint": { risk: "low", label: "Maintenance penyimpanan (fstrim)", cmd: () => "sm idle-maint run" },
    "anim-off": { risk: "mid", label: "Matikan animasi sistem", detail: "Bisa dikembalikan dengan 'Animasi normal 1x'.", cmd: () => anim("0") },
    "anim-half": { risk: "low", label: "Animasi 0.5x", cmd: () => anim("0.5") },
    "anim-normal": { risk: "low", label: "Animasi normal 1x", cmd: () => anim("1.0") },

    "wifi-on": { risk: "low", label: "Wi-Fi hidup", cmd: () => "svc wifi enable" },
    "wifi-off": { risk: "low", label: "Wi-Fi mati", cmd: () => "svc wifi disable" },
    "data-on": { risk: "low", label: "Data seluler hidup", cmd: () => "svc data enable" },
    "data-off": { risk: "low", label: "Data seluler mati", cmd: () => "svc data disable" },
    "air-on": { risk: "mid", label: "Mode pesawat hidup", detail: "Sinyal seluler, Wi-Fi, dan Bluetooth mati.", cmd: () => "cmd connectivity airplane-mode enable" },
    "air-off": { risk: "low", label: "Mode pesawat mati", cmd: () => "cmd connectivity airplane-mode disable" },

    "bat-info": { risk: "low", label: "Status baterai", cmd: () => "dumpsys battery" },
    "bat-reset-stats": {
      risk: "mid", label: "Reset statistik baterai",
      detail: "Riwayat pemakaian baterai dihapus. Tidak memperbaiki kesehatan baterai.",
      cmd: () => "dumpsys batterystats --reset",
    },
    "bat-reset-fake": { risk: "low", label: "Hapus simulasi baterai", cmd: () => "dumpsys battery reset" },
  };

  async function perform(a, btn) {
    let cmd;
    try {
      cmd = a.cmd();
    } catch (e) {
      addLog(a.label, false, e.message);
      return;
    }
    if (!(await confirmRisk(a.risk, a.label, a.detail))) return;
    if (btn) btn.disabled = true;
    addLog(`${a.label} (dikirim)`, true, "");
    try {
      const r = await exec(cmd);
      if (a.disconnects && !r.out && r.code == null) addLog(a.label, true, "Perintah terkirim; koneksi akan terputus.");
      else addLog(a.label, r.ok, r.out || (r.code == null ? "Tidak ada respons dari HP." : `kode keluar ${r.code}`));
    } catch (e) {
      addLog(a.label, false, e.message || e);
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  view.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-act]");
    if (!b) return;
    const a = ACTIONS[b.dataset.act];
    if (a) perform(a, b);
  });

  // --- daftar paket untuk autocomplete ---------------------------------
  sh("pm list packages -3").then((t) => {
    const dl = q("#pkgs");
    if (!dl) return;
    dl.innerHTML = t.split("\n").map((l) => l.replace("package:", "").trim()).filter(Boolean).sort()
      .map((p) => `<option value="${esc(p)}"></option>`).join("");
  });

  // --- install APK ------------------------------------------------------
  q("#apkgo").onclick = async () => {
    const file = q("#apk").files?.[0];
    const stat = (t) => { const el = q("#apkstat"); if (el) el.textContent = t; };
    if (!file) return stat("Pilih file .apk dulu.");
    if (!file.name.toLowerCase().endsWith(".apk")) return stat("File harus berakhiran .apk.");
    if (!(await confirmRisk("mid", `Install ${file.name}`, `Ukuran ${fmtSize(file.size)}. Pasang hanya APK dari sumber tepercaya.`))) return;
    const btn = q("#apkgo");
    btn.disabled = true;
    try {
      const adb = getAdb();
      stat("Mengirim APK…");
      const proc = await adb.subprocess.noneProtocol.spawn(`cmd package install -S ${file.size} -r`);
      const outP = readText(proc.output);
      const writer = proc.stdin.getWriter();
      const reader = file.stream().getReader();
      let sent = 0;
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        await writer.write(value);
        sent += value.length;
        stat(`Mengirim… ${Math.round((sent / file.size) * 100)}%`);
      }
      stat("Menunggu hasil dari HP…");
      // pm install -S berhenti membaca setelah <ukuran> byte; kalau HP tidak merespons dalam 20 detik,
      // tutup stdin (cara yang dipakai Tango) lalu tunggu hasilnya.
      let out = await Promise.race([outP, new Promise((r) => setTimeout(() => r(null), 20000))]);
      if (out === null) {
        try { await writer.close(); } catch {}
        out = await outP;
      } else {
        writer.releaseLock();
      }
      out = out.trim();
      const ok = /Success/i.test(out);
      stat(ok ? "Terpasang." : "Gagal.");
      addLog(`Install APK ${file.name}`, ok, out);
    } catch (e) {
      stat("Gagal.");
      addLog(`Install APK ${file.name}`, false, e.message || e);
    } finally {
      btn.disabled = false;
    }
  };

  // --- unduh dari HP (cat / tar) -----------------------------------------
  async function streamToFile(cmd, filename, onProgress) {
    const adb = getAdb();
    let writer = null;
    if (window.showSaveFilePicker) {
      try {
        const handle = await window.showSaveFilePicker({ suggestedName: filename });
        writer = await handle.createWritable();
      } catch (e) {
        if (e?.name === "AbortError") throw new Error("Dibatalkan.");
        writer = null; // izin klik sudah habis atau tidak didukung: pakai unduhan biasa
      }
    }
    const proc = await adb.subprocess.noneProtocol.spawn(cmd);
    const reader = proc.output.getReader();
    const chunks = [];
    let total = 0;
    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        total += value.length;
        if (writer) await writer.write(value);
        else {
          chunks.push(value);
          if (total > 700 * 1024 * 1024) throw new Error("Terlalu besar untuk diunduh lewat browser ini (batas 700 MB). Pakai Chrome desktop, atau pilih folder yang lebih kecil.");
        }
        onProgress?.(total);
      }
      if (writer) await writer.close();
      else {
        const a = document.createElement("a");
        a.href = URL.createObjectURL(new Blob(chunks));
        a.download = filename;
        a.click();
        setTimeout(() => URL.revokeObjectURL(a.href), 4000);
      }
    } catch (e) {
      try { await writer?.abort(); } catch {}
      try { await proc.kill(); } catch {}
      throw e;
    }
    return total;
  }

  q("#bkgo").onclick = async () => {
    const stat = (t) => { const el = q("#bkstat"); if (el) el.textContent = t; };
    const btn = q("#bkgo");
    btn.disabled = true;
    try {
      const path = needPath(q("#bkpath").value.trim());
      const cut = path.lastIndexOf("/");
      const parent = path.slice(0, cut) || "/";
      const name = path.slice(cut + 1);
      if (!name) throw new Error("Isi path folder, mis. /sdcard/DCIM.");
      const du = await sh(`du -sk ${shq(path)} 2>/dev/null`);
      const kb = Number((du.split(/\s+/)[0]) || 0);
      if (!kb) throw new Error("Folder kosong atau tidak ditemukan.");
      if (!(await confirmRisk("mid", `Backup ${path}`, `Ukuran sekitar ${fmtSize(kb * 1024)}. Hasil berupa file .tar; ${window.showSaveFilePicker ? "kamu akan memilih lokasi simpan" : "disimpan lewat unduhan browser"}.`))) return;
      const fname = `backup-${name}-${new Date().toISOString().slice(0, 10)}.tar`;
      stat("Menyiapkan…");
      const total = await streamToFile(`tar -cf - -C ${shq(parent)} ${shq(name)} 2>/dev/null`, fname, (n) => stat(`Terunduh ${fmtSize(n)}…`));
      stat(`Selesai: ${fname} (${fmtSize(total)})`);
      addLog(`Backup ${path}`, true, `${fname}, ${fmtSize(total)}`);
    } catch (e) {
      stat("Gagal: " + (e.message || e));
      addLog("Backup folder", false, e.message || e);
    } finally {
      btn.disabled = false;
    }
  };

  // --- cari file besar ---------------------------------------------------
  q("#scan").onclick = async () => {
    const box = q("#large");
    box.innerHTML = `<p class="muted">Mencari… (bisa agak lama)</p>`;
    // /sdcard adalah symlink; find tidak mengikutinya, jadi pakai path aslinya.
    const out = await sh("find /storage/emulated/0 -type f -size +20M -exec ls -l {} + 2>/dev/null");
    const rows = out.split("\n").map((l) => {
      const p = l.trim().split(/\s+/);
      if (p.length < 8 || !p[0].startsWith("-")) return null;
      return { size: Number(p[4]), path: p.slice(7).join(" ") };
    }).filter((r) => r && r.size > 0 && r.path.startsWith("/")).sort((a, b) => b.size - a.size).slice(0, 30);
    if (!rows.length) { box.innerHTML = `<p class="muted">Tidak ada file besar (&gt; 20 MB) atau tidak ada izin baca.</p>`; return; }
    box.innerHTML = `<table>${rows.map((r, i) => `<tr><td>${esc(r.path)}</td><td class="muted">${fmtSize(r.size)}</td>
      <td><span class="link" data-dl="${i}">unduh</span> · <span class="link" data-rm="${i}">hapus</span></td></tr>`).join("")}</table>`;
    box.onclick = async (e) => {
      const dl = e.target.dataset?.dl, rm = e.target.dataset?.rm;
      const r = rows[Number(dl ?? rm)];
      if (!r) return;
      try {
        const path = needPath(r.path);
        if (dl != null) {
          const name = path.split("/").pop();
          const total = await streamToFile(`cat ${shq(path)}`, name);
          addLog(`Unduh ${path}`, true, fmtSize(total));
        } else {
          if (!(await confirmRisk("high", `Hapus file ${path}`, "File dihapus permanen dari HP."))) return;
          const res = await exec(`rm ${shq(path)}`);
          addLog(`Hapus ${path}`, res.ok, res.out);
          if (res.ok) e.target.closest("tr")?.remove();
        }
      } catch (err) {
        addLog("Aksi file", false, err.message || err);
      }
    };
  };

  // --- reset pabrik terpandu --------------------------------------------
  q("#fr").onclick = async () => {
    try {
      const acc = await sh("dumpsys account | grep -c com.google");
      const n = Number(acc.split(/\s+/)[0]) || 0;
      const detail = `SEMUA data di HP akan terhapus. ${n > 0 ? `HP ini masih memiliki akun Google; setelah reset, akun itu diminta lagi (FRP).` : "Tidak terdeteksi akun Google."}\n` +
        "Pastikan pemilik setuju dan data sudah dibackup. Alat ini hanya mem-boot HP ke Recovery; kamu memilih Wipe data/Factory reset sendiri.";
      const t = prompt(`[Risiko Tinggi] Reset pabrik terpandu\n\n${detail}\n\nKetik RESET untuk melanjutkan.`);
      if ((t || "").trim().toUpperCase() !== "RESET") return;
      await sh("reboot recovery");
      addLog("Reset pabrik terpandu: reboot ke Recovery", true,
        "Di layar Recovery pilih Wipe data / Factory reset dengan tombol Volume dan Power, lalu konfirmasi. Koneksi USB terputus selama reboot.");
    } catch (e) {
      addLog("Reset pabrik terpandu", false, e.message || e);
    }
  };

  // --- log ---------------------------------------------------------------
  q("#copylog").onclick = async () => {
    try { await navigator.clipboard.writeText(logs.join("\n")); } catch {}
  };
  q("#clearlog").onclick = () => { logs.length = 0; q("#log").textContent = "(belum ada tindakan)"; };
}
