// DIBUAT OTOMATIS oleh tools/export_shared.py - jangan diedit manual.
export default {
  "bootloop_steps": [
    {
      "id": "hardware_suspect",
      "title": "Periksa tanda kerusakan fisik",
      "detail": "Cek baterai kembung, bekas air, konektor longgar, dan tombol power atau volume yang tertahan sebelum menyalahkan software.",
      "modes": [
        "android",
        "recovery",
        "sideload",
        "fastboot",
        "fastbootd",
        "unauthorized",
        "offline",
        "none"
      ],
      "data_loss": "none"
    },
    {
      "id": "charge_restart",
      "title": "Isi daya lalu paksa restart",
      "detail": "Isi daya minimal 30 menit dengan charger asli, lalu tahan tombol power 10 sampai 20 detik untuk paksa restart.",
      "modes": [
        "android",
        "recovery",
        "sideload",
        "fastboot",
        "fastbootd",
        "unauthorized",
        "offline",
        "none"
      ],
      "data_loss": "none"
    },
    {
      "id": "wipe_cache",
      "title": "Hapus partisi cache dari recovery",
      "detail": "Masuk recovery lalu pilih Wipe cache partition. Data pengguna tidak terhapus.",
      "modes": [
        "recovery"
      ],
      "data_loss": "none"
    },
    {
      "id": "sideload_ota",
      "title": "Pasang ulang paket OTA resmi",
      "detail": "Pakai adb sideload dengan paket OTA resmi yang cocok dengan model dan versi. Data pengguna umumnya tetap.",
      "modes": [
        "recovery",
        "sideload"
      ],
      "data_loss": "none"
    },
    {
      "id": "reflash_boot",
      "title": "Flash ulang boot dan vbmeta stok",
      "detail": "Flash hanya image stok yang cocok dengan model dan codename. Bootloader harus terbuka.",
      "modes": [
        "fastboot",
        "fastbootd"
      ],
      "data_loss": "none"
    },
    {
      "id": "flash_full",
      "title": "Flash firmware stok lengkap",
      "detail": "Flash semua partisi stok. Data bisa terhapus, pastikan backup sudah ada.",
      "modes": [
        "fastboot",
        "fastbootd"
      ],
      "data_loss": "possible"
    },
    {
      "id": "factory_reset",
      "title": "Factory reset dari recovery",
      "detail": "Pilih Wipe data atau Factory reset. SEMUA data pengguna hilang. Lakukan hanya jika langkah aman lain gagal.",
      "modes": [
        "recovery"
      ],
      "data_loss": "all"
    }
  ],
  "modes": [
    "android",
    "recovery",
    "sideload",
    "fastboot",
    "fastbootd",
    "unauthorized",
    "offline",
    "none"
  ],
  "flash": {
    "common_partitions": [
      "boot",
      "recovery",
      "system",
      "vendor",
      "vbmeta",
      "dtbo"
    ],
    "critical_partitions": [
      "bootloader",
      "modem",
      "radio"
    ],
    "logical_partitions": [
      "odm",
      "odm_dlkm",
      "product",
      "system",
      "system_dlkm",
      "system_ext",
      "vendor",
      "vendor_dlkm"
    ],
    "queue_skip": [
      "efs",
      "frp",
      "metadata",
      "persist",
      "userdata"
    ]
  }
};
