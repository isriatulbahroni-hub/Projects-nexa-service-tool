# Mirror Real-time & Koneksi Wi-Fi

Fitur ini menambah mirror layar real-time (stream H.264 lewat scrcpy-server v5.0.1)
dan koneksi ADB tanpa kabel. `core/mirror.py` (screencap) tidak diubah dan tetap bisa
dipakai sebagai cadangan.

## Modul

| File | Fungsi |
| --- | --- |
| `core/scrcpy_client.py` | Klien scrcpy-server: push, forward, stream H.264, decode (PyAV), kontrol sentuh/tombol/teks/scroll |
| `core/realtime_mirror.py` | Pembungkus Qt (`RealtimeMirror`), API mirip `ScreenMirror`; hanya frame terbaru dikirim ke GUI |
| `core/wireless_adb.py` | `adb pair` (kode & QR), `adb connect`, mDNS, USB → Wi-Fi |
| `ui/realtime_mirror_page.py` | `RealtimeMirrorPanel` (widget mandiri) |
| `ui/mirror_integration.py` | Memasang panel ke halaman Screen Mirror `MainWindow` |

## Terpasang di halaman Screen Mirror

`main.py` memanggil `ui.mirror_integration.install_realtime_mirror(MainWindow)` sebelum
jendela dibuat. Halaman **Screen Mirror** lalu memakai `RealtimeMirrorPanel` (scrcpy)
menggantikan polling `screencap` lama (±1 fps). Saat membuka halaman, perangkat yang
sedang aktif otomatis dipilih; stream dihentikan otomatis saat pindah halaman / app ditutup.

Untuk memakai panel di tempat lain:

```python
from ui.realtime_mirror_page import RealtimeMirrorPanel

page = RealtimeMirrorPanel()
```

## Tuning performa

- Lewat Wi-Fi (serial `IP:port`) otomatis memakai profil ringan: 960 px, 30 fps, 3 Mbps.
  Lewat USB: 1280 px, 60 fps, 8 Mbps. Ubah di `RealtimeMirrorPanel.stream_profile`.
- Decoder H.264 dalam mode low-delay; jika PC tertinggal, konversi RGB frame usang dilewati.
- Di build `.exe`, scrcpy-server disimpan di `%LOCALAPPDATA%\NexaServiceTool\vendor`
  (bukan folder temp PyInstaller) sehingga tidak diunduh ulang tiap dijalankan.

## Catatan

- scrcpy-server diunduh sekali ke `vendor/` (diabaikan git) dan diverifikasi SHA-256.
  Jika PC offline, letakkan `scrcpy-server-v5.0.1` di `vendor/` secara manual.
- Versi server dan klien harus sama persis (`SCRCPY_VERSION` di `core/scrcpy_client.py`).
- Pair via QR butuh HP dan PC di Wi-Fi yang sama dan mDNS tidak diblokir jaringan.
  Jika gagal, pakai pair dengan kode 6 digit.
- Layar yang diproteksi aplikasi (mis. m-banking) tampil hitam.
