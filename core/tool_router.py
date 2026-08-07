"""Resolusi path tool eksternal (ADB/Fastboot) dan rekomendasi tool resmi.

Modul ini murni membantu MENEMUKAN executable yang sudah terpasang di
sistem (fallback ketika path default di core/config.py tidak ditemukan)
dan memberi REKOMENDASI nama tool resmi/official sesuai brand device.

PENTING: ToolRouter tidak pernah men-download, menjalankan, atau
mengotomasi tool unlock/bypass pihak ketiga. select_tools_for_device()
hanya mengembalikan nama tool (string) sebagai referensi untuk teknisi -
konsisten dengan core/locked_device_recovery.py yang secara sengaja
tidak pernah menawarkan bypass FRP/PIN/password/pattern.
"""

from __future__ import annotations

import shutil
from pathlib import Path


class ToolRouter:
    """Helper ringan untuk mencari lokasi tool ADB/Fastboot dan memberi
    rekomendasi tool resmi per brand. Tidak menyimpan state berat, aman
    dibuat berkali-kali (mis. `_router = ToolRouter()` di banyak modul).
    """

    # Rekomendasi tool RESMI per brand group. Semua adalah tool official
    # dari OEM/Google untuk flashing firmware resmi & diagnostik biasa -
    # bukan tool unlock/bypass pihak ketiga.
    _BRAND_TOOLS: dict[str, tuple[str, ...]] = {
        "Samsung": ("Samsung Odin (official firmware flashing)", "Samsung Smart Switch"),
        "Xiaomi / Redmi / POCO": ("Mi Flash Tool (official)", "Mi Unlock (akun Mi resmi)"),
        "OPPO / realme": ("OPPO/realme official firmware tool", "Fastboot standar"),
        "vivo / iQOO": ("vivo official firmware tool", "Fastboot standar"),
        "Infinix / TECNO": ("XOS official firmware tool", "Fastboot standar"),
        "Motorola": ("Motorola Rescue and Smart Assistant (resmi)",),
        "Nokia / HMD": ("Nokia FIH/HMD official tool",),
        "Google Pixel": ("Android Flash Tool (Google resmi)",),
    }

    _DEFAULT_TOOLS: tuple[str, ...] = ("ADB standar", "Fastboot standar")

    def get_tool_path(self, name: str) -> Path | None:
        """Cari path executable `name` (mis. "adb", "fastboot") di PATH
        sistem. Dipakai sebagai fallback ketika path default di
        core/config.py (mis. ~/platform-tools/platform-tools/adb.exe)
        tidak ditemukan - misalnya kalau platform-tools di-install lewat
        package manager (choco/scoop/apt) dan sudah ada di PATH.
        """
        found = shutil.which(name)
        return Path(found) if found else None

    def select_tools_for_device(
        self,
        brand_group: str,
        device_mode: str,
        fastboot_connected: bool,
        authorized: bool,
    ) -> list[str]:
        """Kembalikan daftar nama tool RESMI yang relevan sebagai
        referensi teknisi, berdasarkan brand dan mode koneksi device.
        Tidak pernah mengembalikan nama tool unlock/bypass FRP.
        """
        tools = list(self._BRAND_TOOLS.get(brand_group, ()))

        for default_tool in self._DEFAULT_TOOLS:
            if default_tool not in tools:
                tools.append(default_tool)

        if not fastboot_connected and device_mode != "No connection":
            tools.append("Reboot ke Fastboot/Download Mode (tombol volume + power)")

        if not authorized and device_mode == "ADB Unauthorized":
            tools.append("Aktifkan & otorisasi USB Debugging di device")

        return tools
