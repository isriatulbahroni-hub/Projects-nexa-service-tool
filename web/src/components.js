// Halaman Uji Komponen: sensor, kamera, mikrofon, warna layar, dan sentuhan.
// Uji dijalankan lewat ADB lalu dinilai teknisi; hasilnya masuk ke laporan servis.
// Beberapa HP membatasi data tertentu, jadi hasil yang tidak bisa dibaca ditandai, bukan dianggap lulus.
import { esc, sleep, num, CLS, LABEL, getTests, saveTest } from "./kit.js";

const WANT = [
  ["accelerometer", "Accelerometer (gerak)"],
  ["gyroscope", "Gyroscope (putar)"],
  ["proximity", "Proximity (dekat)"],
  ["light", "Cahaya"],
  ["magnetic_field", "Kompas (magnetik)"],
];

const CARDS = [
  { id: "sensor", title: "Sensor", hint: "Membaca accelerometer, gyroscope, proximity, cahaya, dan kompas. Pada uji gerak, goyangkan HP, miringkan, lalu tutup sensor dekat speaker atas dengan tangan.", actions: [["read", "Baca sensor"], ["move", "Uji gerak 12 detik"]] },
  { id: "camera", title: "Kamera", hint: "Membaca kamera yang terdaftar, lalu membuka aplikasi kamera dan mengambil satu foto uji. HP harus menyala dan tidak terkunci.", actions: [["info", "Cek kamera"], ["back", "Foto uji belakang"], ["front", "Foto uji depan"], ["check", "Cek foto baru"], ["clean", "Hapus foto uji"]] },
  { id: "audio", title: "Mikrofon", hint: "Membaca status mikrofon, lalu membuka perekam suara. Bicara ke mikrofon, putar ulang, dan nilai hasilnya. Uji speaker ada di Hardware Test.", actions: [["info", "Cek status mikrofon"], ["rec", "Buka perekam suara"]] },
  { id: "display", title: "Warna layar", hint: "Membuka halaman uji di HP: merah, hijau, biru, putih, hitam, abu-abu. Cari piksel mati, garis, bercak, atau layar yang menguning. HP butuh internet.", actions: [["info", "Info layar"], ["color", "Buka uji warna di HP"]] },
  { id: "touch", title: "Sentuhan layar", hint: "Membuka kotak-kotak di layar HP. Usap seluruh layar sampai semua kotak menyala. Kotak yang tidak menyala menandakan area sentuh mati. HP butuh internet.", actions: [["open", "Buka uji sentuhan di HP"]] },
];
const TITLE = Object.fromEntries(CARDS.map((c) => [c.id, c.title]));

// ---------------------------------------------------------------
// Pembaca keluaran dumpsys (fungsi murni, bisa diuji tanpa HP)
// ---------------------------------------------------------------
export function parseSensors(text) {
  const byName = {};
  const list = [];
  let inRecent = false;
  let cur = null;
  const stampsBy = {};
  for (const raw of String(text || "").split("\n")) {
    const line = raw.replace(/\r$/, "");
    const lm = line.match(/^\s*0x[0-9a-f]+\)\s*(.*?)\s*\|.*type:\s*([\w.]+)\((\d+)\)/i);
    if (lm) { list.push({ name: lm[1], type: lm[2].replace(/^android\.sensor\./, "") }); continue; }
    if (/Recent Sensor events/i.test(line)) { inRecent = true; cur = null; continue; }
    if (!inRecent) continue;
    const hm = line.match(/^\s*(.+?):\s*last\s+(\d+)\s+events/i);
    if (hm) { cur = hm[1].trim(); byName[cur] = []; stampsBy[cur] = []; continue; }
    const em = line.match(/\(ts=[^)]*\)\s*(.*)$/);
    if (em && cur) {
      const vals = em[1].split(",").map((s) => parseFloat(s)).filter(Number.isFinite);
      if (vals.length) {
        byName[cur].push(vals);
        const tm = line.match(/\(ts=([\d.]+)/);
        stampsBy[cur].push(tm ? tm[1] : "");
      }
    }
  }
  const out = {};
  for (const s of list) {
    const prev = out[s.type];
    if (!prev || (/wake/i.test(prev.name) && !/wake/i.test(s.name))) out[s.type] = { name: s.name, events: [], stamps: [] };
  }
  for (const t of Object.keys(out)) { out[t].events = byName[out[t].name] || []; out[t].stamps = stampsBy[out[t].name] || []; }
  return out;
}

