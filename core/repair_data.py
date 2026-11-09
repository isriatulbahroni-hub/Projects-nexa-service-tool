"""Data aturan perbaikan. Bagian SHARED diekspor ke web/src/shared/repair-data.js
(lewat tools/export_shared.py). Ubah di sini, lalu jalankan: python tools/export_shared.py
"""
from __future__ import annotations

MODES = ["android", "recovery", "sideload", "fastboot", "fastbootd", "unauthorized", "offline", "none"]


def _step(step_id: str, title: str, detail: str, modes: list[str], data_loss: str) -> dict:
    # data_loss: none | possible | all. Langkah selain 'none' terkunci sampai langkah aman selesai/di-skip.
    return {"id": step_id, "title": title, "detail": detail, "modes": list(modes), "data_loss": data_loss}


BOOTLOOP_STEPS = [
    _step(
        "hardware_suspect",
        "Periksa tanda kerusakan fisik",
        "Cek baterai kembung, bekas air, konektor longgar, dan tombol power atau volume yang tertahan sebelum menyalahkan software.",
        MODES,
        "none",
    ),
    _step(
        "charge_restart",
        "Isi daya lalu paksa restart",
        "Isi daya minimal 30 menit dengan charger asli, lalu tahan tombol power 10 sampai 20 detik untuk paksa restart.",
        MODES,
        "none",
    ),
    _step(
        "wipe_cache",
        "Hapus partisi cache dari recovery",
        "Masuk recovery lalu pilih Wipe cache partition. Data pengguna tidak terhapus.",
        ["recovery"],
        "none",
    ),
    _step(
        "sideload_ota",
        "Pasang ulang paket OTA resmi",
        "Pakai adb sideload dengan paket OTA resmi yang cocok dengan model dan versi. Data pengguna umumnya tetap.",
        ["recovery", "sideload"],
        "none",
    ),
    _step(
        "reflash_boot",
        "Flash ulang boot dan vbmeta stok",
        "Flash hanya image stok yang cocok dengan model dan codename. Bootloader harus terbuka.",
        ["fastboot", "fastbootd"],
        "none",
    ),
    _step(
        "flash_full",
        "Flash firmware stok lengkap",
        "Flash semua partisi stok. Data bisa terhapus, pastikan backup sudah ada.",
        ["fastboot", "fastbootd"],
        "possible",
    ),
    _step(
        "factory_reset",
        "Factory reset dari recovery",
        "Pilih Wipe data atau Factory reset. SEMUA data pengguna hilang. Lakukan hanya jika langkah aman lain gagal.",
        ["recovery"],
        "all",
    ),
]

# Profil perbaikan per gejala (hanya desktop). Tiap aksi = perintah adb; 'wait' = jeda detik sesudahnya.
SYMPTOMS = {
    "lambat": {
        "title": "HP lambat atau lag",
        "actions": [
            {"id": "trim_caches", "title": "Bersihkan cache semua aplikasi", "cmd": ["shell", "pm", "trim-caches", "999999999999"]},
            {"id": "kill_background", "title": "Hentikan proses latar belakang", "cmd": ["shell", "am", "kill-all"]},
        ],
        "measure": ["mem_available_kb", "storage_free_kb"],
    },
    "storage_penuh": {
        "title": "Penyimpanan penuh",
        "actions": [
            {"id": "trim_caches", "title": "Bersihkan cache semua aplikasi", "cmd": ["shell", "pm", "trim-caches", "999999999999"]},
        ],
        "measure": ["storage_free_kb"],
    },
    "wifi_bermasalah": {
        "title": "WiFi bermasalah",
        "actions": [
            {"id": "wifi_off", "title": "Matikan WiFi", "cmd": ["shell", "svc", "wifi", "disable"], "wait": 2},
            {"id": "wifi_on", "title": "Nyalakan WiFi", "cmd": ["shell", "svc", "wifi", "enable"], "wait": 3},
        ],
        "measure": [],
    },
    "baterai_boros": {
        "title": "Baterai boros",
        "actions": [
            {"id": "reset_batterystats", "title": "Reset statistik baterai", "cmd": ["shell", "dumpsys", "batterystats", "--reset"]},
        ],
        "measure": ["battery_temp_c"],
    },
}

SHARED = {"bootloop_steps": BOOTLOOP_STEPS, "modes": MODES}
