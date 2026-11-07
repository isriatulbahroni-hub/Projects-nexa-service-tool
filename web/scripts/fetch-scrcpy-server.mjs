// Mengunduh scrcpy-server dari rilis resmi Genymobile/scrcpy ke public/.
// Dijalankan otomatis sebelum `npm run dev` dan `npm run build`.
// Versi harus sama dengan opsi AdbScrcpyOptions5_0_1 di src/main.js.
import { access, mkdir, writeFile } from "node:fs/promises";

const VERSION = "5.0.1";
const target = new URL("../public/scrcpy-server.bin", import.meta.url);

try {
  await access(target);
  console.log(`scrcpy-server v${VERSION} sudah ada, dilewati.`);
  process.exit(0);
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

await mkdir(new URL("../public/", import.meta.url), { recursive: true });
await writeFile(target, Buffer.from(await res.arrayBuffer()));
console.log("scrcpy-server tersimpan di public/scrcpy-server.bin");
