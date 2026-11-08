# Nexa Service Tool Web

Versi website (WebUSB) dari Nexa Service Tool. Terhubung langsung ke HP lewat browser, tanpa data demo.

Dokumentasi lengkap (fitur, batasan, rencana) ada di [README di root repo](../README.md).

## Fitur singkat

- Pemeriksaan baca-saja: Dashboard, Info Device, Hardware Test, Security, Aplikasi, File.
- **Uji manual interaktif** di Hardware Test: getaran, suara, kecerahan layar, tombol fisik (Vol+, Vol−, Power), port USB/pengisian. Hasil dinilai teknisi (Normal / Bermasalah).
- **Mirror real-time (scrcpy v5.0.1)** dengan kontrol sentuh, tombol Back/Home/Recents, dan screenshot. Fitur ini **mengendalikan HP**.
  - Server scrcpy diunduh di latar belakang saat halaman dibuka dan tidak dikirim ulang ke HP kalau sudah ada.
  - Profil kualitas Ringan (720p, bawaan), Normal (1024p), Tajam (1600p).
  - Tiap tahap punya batas waktu; kalau push lewat sync macet, otomatis memakai jalur cadangan lewat shell.
- Terminal ADB shell. Ini juga bisa mengubah HP; hati-hati dengan perintahnya.
- PWA: bisa ditambahkan ke layar utama.

## Deploy ke Vercel

1. Import repo ini di Vercel, pilih branch `main`.
2. Atur **Root Directory** ke `web`. Framework Vite terdeteksi otomatis.
3. Deploy, lalu buka URL HTTPS-nya di Chrome/Edge. Kalau halaman harus publik, matikan proteksi SSO Vercel di pengaturan project.

## Memakai

- Aktifkan USB debugging di HP, colok kabel USB (di HP teknisi: kabel OTG).
- Di komputer jalankan `adb kill-server` (ADB server bawaan merebut koneksi USB).
- Tekan **Hubungkan HP (USB)**, pilih perangkat, lalu izinkan debugging di layar HP.
- Layar HP tidak bisa disentuh? Lihat panduan lipat di halaman Mirror (mouse OTG untuk mengaktifkan USB debugging).

## Lokal

```
cd web
npm install
npm run dev
```

`npm run dev` dan `npm run build` mengunduh `scrcpy-server` v5.0.1 ke `public/scrcpy-server.bin` lebih dulu.
