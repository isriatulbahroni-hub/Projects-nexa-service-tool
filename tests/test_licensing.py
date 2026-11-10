"""Tes lisensi Ed25519 dan login teknisi (core/licensing.py)."""
import time

import pytest

from core import licensing


@pytest.fixture()
def keys(monkeypatch, tmp_path):
    private_b64, public_b64 = licensing.generate_keypair()
    monkeypatch.setattr(licensing, "LICENSE_PUBLIC_KEY_B64", public_b64)
    monkeypatch.delenv("NEXA_LICENSE_PUBLIC_KEY", raising=False)
    monkeypatch.setattr(licensing, "DATA_DIR", tmp_path)
    monkeypatch.setattr(licensing, "AUTH_FILE", tmp_path / "technicians.json")
    monkeypatch.setattr(licensing, "LICENSE_FILE", tmp_path / "license.json")
    return private_b64, public_b64


def test_valid_license_roundtrip(keys):
    private_b64, _ = keys
    key = licensing.generate_license_key("Konter Maju", 0, private_key_b64=private_b64)
    info = licensing.validate_license_key(key)
    assert info == {"licensee": "Konter Maju", "expires_at": 0}
    assert licensing.activate_license(key)["licensee"] == "Konter Maju"
    assert licensing.is_licensed() is True


def test_tampered_payload_is_rejected(keys):
    private_b64, _ = keys
    key = licensing.generate_license_key("Konter A", 0, private_key_b64=private_b64)
    _, payload_hex, sig = key.split("-", 2)
    forged_payload = "Konter B|0".encode().hex()
    with pytest.raises(licensing.LicenseError):
        licensing.validate_license_key(f"NEXA-{forged_payload}-{sig}")


def test_key_signed_by_other_private_key_is_rejected(keys):
    other_private, _ = licensing.generate_keypair()
    forged = licensing.generate_license_key("Bajakan", 0, private_key_b64=other_private)
    with pytest.raises(licensing.LicenseError):
        licensing.validate_license_key(forged)


def test_expired_license_is_rejected(keys):
    private_b64, _ = keys
    key = licensing.generate_license_key("Konter", int(time.time()) - 10, private_key_b64=private_b64)
    with pytest.raises(licensing.LicenseError, match="kedaluwarsa"):
        licensing.validate_license_key(key)


def test_everything_rejected_when_public_key_not_configured(monkeypatch, keys):
    private_b64, _ = keys
    key = licensing.generate_license_key("Konter", 0, private_key_b64=private_b64)
    monkeypatch.setattr(licensing, "LICENSE_PUBLIC_KEY_B64", "")
    with pytest.raises(licensing.LicenseError, match="belum dikonfigurasi"):
        licensing.validate_license_key(key)


@pytest.mark.parametrize("bad", ["", "NEXA", "NEXA-zz-zz", "NEXA-4142-00", "abc"])
def test_malformed_keys_raise_license_error(keys, bad):
    with pytest.raises(licensing.LicenseError):
        licensing.validate_license_key(bad)


def test_generate_requires_private_key(monkeypatch):
    monkeypatch.delenv("NEXA_LICENSE_PRIVATE_KEY", raising=False)
    with pytest.raises(licensing.LicenseError):
        licensing.generate_license_key("Konter")


def test_technician_register_login_and_validation(keys):
    licensing.register_technician("Budi", "rahasia1", "Budi S.")
    assert licensing.login("budi", "rahasia1").display_name == "Budi S."
    with pytest.raises(licensing.AuthError):
        licensing.login("budi", "salah")
    with pytest.raises(licensing.AuthError):
        licensing.register_technician("x", "rahasia1", "X", role="superuser")
    with pytest.raises(licensing.AuthError):
        licensing.register_technician("  ", "rahasia1", "Kosong")


def test_corrupt_technician_record_does_not_crash_login(keys, tmp_path):
    (tmp_path / "technicians.json").write_text('{"budi": {"display_name": "B"}}', encoding="utf-8")
    with pytest.raises(licensing.AuthError):
        licensing.login("budi", "apa-saja")
