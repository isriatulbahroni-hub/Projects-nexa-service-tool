// Utilitas kecil untuk halaman Hardware Test (pembacaan langsung dan uji manual).

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Batas waktu untuk satu panggilan ke HP. Panggilan yang macet tidak bisa dibatalkan,
// tapi pemanggil tidak ikut menggantung.
export function withTimeout(promise, ms, message) {
  let t;
  return Promise.race([
    promise,
    new Promise((_, reject) => { t = setTimeout(() => reject(new Error(message)), ms); }),
  ]).finally(() => clearTimeout(t));
}

// Baris pertama keluaran, dipotong, untuk ditampilkan sebagai bukti jawaban asli HP.
export const snippet = (s, n = 100) => String(s ?? "").trim().split("\n")[0].slice(0, n) || "(kosong)";

// Antrean perintah ADB: satu perintah pada satu waktu, supaya pembacaan otomatis dan uji manual
// tidak saling berebut koneksi USB. `shx` harus MELEMPAR galat kalau koneksi/pengiriman gagal
// (berbeda dengan sh() yang menelan galat dan mengembalikan teks kosong).
export function createRunner(shx) {
  let chain = Promise.resolve();
  let fails = 0;
  const run = (cmd, ms = 15000) => {
    const task = chain.then(() =>
      withTimeout(Promise.resolve(shx(cmd)), ms, `HP tidak merespons (${String(cmd).split(" ")[0]}).`));
    chain = task.then(
      () => { fails = 0; },
      (e) => { if (/tidak merespons/.test(String(e?.message))) fails++; },
    );
    return task;
  };
  return { run, fails: () => fails };
}
