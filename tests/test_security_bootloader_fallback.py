from core import security_check


def _fake_getprop(values):
    def fake(serial, prop):
        return values.get(prop, "Unknown")
    return fake


def _run(monkeypatch, props):
    monkeypatch.setattr(security_check, "_getprop", _fake_getprop(props))
    monkeypatch.setattr(security_check, "_check_root", lambda serial: (False, ""))
    monkeypatch.setattr(security_check, "run_adb", lambda *a, **k: "Enforcing")
    return security_check.run_security_check("S")


def test_flash_locked_prop_is_used_first(monkeypatch):
    r = _run(monkeypatch, {"ro.boot.flash.locked": "1", "ro.boot.verifiedbootstate": "green"})
    assert r.bootloader_state == "Locked"


def test_falls_back_to_vbmeta_device_state(monkeypatch):
    r = _run(monkeypatch, {"ro.boot.vbmeta.device_state": "locked", "ro.boot.verifiedbootstate": "green"})
    assert r.bootloader_state == "Locked"


def test_orange_verified_boot_means_unlocked(monkeypatch):
    r = _run(monkeypatch, {"ro.boot.verifiedbootstate": "orange"})
    assert r.bootloader_state == "Unlocked"


def test_stays_unknown_when_nothing_is_readable(monkeypatch):
    r = _run(monkeypatch, {})
    assert r.bootloader_state == "Unknown"
