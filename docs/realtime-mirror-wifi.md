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

## Memasang panel di app.py

Panel mandiri: punya daftar perangkat sendiri, jadi tidak bergantung pada perangkat
terpilih di bagian lain aplikasi.

```python
from ui.realtime_mirror_page import RealtimeMirrorPanel

page = RealtimeMirrorPanel()   # daftarkan seperti halaman lain di sidebar
```

## Catatan

- scrcpy-server diunduh sekali ke `vendor/` (diabaikan git) dan diverifikasi SHA-256.
  Jika PC offline, letakkan `scrcpy-server-v5.0.1` di `vendor/` secara manual.
- Versi server dan klien harus sama persis (`SCRCPY_VERSION` di `core/scrcpy_client.py`).
- Pair via QR butuh HP dan PC di Wi-Fi yang sama dan mDNS tidak diblokir jaringan.
  Jika gagal, pakai pair dengan kode 6 digit.
- Layar yang diproteksi aplikasi (mis. m-banking) tampil hitam.
