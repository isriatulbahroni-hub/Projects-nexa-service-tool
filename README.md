# Nexa Service Tool

Alat bantu untuk konter dan teknisi servis HP Android: diagnosa perangkat, mirror dan kontrol layar, manajemen kasus servis, nota, sparepart, dan laporan.

Proyek ini punya **dua versi** yang berdiri sendiri:

| Versi | Lokasi | Teknologi | Dipakai di |
|---|---|---|---|
| **Desktop** | root (`main.py`, `app.py`, `core/`, `ui/`) | Python, PySide6 | Windows/Linux, ADB lewat kabel atau Wi-Fi |
| **Web** | `web/` | Vite, WebUSB, Tango (ADB + scrcpy di browser) | Chrome/Edge di PC, atau Chrome Android + kabel OTG |

Status dokumen: per 7 November 2026. Bagian yang belum diverifikasi ditandai jelas. Kalau kode berubah, perbarui dokumen ini.

---

## Tujuan produk

- Teknisi/pemilik konter bisa memeriksa dan mengendalikan HP pelanggan **tanpa harus memegang laptop**: cukup HP sendiri + kabel OTG (versi web/PWA).
- Jalur nirkabel (Wi-Fi) membutuhkan aplikasi Android asli (browser tidak boleh membuka koneksi TCP mentah). Itu **belum dibangun**.
- Bluetooth **tidak dipakai**: ADB dan scrcpy tidak berjalan lewat Bluetooth dan bandwidth-nya tidak cukup untuk video layar.
- Rencana jual: aplikasi desktop lewat Shopee (lihat bagian Lisensi).

---

## Struktur repo

```
main.py            entry point desktop (memanggil app.py)
app.py             GUI utama desktop (PySide6, file besar)
core/              logika desktop (ADB, diagnosa, kasus servis, nota, dll.)
ui/                halaman/panel PySide6 terpisah (mirror real-time, smart diagnosis)
tools/             skrip bantu pengembangan
tests/             tes (pytest, lihat pytest.ini)
web/               versi web (Vite) + konfigurasi Vercel
.github/           konfigurasi GitHub
requirements.txt   dependensi Python
```

---

## Versi Web (`web/`)

Di-deploy ke Vercel. Semua pembacaan device lewat ADB di browser (WebUSB), tanpa server.

### Menjalankan lokal

```
cd web
npm install
npm run dev
```

`npm run dev` dan `npm run build` otomatis menjalankan `scripts/fetch-scrcpy-server.mjs`, yang mengunduh `scrcpy-server` v5.0.1 dari rilis resmi Genymobile/scrcpy ke `web/public/scrcpy-server.bin`. File itu tidak dicommit.

### Deploy ke Vercel

1. Import repo ini, pilih branch produksi (`main`).
2. **Root Directory = `web`**, Framework = Vite. Tanpa ini Vercel membaca `app.py` di root dan gagal dengan `PYTHON_ENTRYPOINT_NOT_FOUND`.
3. Proteksi SSO Vercel aktif secara default untuk semua deployment. Matikan di pengaturan project kalau halaman harus bisa dibuka publik.

### Syarat pemakaian

- Chrome atau Edge (WebUSB dan WebCodecs), halaman HTTPS.
- USB debugging aktif di HP target dan dialog izin disetujui di layar HP target.
- Di PC: jalankan `adb kill-server` supaya ADB server bawaan tidak merebut koneksi USB.
- Di HP (tanpa PC): kabel OTG dari HP teknisi ke HP pelanggan. Belum diuji dengan perangkat asli.

### Halaman dan fungsinya

| Halaman | Fungsi | Catatan |
|---|---|---|
| Dashboard | Model, versi Android, security patch, serial, baterai, suhu, storage, RAM, IP Wi-Fi | Baca-saja |
| Info Device | Semua properti `getprop`, bisa dicari | Belum menampilkan IMEI |
| Hardware Test | Kesehatan baterai, suhu, thermal, RAM, storage, Wi-Fi, SIM, jumlah crash/ANR di logcat, keberadaan komponen | Baris komponen (kamera, sensor, dll.) hanya berarti HP **mengaku** punya komponen itu, bukan komponennya hidup |
| Security | Verified boot, bootloader, enkripsi, SELinux, umur security patch, build debuggable, cek file `su`, setup wizard | Cek root hanya mencari file `su`; Magisk modern bisa lolos |
| Aplikasi | Daftar paket pihak ketiga dan sistem, detail versi | Belum bisa hapus/nonaktifkan |
| File | Menelusuri `/sdcard` | Hanya daftar, belum bisa ambil file |
| Mirror | Video real-time scrcpy, sentuh/geser, tombol Back/Home/Recents, screenshot | **Mengendalikan HP**, bukan baca-saja. Belum ada keyboard, scroll, Power/Volume. Ada panduan lipat untuk layar yang tidak bisa disentuh |
| Terminal & Log | Shell ADB bebas, tombol cepat (logcat, crash log, battery, meminfo, storage) | Konfirmasi hanya untuk kata kunci tertentu (`rm`, `reboot`, `setprop`, dll.); tidak menjamin semua perintah berbahaya tertangkap |