export function parseCameras(text) {
  const t = String(text || "");
  const facing = [...t.matchAll(/Facing:\s*(BACK|FRONT|EXTERNAL)/gi)].map((m) => m[1].toUpperCase());
  const status = [...t.matchAll(/Device status:\s*(\w+)/gi)].map((m) => m[1].toUpperCase());
  return {
    count: num((t.match(/Number of camera devices:\s*(\d+)/i) || [])[1]),
    hasBack: facing.includes("BACK"),
    hasFront: facing.includes("FRONT"),
    status,
  };
}

// true = nilai berubah selama uji, false = tidak berubah, null = tidak ada data cukup
export function reacted(type, vecs) {
  if (!vecs || vecs.length < 2) return null;
  if (type === "proximity") return new Set(vecs.map((v) => v[0])).size >= 2;
  if (type === "light") {
    const xs = vecs.map((v) => v[0]);
    return Math.max(...xs) - Math.min(...xs) >= 10;
  }
  const th = type === "gyroscope" ? 0.4 : type === "magnetic_field" ? 8 : 1.5;
  let best = 0;
  for (let i = 0; i < 3; i++) {
    const xs = vecs.map((v) => v[i]).filter(Number.isFinite);
    if (xs.length > 1) best = Math.max(best, Math.max(...xs) - Math.min(...xs));
  }
  return best >= th;
}

function sensorTable(s, verdict) {
  const rows = WANT.map(([t, label]) => {
    const x = s[t];
    if (!x) return `<tr><td>${esc(label)}</td><td class="warn">Tidak terdeteksi</td><td class="muted">-</td></tr>`;
    const last = x.events[x.events.length - 1];
    const val = last ? last.slice(0, 3).map((v) => v.toFixed(2)).join(", ") : "belum ada data";
    const vd = verdict ? verdict[t] : undefined;
    const cls = vd === true ? "pass" : vd === false ? "warn" : "info";
    const txt = vd === true ? "Bereaksi" : vd === false ? "Tidak berubah" : vd === "idle" ? "Tidak aktif (tidak diuji)" : "Ada";
    return `<tr><td>${esc(label)}<br><span class="muted">${esc(x.name)}</span></td><td class="${cls}">${txt}</td><td>${esc(val)}</td></tr>`;
  });
  return `<table><tr><th>Sensor</th><th>Status</th><th>Nilai terakhir</th></tr>${rows.join("")}</table>`;
}

const kv = (pairs) => `<dl class="kv">${pairs.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join("")}</dl>`;
const PHOTO_OK = /^\/storage\/emulated\/0\/[\w./ ()-]+$/;

