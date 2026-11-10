// Mengunduh scrcpy-server dari rilis resmi Genymobile/scrcpy ke public/.
// Dijalankan otomatis sebelum `npm run dev` dan `npm run build`.
// Versi harus sama dengan opsi AdbScrcpyOptions5_0_1 di src/main.js.
// File ini dikirim ke HP dan dijalankan di sana, jadi isinya WAJIB diverifikasi SHA-256
// (nilai yang sama dengan SERVER_SHA256 di core/scrcpy_client.py versi desktop).
import { createHash } from "node:crypto";
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";

const VERSION = "5.0.1";
const SHA256 = "764eb6f79811d5211fe9df341120882ba9994c7a61b897d7bf3fb662e53bc536";
const target = new URL("../public/scrcpy-server.bin", import.meta.url);

const sha256 = (buf) => createHash("sha256").update(buf).digest("hex");

try {
  const existing = await readFile(target);
  if (sha256(existing) === SHA256) {
    console.log(`scrcpy-server v${VERSION} sudah ada dan checksum cocok, dilewati.`);
    process.exit(0);
  }
  console.warn("scrcpy-server di public/ checksum-nya tidak cocok; diunduh ulang.");
  await rm(target, { force: true });
} catch {
  // belum ada, lanjut unduh
}

const url = `https://github.com/Genymobile/scrcpy/releases/download/v${VERSION}/scrcpy-server-v${VERSION}`;
console.log(`Mengunduh ${url}`);
const res = await fetch(url);
if (!res.ok) {
  console.error(`Gagal mengunduh scrcpy-server: ${res.status} ${res.statusText}`);
  process.exit(1);
}

const data = Buffer.from(await res.arrayBuffer());
const got = sha256(data);
if (got !== SHA256) {
  console.error(`Checksum scrcpy-server TIDAK cocok, file ditolak.\n  harapan: ${SHA256}\n  didapat: ${got}`);
  process.exit(1);
}

await mkdir(new URL("../public/", import.meta.url), { recursive: true });
await writeFile(target, data);
console.log("scrcpy-server tersimpan di public/scrcpy-server.bin (checksum cocok)");