PWA: ada `manifest.webmanifest`, ikon SVG, dan service worker (network-first, cadangan cache) supaya bisa ditambahkan ke layar utama. Ikon masih SVG; kalau Chrome tidak menawarkan "Instal", tambahkan ikon PNG 192 dan 512.

### Catatan teknis penting

- Memakai **Tango (`@yume-chan/*`) 3.0.0-beta.5**. Semua paket yume-chan harus satu versi yang sama.
- Versi server scrcpy harus cocok dengan kelas opsi di kode: server **5.0.1** ↔ `AdbScrcpyOptions5_0_1`. Kalau mengganti salah satu, ganti keduanya (`scripts/fetch-scrcpy-server.mjs` dan `src/main.js`).
- API Tango 3.0 berbeda dari 2.x: `spawnWaitText` diganti `adb.subprocess.noneProtocol.spawn(cmd).wait().toString()`, `adb.sync` adalah properti, autentikasi lewat `adbDaemonAuthenticate` dengan `AdbWebCryptoCredentialManager`.
- Tombol navigasi memakai kode angka mentah (Home=3, Back=4, Recents=187). Konstanta `AndroidKeyCode.Home` di library adalah tombol Home keyboard (122), bukan tombol Home Android.
- Kunci ADB disimpan di `localStorage` browser (`nexa-service-web-adb-key`). Belum ada tombol untuk menghapusnya.

---

## Versi Desktop (Python/PySide6)

```
pip install -r requirements.txt
python main.py
```

Dependensi: PySide6 (GUI), reportlab (PDF), psutil, pyzipper (arsip zip), av (decode video scrcpy), qrcode[pil] (QR pairing).
Butuh `adb` dan `fastboot` (platform-tools). Lokasi default diatur di `core/config.py`; `core/tool_router.py` mencari di PATH sebagai cadangan.

### Modul yang sudah diverifikasi isinya

- **`core/service_cases.py`**: manajemen kasus servis di SQLite (`data/nexa_service.db`). Nomor kasus `NS-YYYYMMDD-NNNN`; status `Received, Diagnosing, Repairing, Testing, Completed, Cancelled`; pembayaran `Belum Bayar, DP, Lunas` dengan jumlah terbayar; estimasi selesai; foto per kasus; linimasa kejadian (status, catatan, pembayaran, edit, foto); koreksi data awal; ringkasan bisnis per rentang tanggal (jumlah kasus, pendapatan, sisa tagihan, rata-rata waktu pengerjaan, per teknisi); ekspor CSV untuk pembukuan.
- **`core/licensing.py`**: login teknisi (PBKDF2-SHA256, file `data/technicians.json`) dan lisensi offline berbasis HMAC (`NEXA-<payload>-<signature>`, `data/license.json`). Peran `technician` / `admin`.
- **`core/frp_service.py`**: alur FRP **verifikasi**, bukan bypass. Membaca status device, reboot standar ke recovery/bootloader (hanya mode yang di-allowlist), verifikasi ulang. Tombol aksi hanya aktif bila verifikasi pemilik tidak diwajibkan.
- **`core/tool_router.py`**: mencari `adb`/`fastboot` dan merekomendasikan tool **resmi** per merek (Odin, Mi Flash, Android Flash Tool, dll.). Tidak pernah mengunduh atau menjalankan tool unlock pihak ketiga.
- **Mirror**: `core/mirror.py` (screenshot berulang), `core/scrcpy_client.py` + `core/realtime_mirror.py` + `ui/realtime_mirror_page.py` (scrcpy real-time, kontrol sentuh/tombol/teks/scroll), `core/wireless_adb.py` (ADB Wi-Fi: pair lewat kode atau QR). Semua ini datang dari PR #1 (sudah di-merge ke `main`), dengan server scrcpy v5.0.1. Panel baru **belum terpasang di `app.py`** per 7 Nov 2026.

