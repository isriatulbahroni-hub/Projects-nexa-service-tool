"""
Licensing & technician auth module -- login teknisi + validasi lisensi
offline untuk Nexa Service Tool.

Pakai file JSON sendiri (data/technicians.json, data/license.json) supaya
TIDAK bentrok dengan database riwayat servis yang sedang dibuat di sesi lain.

Standalone module, BELUM di-wire ke app.py (sengaja, biar tidak bentrok
dengan sesi lain yang sedang merombak app.py).

PENTING sebelum dipakai produksi:
- Ganti NEXA_LICENSE_SECRET (env var) dengan secret milikmu sendiri, JANGAN
  commit secret asli ke repo public.
- Sistem lisensi ini offline & berbasis HMAC signature -- cukup kuat untuk
  mencegah orang asal generate key, tapi bukan DRM anti-crack tingkat tinggi.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
AUTH_FILE = DATA_DIR / "technicians.json"
LICENSE_FILE = DATA_DIR / "license.json"

LICENSE_SECRET = os.environ.get(
    "NEXA_LICENSE_SECRET",
    "nexa-service-tool-default-secret-CHANGE-ME",
)

PBKDF2_ITERATIONS = 200_000


class AuthError(RuntimeError):
    pass


class LicenseError(RuntimeError):
    pass


@dataclass
class Technician:
    username: str
    display_name: str
    role: str = "technician"   # "technician" | "admin"


# ---------------------------------------------------------------------------
# Password hashing (stdlib only -- pbkdf2_hmac, tidak butuh dependency luar)
# ---------------------------------------------------------------------------

def _hash_password(password: str, salt: Optional[bytes] = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"{salt.hex()}${digest.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$", 1)
    except ValueError:
        return False

    salt = bytes.fromhex(salt_hex)
    expected = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return hmac.compare_digest(expected.hex(), digest_hex)


# ---------------------------------------------------------------------------
# Technician management
# ---------------------------------------------------------------------------

def _load_technicians() -> dict:
    if not AUTH_FILE.exists():
        return {}
    return json.loads(AUTH_FILE.read_text(encoding="utf-8"))


def _save_technicians(data: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    AUTH_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def register_technician(username: str, password: str, display_name: str, role: str = "technician") -> Technician:
    if len(password) < 6:
        raise AuthError("Password minimal 6 karakter.")

    data = _load_technicians()
    key = username.strip().lower()

    if key in data:
        raise AuthError(f"Username '{username}' sudah terdaftar.")

    data[key] = {
        "password_hash": _hash_password(password),
        "display_name": display_name,
        "role": role,
        "created_at": time.time(),
    }
    _save_technicians(data)

    return Technician(username=username, display_name=display_name, role=role)


def login(username: str, password: str) -> Technician:
    data = _load_technicians()
    key = username.strip().lower()
    record = data.get(key)

    if not record or not _verify_password(password, record["password_hash"]):
        raise AuthError("Username atau password salah.")

    return Technician(
        username=username,
        display_name=record.get("display_name", username),
        role=record.get("role", "technician"),
    )


def has_any_technician() -> bool:
    """Berguna buat cek first-run: kalau belum ada teknisi, tampilkan halaman setup."""
    return len(_load_technicians()) > 0


def change_password(username: str, old_password: str, new_password: str) -> None:
    login(username, old_password)  # validasi password lama dulu

    if len(new_password) < 6:
        raise AuthError("Password baru minimal 6 karakter.")

    data = _load_technicians()
    key = username.strip().lower()
    data[key]["password_hash"] = _hash_password(new_password)
    _save_technicians(data)


def list_technicians() -> list[Technician]:
    data = _load_technicians()
    return [
        Technician(
            username=uname,
            display_name=rec.get("display_name", uname),
            role=rec.get("role", "technician"),
        )
        for uname, rec in data.items()
    ]


# ---------------------------------------------------------------------------
# Offline license key
#
# Format key: NEXA-<payload dalam hex>-<signature 12 hex char>
# Payload berisi: "nama_pemilik_lisensi|expires_at_unix" (expires_at 0 = lifetime)
# ---------------------------------------------------------------------------

def generate_license_key(licensee: str, expires_at: int = 0) -> str:
    """Generate license key baru (dipakai di sisi pembuat/penjual tool,
    bukan di sisi user biasa)."""
    payload = f"{licensee}|{expires_at}"
    signature = hmac.new(LICENSE_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()[:12]
    payload_hex = payload.encode("utf-8").hex()
    return f"NEXA-{payload_hex}-{signature}"


def validate_license_key(key: str) -> dict:
    """Validasi format & signature license key.
    Raise LicenseError kalau format salah, signature tidak cocok, atau expired."""
    try:
        _, payload_hex, signature = key.strip().split("-", 2)
        payload = bytes.fromhex(payload_hex).decode("utf-8")
        licensee, expires_str = payload.split("|", 1)
        expires_at = int(expires_str)
    except (ValueError, IndexError):
        raise LicenseError("Format license key tidak valid.")

    expected_sig = hmac.new(LICENSE_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()[:12]
    if not hmac.compare_digest(expected_sig, signature):
        raise LicenseError("License key tidak valid (signature tidak cocok).")

    if expires_at != 0 and time.time() > expires_at:
        raise LicenseError("License key sudah kedaluwarsa.")

    return {"licensee": licensee, "expires_at": expires_at}


def activate_license(key: str) -> dict:
    """Validasi lalu simpan license key ke local storage device ini."""
    info = validate_license_key(key)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LICENSE_FILE.write_text(
        json.dumps({"key": key, **info}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return info


def get_active_license() -> Optional[dict]:
    if not LICENSE_FILE.exists():
        return None

    data = json.loads(LICENSE_FILE.read_text(encoding="utf-8"))

    try:
        validate_license_key(data["key"])
    except LicenseError:
        return None

    return data


def is_licensed() -> bool:
    return get_active_license() is not None
