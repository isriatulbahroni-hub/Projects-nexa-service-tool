"""
Licensing & technician auth module -- login teknisi + validasi lisensi
offline untuk Nexa Service Tool.

Pakai file JSON sendiri (data/technicians.json, data/license.json) supaya
TIDAK bentrok dengan database riwayat servis.

Standalone module, BELUM di-wire ke app.py.

Lisensi memakai tanda tangan ASIMETRIS (Ed25519):
- KUNCI PRIVAT hanya ada di sisi penjual (kamu). Dipakai membuat license key
  lewat `python tools/license_keygen.py issue ...`. JANGAN masukkan ke repo
  atau ke aplikasi yang dijual.
- KUNCI PUBLIK ditanam di aplikasi (LICENSE_PUBLIC_KEY_B64 atau env
  NEXA_LICENSE_PUBLIC_KEY). Aplikasi hanya bisa MEMVERIFIKASI, tidak bisa
  membuat key baru. Jadi membongkar aplikasi tidak membocorkan cara
  membuat key (beda dengan HMAC simetris, di mana secret ikut terdistribusi).
- Selama kunci publik belum diisi, semua license key DITOLAK (aman secara bawaan).

Setup sekali: `python tools/license_keygen.py init` -> simpan private key di
tempat aman (bukan di repo), tempel public key ke LICENSE_PUBLIC_KEY_B64.

Catatan: lisensi offline tetap bukan DRM anti-crack tingkat tinggi (orang
bisa mengubah kode untuk melewati pengecekan); ini mencegah pembuatan key palsu.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .config import DATA_DIR

AUTH_FILE = DATA_DIR / "technicians.json"
LICENSE_FILE = DATA_DIR / "license.json"

# Kunci publik Ed25519 (base64, 32 byte). Kosong = belum dikonfigurasi.
LICENSE_PUBLIC_KEY_B64 = ""

PBKDF2_ITERATIONS = 200_000
VALID_ROLES = ("technician", "admin")


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
        salt = bytes.fromhex(salt_hex)
    except (ValueError, AttributeError):
        return False

    expected = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return hmac.compare_digest(expected.hex(), digest_hex)


# ---------------------------------------------------------------------------
# Technician management
# ---------------------------------------------------------------------------

def _load_technicians() -> dict:
    if not AUTH_FILE.exists():
        return {}
    try:
        data = json.loads(AUTH_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AuthError(
            f"File akun teknisi rusak atau tidak terbaca ({AUTH_FILE}). "
            "Pulihkan dari backup; jangan dihapus supaya akun lama tidak hilang."
        ) from exc
    return data if isinstance(data, dict) else {}


def _save_technicians(data: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = AUTH_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(AUTH_FILE)


def register_technician(username: str, password: str, display_name: str, role: str = "technician") -> Technician:
    if len(password) < 6:
        raise AuthError("Password minimal 6 karakter.")
    if role not in VALID_ROLES:
        raise AuthError(f"Peran tidak valid: {role!r}. Pilih salah satu dari {VALID_ROLES}.")

    data = _load_technicians()
    key = username.strip().lower()
    if not key:
        raise AuthError("Username tidak boleh kosong.")

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

    if (
        not isinstance(record, dict)
        or not _verify_password(password, record.get("password_hash", ""))
    ):
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
# Offline license key (Ed25519)
#
# Format key: NEXA-<payload dalam hex>-<tanda tangan Ed25519 dalam hex>
# Payload berisi: "nama_pemilik_lisensi|expires_at_unix" (expires_at 0 = lifetime)
# ---------------------------------------------------------------------------

def _ed25519():
    try:
        from cryptography.hazmat.primitives.asymmetric import ed25519
        from cryptography.exceptions import InvalidSignature
    except ImportError as exc:  # pragma: no cover - dependensi wajib
        raise LicenseError(
            "Library 'cryptography' belum terpasang. Jalankan: pip install cryptography"
        ) from exc
    return ed25519, InvalidSignature


def generate_keypair() -> tuple[str, str]:
    """Buat pasangan kunci baru. Return (private_key_b64, public_key_b64)."""
    from cryptography.hazmat.primitives import serialization
    ed25519, _ = _ed25519()

    private = ed25519.Ed25519PrivateKey.generate()
    private_raw = private.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    public_raw = private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return (
        base64.b64encode(private_raw).decode("ascii"),
        base64.b64encode(public_raw).decode("ascii"),
    )


def _public_key_b64() -> str:
    return (os.environ.get("NEXA_LICENSE_PUBLIC_KEY") or LICENSE_PUBLIC_KEY_B64).strip()


def generate_license_key(licensee: str, expires_at: int = 0, private_key_b64: Optional[str] = None) -> str:
    """Buat license key baru. HANYA dipanggil di sisi penjual, memakai kunci
    privat (argumen atau env NEXA_LICENSE_PRIVATE_KEY)."""
    ed25519, _ = _ed25519()
    private_b64 = (private_key_b64 or os.environ.get("NEXA_LICENSE_PRIVATE_KEY") or "").strip()
    if not private_b64:
        raise LicenseError("Kunci privat lisensi tidak diberikan (NEXA_LICENSE_PRIVATE_KEY).")
    if "|" in licensee:
        raise LicenseError("Nama pemilik lisensi tidak boleh mengandung karakter '|'.")

    try:
        private = ed25519.Ed25519PrivateKey.from_private_bytes(base64.b64decode(private_b64))
    except (ValueError, TypeError) as exc:
        raise LicenseError("Kunci privat lisensi tidak valid.") from exc

    payload = f"{licensee}|{int(expires_at)}".encode("utf-8")
    signature = private.sign(payload)
    return f"NEXA-{payload.hex()}-{signature.hex()}"


def validate_license_key(key: str) -> dict:
    """Validasi format & tanda tangan license key dengan kunci publik.
    Raise LicenseError kalau kunci publik belum diisi, format salah,
    tanda tangan tidak cocok, atau expired."""
    ed25519, InvalidSignature = _ed25519()

    public_b64 = _public_key_b64()
    if not public_b64:
        raise LicenseError("Kunci publik lisensi belum dikonfigurasi di aplikasi ini.")

    try:
        _, payload_hex, signature_hex = key.strip().split("-", 2)
        payload = bytes.fromhex(payload_hex)
        signature = bytes.fromhex(signature_hex)
        licensee, expires_str = payload.decode("utf-8").split("|", 1)
        expires_at = int(expires_str)
    except (ValueError, IndexError, AttributeError):
        raise LicenseError("Format license key tidak valid.")

    try:
        public = ed25519.Ed25519PublicKey.from_public_bytes(base64.b64decode(public_b64))
        public.verify(signature, payload)
    except InvalidSignature:
        raise LicenseError("License key tidak valid (tanda tangan tidak cocok).")
    except (ValueError, TypeError) as exc:
        raise LicenseError("Kunci publik lisensi di aplikasi tidak valid.") from exc

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

    try:
        data = json.loads(LICENSE_FILE.read_text(encoding="utf-8"))
        validate_license_key(data["key"])
    except (OSError, json.JSONDecodeError, KeyError, TypeError, LicenseError):
        return None

    return data


def is_licensed() -> bool:
    return get_active_license() is not None
