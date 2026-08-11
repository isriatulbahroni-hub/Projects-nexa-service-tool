"""CLI buat generate license key Nexa Service Tool.

Ini tool buat PENJUAL (kamu), bukan bagian dari aplikasi yang dijual ke
pembeli. Jalankan lewat command line, bukan dari dalam app.py.

PENTING: pastikan NEXA_LICENSE_SECRET (env var) di sini SAMA PERSIS
dengan yang dipakai di build .exe yang kamu distribusikan ke pembeli -
kalau beda, key yang di-generate di sini tidak akan valid di aplikasi
mereka.

Contoh pakai:
    python tools/generate_license.py "Toko HP Jaya" --days 365
    python tools/generate_license.py "Budi Santoso" --lifetime
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.licensing import generate_license_key, validate_license_key  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate license key Nexa Service Tool.")
    parser.add_argument("licensee", help="Nama pembeli/toko yang tercantum di license key.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--days", type=int, help="Masa berlaku dalam hari dari sekarang.")
    group.add_argument("--lifetime", action="store_true", help="Lisensi seumur hidup (tidak expired).")

    args = parser.parse_args()

    if args.lifetime or args.days is None:
        expires_at = 0
    else:
        expires_at = int(time.time()) + (args.days * 86400)

    key = generate_license_key(args.licensee, expires_at=expires_at)

    # Validasi ulang sebelum ditampilkan, jaga-jaga kalau ada masalah env var.
    info = validate_license_key(key)

    print("License key berhasil dibuat:")
    print(f"  Licensee   : {info['licensee']}")
    if info["expires_at"] == 0:
        print("  Masa berlaku: Seumur hidup")
    else:
        expiry_str = time.strftime("%Y-%m-%d", time.localtime(info["expires_at"]))
        print(f"  Masa berlaku: sampai {expiry_str}")
    print()
    print(key)

    return 0


if __name__ == "__main__":
    sys.exit(main())
