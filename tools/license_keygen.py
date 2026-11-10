"""Alat sisi penjual untuk lisensi Nexa Service Tool (Ed25519).

  python tools/license_keygen.py init
      Buat pasangan kunci. Simpan PRIVATE KEY di tempat aman (password manager),
      JANGAN di repo. Tempel PUBLIC KEY ke core/licensing.py -> LICENSE_PUBLIC_KEY_B64.

  NEXA_LICENSE_PRIVATE_KEY=<private key> python tools/license_keygen.py issue "Nama Toko" --days 365
  NEXA_LICENSE_PRIVATE_KEY=<private key> python tools/license_keygen.py issue "Nama Toko"        (seumur hidup)
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import licensing  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="buat pasangan kunci baru")
    issue = sub.add_parser("issue", help="buat license key")
    issue.add_argument("licensee", help="nama pemilik lisensi")
    issue.add_argument("--days", type=int, default=0, help="masa berlaku (hari); 0 = seumur hidup")
    args = parser.parse_args()

    if args.cmd == "init":
        private_b64, public_b64 = licensing.generate_keypair()
        print("PRIVATE KEY (RAHASIA, simpan aman, jangan commit):")
        print(private_b64)
        print()
        print("PUBLIC KEY (tempel ke LICENSE_PUBLIC_KEY_B64 di core/licensing.py):")
        print(public_b64)
        return 0

    expires_at = int(time.time()) + args.days * 86400 if args.days > 0 else 0
    try:
        print(licensing.generate_license_key(args.licensee, expires_at))
    except licensing.LicenseError as exc:
        print(f"Gagal: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
