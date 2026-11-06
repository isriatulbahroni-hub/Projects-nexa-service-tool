# Nexa Service Tool Web

Versi website (WebUSB) dari Nexa Service Tool. Terhubung langsung ke HP asli lewat browser, tanpa data demo. Semua pemeriksaan bersifat baca-saja.

## Deploy ke Vercel

1. Import repo ini di Vercel, pilih branch `web-vercel`.
2. Atur **Root Directory** ke `web`. Framework Vite terdeteksi otomatis.
3. Deploy, lalu buka URL HTTPS-nya di Chrome/Edge.

## Memakai

- Aktifkan USB debugging di HP, colok kabel USB.
- Di komputer jalankan `adb kill-server` (ADB server bawaan merebut koneksi USB).
- Tekan **Hubungkan HP (USB)**, pilih perangkat, lalu izinkan debugging di layar HP.

## Lokal

```
cd web
npm install
npm run dev
```
