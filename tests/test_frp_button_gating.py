"""Regression test untuk bug: tombol 'Reboot ke Recovery'/'Reboot ke
Bootloader' sempat di-enable tanpa syarat (True) setelah operasi selesai
atau gagal, tanpa mengecek ulang owner_verification_required. Lihat
_on_frp_action_complete / _on_frp_action_error di app.py.

Test ini level source-code (bukan instantiate full QMainWindow, yang
butuh device ADB nyata untuk banyak state lain) - konsisten dengan pola
tests/test_app_structure.py di repo ini.
"""

from pathlib import Path

SOURCE = Path("app.py").read_text(encoding="utf-8")


def _handler_body(name: str) -> str:
    start = SOURCE.index(f"def {name}(")
    # Ambil sampai definisi method berikutnya.
    next_def = SOURCE.index("\n    def ", start + 1)
    return SOURCE[start:next_def]


def test_action_complete_does_not_unconditionally_enable_reboot_buttons():
    body = _handler_body("_on_frp_action_complete")
    assert "self.frp_recovery_button.setEnabled(True)" not in body
    assert "self.frp_bootloader_button.setEnabled(True)" not in body
    assert "_reboot_action_buttons_allowed" in body


def test_action_error_does_not_unconditionally_enable_reboot_buttons():
    body = _handler_body("_on_frp_action_error")
    assert "self.frp_recovery_button.setEnabled(True)" not in body
    assert "self.frp_bootloader_button.setEnabled(True)" not in body
    assert "_reboot_action_buttons_allowed" in body


def test_gating_helper_defaults_to_locked_when_no_verification_yet():
    body = _handler_body("_reboot_action_buttons_allowed")
    assert "self._last_frp_verification is not None" in body
    assert "owner_verification_required" in body


def test_refresh_frp_verification_gates_buttons_on_every_path():
    body = _handler_body("refresh_frp_verification")
    # Jalur sukses harus meng-gate berdasarkan hasil terbaru.
    assert "not result.owner_verification_required" in body
    # Jalur error (FRPVerificationError & Exception umum) harus mengunci
    # tombol, bukan membiarkan state sebelumnya.
    assert body.count("self.frp_recovery_button.setEnabled(False)") >= 2
    assert body.count("self.frp_bootloader_button.setEnabled(False)") >= 2