export async function renderComponents(view, { sh, getId }) {
  view.innerHTML = `
    <div class="card"><h2>Uji komponen</h2>
      <p class="muted">Setiap uji menjalankan perintah ke HP, lalu kamu menilai hasilnya. Penilaian tersimpan dan ikut ke laporan servis.</p>
      <div id="tsum" class="stats"></div></div>
    <div class="cols">${CARDS.map((c) => `
      <section class="card tc" data-t="${c.id}">
        <h2>${esc(c.title)}<span class="tc-st"></span></h2>
        <p class="muted">${esc(c.hint)}</p>
        <div class="row">${c.actions.map(([a, l]) => `<button data-a="${a}">${esc(l)}</button>`).join("")}</div>
        <div class="tc-out"></div>
        <div class="row tc-judge" hidden>
          <input class="tc-note" placeholder="Catatan untuk laporan (opsional)" />
          <button data-j="PASS">Normal</button><button data-j="WARN">Perlu dicek</button><button data-j="FAIL">Bermasalah</button>
        </div>
      </section>`).join("")}</div>`;

  const KEYS = ["battery", "storage", ...CARDS.map((c) => c.id)];
  const paint = () => {
    const all = getTests(getId());
    for (const c of CARDS) {
      const el = view.querySelector(`[data-t="${c.id}"] .tc-st`);
      if (!el) continue;
      const st = all[c.id]?.status || "INFO";
      el.className = `tc-st ${CLS[st]}`;
      el.textContent = LABEL[st];
    }
    const count = (s) => KEYS.filter((k) => all[k]?.status === s).length;
    const sum = view.querySelector("#tsum");
    if (sum) {
      const left = KEYS.filter((k) => !all[k]).length;
      sum.innerHTML = `<div><b>${count("PASS")}</b><span>Normal</span></div><div><b>${count("WARN")}</b><span>Perlu dicek</span></div><div><b>${count("FAIL")}</b><span>Bermasalah</span></div><div><b>${left}</b><span>Belum diuji</span></div>`;
    }
  };
  const record = (id, status, note) => {
    saveTest(getId(), id, { name: TITLE[id], status, note: note || "" });
    paint();
  };
  paint();

  const openOnPhone = async (hash) => {
    const url = `${location.origin}/screentest.html#${hash}`;
    await sh("input keyevent 224");
    const r = await sh(`am start -a android.intent.action.VIEW -d "${url}"`);
    return { url, failed: /error|exception/i.test(r), local: /localhost|127\.0\.0\.1/.test(url) };
  };
  const openMsg = (o, what) => o.failed
    ? `<p class="warn">HP tidak bisa membuka browser. Buka alamat ini di browser HP: <b>${esc(o.url)}</b></p>`
    : `<p>${what} Alamat: <b>${esc(o.url)}</b>${o.local ? "<br><span class=\"warn\">Alamat lokal tidak bisa dibuka dari HP. Pakai versi yang sudah dipublikasikan.</span>" : ""}</p>`;

  const newPhotos = async (minutes) => {
    const out = await sh(`find /storage/emulated/0/DCIM /storage/emulated/0/Pictures -type f -mmin -${minutes} 2>/dev/null | head -n 8`);
    return out.split("\n").map((s) => s.trim()).filter((p) => PHOTO_OK.test(p) && !p.split("/").pop().startsWith(".") && /\.(jpe?g|heic|png|webp|dng)$/i.test(p));
  };
  let shots = [];
  const shoot = async (out, front) => {
    await sh("input keyevent 224");
    const before = new Set(await newPhotos(1));
    const extra = front ? " --ei android.intent.extras.CAMERA_FACING 1 --ez android.intent.extra.USE_FRONT_CAMERA true" : "";
    const r = await sh(`am start -a android.media.action.STILL_IMAGE_CAMERA${extra}`);
    if (/error|exception/i.test(r)) throw new Error("Aplikasi kamera tidak bisa dibuka. " + (r.split("\n")[0] || ""));
    out.innerHTML = `<p class="muted">Kamera dibuka, menunggu fokus…</p>`;
    await sleep(3500);
    await sh("input keyevent 27");
    out.innerHTML = `<p class="muted">Mengambil foto…</p>`;
    await sleep(3500);
    shots = (await newPhotos(1)).filter((p) => !before.has(p));
    if (shots.length) {
      record("camera", "PASS", `Foto uji ${front ? "depan" : "belakang"} berhasil tersimpan.`);
      out.innerHTML = `<p class="pass">Foto baru tersimpan, jadi kamera ${front ? "depan" : "belakang"} bekerja.</p><p class="muted">${shots.map(esc).join("<br>")}</p>`;
    } else {
      record("camera", "WARN", `Foto uji ${front ? "depan" : "belakang"} tidak terdeteksi.`);
      out.innerHTML = `<p class="warn">Tidak ada foto baru. Mungkin tombol rana butuh ditekan manual (pakai Mirror), atau kamera gagal. Tekan rana, lalu <b>Cek foto baru</b>.</p>`;
    }
  };

  const RUN = {
    sensor: {
      async read({ out }) {
        out.innerHTML = `<p class="muted">Membaca sensor…</p>`;
        const s = parseSensors(await sh("dumpsys sensorservice"));
        if (!Object.keys(s).length) { out.innerHTML = `<p class="warn">HP tidak membuka daftar sensor lewat ADB.</p>`; return false; }
        out.innerHTML = sensorTable(s, null) + `<p class="muted">Sensor hanya punya nilai terbaru bila sedang dipakai sistem. Kalau "belum ada data", putar layar atau ubah kecerahan otomatis, lalu baca lagi.</p>`;
        return true;
      },
      async move({ out }) {
        const samples = {};
        const stamps = {};
        let last = {};
        // Daftar "recent events" dumpsys hanya bergerak kalau ada aplikasi yang membaca sensor.
        // Buka halaman kecil di browser HP supaya accelerometer/gyro/kompas benar-benar aktif.
        await sh("input keyevent KEYCODE_WAKEUP");
        await sh(`am start -a android.intent.action.VIEW -d '${location.origin}/sensor.html'`);
        await sleep(2500);
        for (let i = 0; i < 12; i++) {
          out.innerHTML = `<p><b>Goyangkan HP, miringkan, tutup sensor dekat speaker, senter ke sensor cahaya.</b> ${12 - i} detik lagi.</p>`;
          last = parseSensors(await sh("dumpsys sensorservice"));
          for (const t of Object.keys(last)) {
            const n = last[t].events.length;
            const ev = last[t].events[n - 1];
            if (ev) {
              (samples[t] = samples[t] || []).push(ev);
              (stamps[t] = stamps[t] || new Set()).add(last[t].stamps[n - 1] || JSON.stringify(ev));
            }
          }
          await sleep(700);
        }
        await sh("input keyevent KEYCODE_BACK");
        const verdict = {};
        for (const [t] of WANT) {
          // cap waktu event terakhir tidak maju = sensor tidak sedang dipakai sistem (bukan tanda rusak)
          verdict[t] = !stamps[t] || stamps[t].size < 2 ? (samples[t] ? "idle" : null) : reacted(t, samples[t]);
        }
        out.innerHTML = sensorTable(last, verdict);
        const core = ["accelerometer", "proximity", "light"];
        const present = core.filter((t) => last[t]);
        if (!Object.keys(samples).length) {
          out.innerHTML += `<p class="warn">Tidak ada data sensor selama uji. Nyalakan rotasi otomatis dan kecerahan otomatis, lalu ulangi.</p>`;
          return true;
        }
        const bad = present.filter((t) => verdict[t] === false);
        const idle = present.filter((t) => verdict[t] === "idle");
        const missing = core.filter((t) => !last[t]);
        if (idle.length) {
          out.innerHTML += `<p class="muted">Proximity dan sensor cahaya biasanya hanya aktif saat sistem memakainya (mis. saat panggilan atau kecerahan otomatis menyala). Yang berstatus "Tidak aktif" bukan berarti rusak; uji manual: tutup bagian atas layar dengan tangan dan lihat layar mati saat panggilan, serta ubah kecerahan otomatis di bawah lampu terang.</p>`;
        }
        if (!bad.length && !missing.length && !idle.length && present.every((t) => verdict[t] === true)) record("sensor", "PASS", "Accelerometer, proximity, dan cahaya bereaksi.");
        else record("sensor", "WARN", [bad.length ? `Tidak berubah: ${bad.join(", ")}.` : "", idle.length ? `Tidak aktif saat uji (perlu uji manual): ${idle.join(", ")}.` : "", missing.length ? `Tidak terdeteksi: ${missing.join(", ")}.` : ""].filter(Boolean).join(" ") || "Data sensor kurang lengkap.");
        return true;
      },
    },

    camera: {
      async info({ out }) {
        const c = parseCameras(await sh("dumpsys media.camera"));
        if (c.count == null) { out.innerHTML = `<p class="warn">Layanan kamera tidak menjawab. Mulai ulang HP lalu coba lagi.</p>`; return false; }
        const gone = c.status.filter((s) => s !== "PRESENT");
        out.innerHTML = kv([["Kamera terdaftar", String(c.count)], ["Kamera belakang", c.hasBack ? "Ada" : "Tidak terbaca"], ["Kamera depan", c.hasFront ? "Ada" : "Tidak terbaca"], ["Status modul", c.status.length ? [...new Set(c.status)].join(", ") : "Tidak terbaca"]]) +
          (gone.length ? `<p class="fail">Ada modul kamera yang tidak terdeteksi (${esc([...new Set(gone)].join(", "))}). Periksa flexible atau modul kamera.</p>` : "");
        if (gone.length) record("camera", "FAIL", `Modul kamera: ${[...new Set(gone)].join(", ")}.`);
        return true;
      },
      back: ({ out }) => shoot(out, false),
      front: ({ out }) => shoot(out, true),
      async check({ out }) {
        shots = await newPhotos(3);
        out.innerHTML = shots.length ? `<p class="pass">${shots.length} foto baru dalam 3 menit terakhir.</p><p class="muted">${shots.map(esc).join("<br>")}</p>` : `<p class="warn">Belum ada foto baru dalam 3 menit terakhir.</p>`;
        if (shots.length) record("camera", "PASS", "Foto uji tersimpan.");
        return true;
      },
      async clean({ out }) {
        const list = shots.filter((p) => PHOTO_OK.test(p));
        if (!list.length) { out.innerHTML = `<p class="muted">Tidak ada foto uji yang tercatat. Ambil foto uji dulu.</p>`; return false; }
        if (!confirm(`Hapus ${list.length} foto uji ini dari HP?\n\n${list.join("\n")}`)) return false;
        for (const p of list) await sh(`rm "${p}"`);
        shots = [];
        out.innerHTML = `<p class="pass">Foto uji dihapus.</p>`;
        return false;
      },
    },

    audio: {
      async info({ out }) {
        const raw = await sh('dumpsys audio | grep -m6 -iE "mic mute|mic_mute|microphone"');
        const muted = /mic(?:rophone)?[ _]?mute[^\n]*?(true|1)\b/i.test(raw);
        out.innerHTML = muted
          ? `<p class="fail">Mikrofon dalam keadaan dibisukan oleh sistem.</p>`
          : `<p class="pass">Mikrofon tidak dibisukan oleh sistem.</p>`;
        if (raw) out.innerHTML += `<pre>${esc(raw)}</pre>`;
        return true;
      },
      async rec({ out }) {
        await sh("input keyevent 224");
        const r = await sh("am start -a android.provider.MediaStore.RECORD_SOUND");
        out.innerHTML = /error|exception/i.test(r)
          ? `<p class="warn">HP tidak punya aplikasi perekam suara bawaan. Buka perekam apa pun lewat Mirror.</p>`
          : `<p>Perekam suara dibuka di HP. Rekam beberapa detik, putar ulang, lalu nilai.</p>`;
        return true;
      },
    },

    display: {
      async info({ out }) {
        const [size, dens, fps] = await Promise.all([
          sh("wm size"),
          sh("wm density"),
          sh('dumpsys display | grep -m3 -iE "refreshRate|renderFrameRate|fps"'),
        ]);
        const size1 = (size.match(/Physical size:\s*(\S+)/i) || [])[1] || (size.match(/(\d+x\d+)/) || [])[1] || "tidak terbaca";
        const dens1 = (dens.match(/Physical density:\s*(\d+)/i) || [])[1] || (dens.match(/(\d+)/) || [])[1] || "tidak terbaca";
        const hz = (fps.match(/(?:refreshRate|renderFrameRate|fps)[ =]+([\d.]+)/i) || [])[1];
        out.innerHTML = kv([["Resolusi fisik", size1], ["Kepadatan", dens1 + (dens1 === "tidak terbaca" ? "" : " dpi")], ["Refresh rate", hz ? `${Number(hz).toFixed(0)} Hz` : "tidak terbaca"]]);
        return false;
      },
      async color({ out }) {
        const o = await openOnPhone("warna");
        out.innerHTML = openMsg(o, "Uji warna dibuka di HP. Ketuk layar HP untuk ganti warna.");
        return !o.failed;
      },
    },

    touch: {
      async open({ out }) {
        const o = await openOnPhone("sentuh");
        out.innerHTML = openMsg(o, "Uji sentuhan dibuka di HP. Usap seluruh layar sampai semua kotak menyala.");
        return !o.failed;
      },
    },
  };

  let busy = false;
  const lock = (on) => { busy = on; view.querySelectorAll("button, input").forEach((el) => { el.disabled = on; }); };
  view.onclick = async (e) => {
    const b = e.target.closest("button");
    if (!b || busy) return;
    const card = b.closest(".tc");
    if (!card) return;
    const id = card.dataset.t;
    const judge = card.querySelector(".tc-judge");
    if (b.dataset.j) {
      record(id, b.dataset.j, card.querySelector(".tc-note").value.trim());
      judge.hidden = true;
      return;
    }
    const fn = RUN[id] && RUN[id][b.dataset.a];
    if (!fn) return;
    const out = card.querySelector(".tc-out");
    lock(true);
    try {
      const showJudge = await fn({ out });
      judge.hidden = showJudge === false;
    } catch (err) {
      out.innerHTML = `<p class="fail">Gagal: ${esc(err?.message || err)}</p>`;
    } finally {
      lock(false);
    }
  };
  return () => { view.onclick = null; };
}
