import time

import pytest

import core.licensing as licensing


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    """Redirect all licensing storage to a temp dir so tests never touch
    the real data/technicians.json or data/license.json on disk."""
    monkeypatch.setattr(licensing, "DATA_DIR", tmp_path)
    monkeypatch.setattr(licensing, "AUTH_FILE", tmp_path / "technicians.json")
    monkeypatch.setattr(licensing, "LICENSE_FILE", tmp_path / "license.json")
    monkeypatch.setattr(licensing, "LICENSE_SECRET", "test-secret-not-for-production")
    yield


# ---------------------------------------------------------------------------
# Technician registration / login
# ---------------------------------------------------------------------------

def test_register_and_login_roundtrip():
    licensing.register_technician("Budi", "rahasia123", "Budi Santoso", role="admin")

    tech = licensing.login("Budi", "rahasia123")

    assert tech.username == "Budi"
    assert tech.display_name == "Budi Santoso"
    assert tech.role == "admin"


def test_login_is_case_insensitive_on_username():
    licensing.register_technician("Budi", "rahasia123", "Budi Santoso")

    tech = licensing.login("BUDI", "rahasia123")

    assert tech.display_name == "Budi Santoso"


def test_login_wrong_password_raises():
    licensing.register_technician("Budi", "rahasia123", "Budi Santoso")

    with pytest.raises(licensing.AuthError):
        licensing.login("Budi", "salahpassword")


def test_login_unknown_user_raises():
    with pytest.raises(licensing.AuthError):
        licensing.login("tidak_ada", "apapun123")


def test_register_short_password_rejected():
    with pytest.raises(licensing.AuthError):
        licensing.register_technician("Budi", "123", "Budi Santoso")


def test_register_duplicate_username_rejected():
    licensing.register_technician("Budi", "rahasia123", "Budi Santoso")

    with pytest.raises(licensing.AuthError):
        licensing.register_technician("budi", "lainlagi123", "Budi Lain")


def test_has_any_technician_reflects_registration_state():
    assert licensing.has_any_technician() is False

    licensing.register_technician("Budi", "rahasia123", "Budi Santoso")

    assert licensing.has_any_technician() is True


def test_change_password_requires_correct_old_password():
    licensing.register_technician("Budi", "rahasia123", "Budi Santoso")

    with pytest.raises(licensing.AuthError):
        licensing.change_password("Budi", "salah", "barubaru123")

    # Old password still works after a failed change attempt.
    licensing.login("Budi", "rahasia123")


def test_change_password_succeeds_and_old_password_stops_working():
    licensing.register_technician("Budi", "rahasia123", "Budi Santoso")

    licensing.change_password("Budi", "rahasia123", "barubaru123")

    with pytest.raises(licensing.AuthError):
        licensing.login("Budi", "rahasia123")

    tech = licensing.login("Budi", "barubaru123")
    assert tech.username == "Budi"


def test_list_technicians_returns_all_registered():
    licensing.register_technician("budi", "rahasia123", "Budi Santoso", role="admin")
    licensing.register_technician("sari", "rahasia456", "Sari Dewi", role="technician")

    technicians = {t.username: t for t in licensing.list_technicians()}

    assert set(technicians) == {"budi", "sari"}
    assert technicians["budi"].role == "admin"
    assert technicians["sari"].role == "technician"


# ---------------------------------------------------------------------------
# License key generation / validation
# ---------------------------------------------------------------------------

def test_generate_and_validate_lifetime_key():
    key = licensing.generate_license_key("Toko HP Jaya", expires_at=0)

    info = licensing.validate_license_key(key)

    assert info["licensee"] == "Toko HP Jaya"
    assert info["expires_at"] == 0


def test_generate_and_validate_key_with_future_expiry():
    future = int(time.time()) + 3600
    key = licensing.generate_license_key("Toko HP Jaya", expires_at=future)

    info = licensing.validate_license_key(key)

    assert info["expires_at"] == future


def test_expired_key_rejected():
    past = int(time.time()) - 3600
    key = licensing.generate_license_key("Toko HP Jaya", expires_at=past)

    with pytest.raises(licensing.LicenseError):
        licensing.validate_license_key(key)


def test_tampered_key_signature_rejected():
    key = licensing.generate_license_key("Toko HP Jaya", expires_at=0)
    tampered = key[:-1] + ("0" if key[-1] != "0" else "1")

    with pytest.raises(licensing.LicenseError):
        licensing.validate_license_key(tampered)


def test_malformed_key_rejected():
    with pytest.raises(licensing.LicenseError):
        licensing.validate_license_key("BUKAN-KEY-VALID")


def test_key_generated_with_different_secret_rejected(monkeypatch):
    key = licensing.generate_license_key("Toko HP Jaya", expires_at=0)

    monkeypatch.setattr(licensing, "LICENSE_SECRET", "secret-yang-berbeda")

    with pytest.raises(licensing.LicenseError):
        licensing.validate_license_key(key)


# ---------------------------------------------------------------------------
# Activation / active license state
# ---------------------------------------------------------------------------

def test_is_licensed_false_before_activation():
    assert licensing.is_licensed() is False
    assert licensing.get_active_license() is None


def test_activate_license_persists_and_is_licensed_true():
    key = licensing.generate_license_key("Toko HP Jaya", expires_at=0)

    licensing.activate_license(key)

    assert licensing.is_licensed() is True
    active = licensing.get_active_license()
    assert active["licensee"] == "Toko HP Jaya"


def test_activate_invalid_key_raises_and_does_not_persist():
    with pytest.raises(licensing.LicenseError):
        licensing.activate_license("BUKAN-KEY-VALID")

    assert licensing.is_licensed() is False


def test_expired_active_license_reports_not_licensed():
    past = int(time.time()) - 3600
    key = licensing.generate_license_key("Toko HP Jaya", expires_at=past)

    # Bypass activate_license's own validation to simulate a key that
    # was valid at activation time but has since expired.
    licensing.DATA_DIR.mkdir(parents=True, exist_ok=True)
    import json
    licensing.LICENSE_FILE.write_text(
        json.dumps({"key": key, "licensee": "Toko HP Jaya", "expires_at": past}),
        encoding="utf-8",
    )

    assert licensing.is_licensed() is False
    assert licensing.get_active_license() is None