### Modul lain (ringkasan dari nama file, **belum diverifikasi isinya**)

`device_diagnostics`, `diagnostics`, `smart_diagnosis` (+ `ui/smart_diagnosis_*`), `hardware_test`, `hardware_report`, `security_check`, `network_info`, `logcat`, `packages`, `file_explorer`, `parts` (sparepart), `invoice` (nota), `whatsapp`, `report`, `backup`, `db_backup`, `database`, `firmware`, `factory_reset*`, `recovery_actions`, `device_access_recovery`, `locked_device_recovery`, `automation`, `settings`, `async_worker`, `task_runner`, `app_logging`.
Baca modulnya sebelum mengubah atau mendokumentasikan lebih lanjut.

---

## Kebijakan dan batasan yang harus dijaga

- **Tidak ada bypass.** Proyek ini sengaja tidak menyediakan cara melewati kunci layar (PIN/pola/password) atau FRP, dan tidak boleh ditambahkan. Alur yang ada hanya verifikasi, reboot standar, dan rekomendasi tool resmi, dengan verifikasi kepemilikan (nota/KTP) sebelum aksi pemulihan.
- HP yang terkunci: pemilik membukanya sendiri. Lupa PIN: reset lewat recovery dengan persetujuan pemilik (data terhapus, akun Google dimasukkan pemilik).
- HP yang tidak bisa menyala tidak bisa dibantu alat ini (ADB butuh Android yang berjalan). Layar tidak bisa disentuh: pakai mouse OTG untuk mengaktifkan USB debugging dan menyetujui dialog, lalu mirror.
- Versi web mengendalikan HP lewat Mirror dan Terminal, jadi jangan lagi menyebutnya "baca-saja".

---

## Masalah yang sudah diketahui

1. **Mirror web belum diuji dengan HP asli.** Hanya build Vercel yang terverifikasi. Kemungkinan perlu penyesuaian saat uji pertama.
2. Hardware Test web: label "PASS / Terdeteksi" pada komponen menyesatkan (lihat tabel).
3. Kunci ADB web tersimpan di `localStorage` tanpa tombol hapus. Kalau HP teknisi dipinjam, kunci itu bisa dipakai ke HP lain yang pernah memilih "selalu izinkan".
4. `core/licensing.py` memakai secret bawaan `nexa-service-tool-default-secret-CHANGE-ME` kalau env `NEXA_LICENSE_SECRET` tidak diisi. **Ganti sebelum dijual.** Modul ini juga tertulis belum di-wire ke `app.py`; periksa status terbarunya.
5. Proteksi SSO Vercel membuat URL deployment meminta login Vercel.
6. Branch lain di repo (`feat/usb-diagnostics`, `fix/frp-button-gating-imei-fallback`, `fix/mirror-lag-security-check-sidebar`, `fix/ui-click-responsiveness`) belum diperiksa. Cek sebelum mengerjakan fitur serupa agar tidak dobel.

---

## Rencana (urut prioritas)

1. Uji Mirror web dengan HP asli lewat kabel OTG.
2. Web: baca IMEI/serial, ambil file (pull), install APK, reboot ke recovery/bootloader, keyboard dan scroll di Mirror, tombol Power/Volume.
3. Web: tombol hapus kunci ADB, perbaiki label Hardware Test, ikon PNG untuk PWA.
4. Desktop: pasang panel mirror real-time dan ADB Wi-Fi ke `app.py`; wire lisensi dan login teknisi.
5. Web: fitur bisnis (kasus servis, nota) yang saat ini hanya ada di desktop.
6. Aplikasi Android (Capacitor atau Kotlin) dengan library ADB-over-TCP untuk jalur Wi-Fi tanpa PC.

---

## Panduan untuk pengembang atau sesi AI berikutnya

- Sebelum membuat fitur: cek `git branch -a`, PR terbuka, dan isi `core/` serta `web/src/main.js` agar tidak dobel. Banyak fitur sudah ada di salah satu versi.
- Kerjakan di branch baru; jangan langsung ke `main`. Merge ke `main` memicu deploy production di Vercel.
- Setelah push ke branch web, periksa build preview Vercel. Build lolos belum berarti fitur jalan di HP.
- Jangan menyebut sesuatu "berfungsi" kalau hanya dibaca dari kode. Tulis apa yang diuji dan apa yang tidak.
- Jangan menambah bypass kunci layar/FRP, dan jangan menyimpan secret asli di repo.
- Bahasa antarmuka dan dokumentasi: Indonesia.
