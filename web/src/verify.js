// Verifikasi integritas file yang akan dijalankan di HP pelanggan.
// Nilai ini harus sama dengan SHA256 di scripts/fetch-scrcpy-server.mjs
// dan SERVER_SHA256 di core/scrcpy_client.py (versi desktop). Ganti ketiganya bersamaan
// kalau versi scrcpy-server dinaikkan.
export const SCRCPY_SERVER_SHA256 = "764eb6f79811d5211fe9df341120882ba9994c7a61b897d7bf3fb662e53bc536";

export async function sha256Hex(bytes) {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}
