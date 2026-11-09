import pytest

from core import packages
from core.adb import ADBError


@pytest.fixture
def calls(monkeypatch):
    seen = []
    monkeypatch.setattr(packages, "run_adb", lambda *a, **k: seen.append(a) or "ok")
    return seen


def test_disable_app_runs_pm_disable_user(calls):
    packages.disable_app("S", "com.whatsapp")
    assert calls == [("-s", "S", "shell", "pm", "disable-user", "--user", "0", "com.whatsapp")]


@pytest.mark.parametrize("pkg", ["com.android.systemui", "android", "com.google.android.gms",
                                 "com.android.providers.contacts", "com.android.settings"])
def test_disable_blocks_system_critical_packages(calls, pkg):
    with pytest.raises(ADBError):
        packages.disable_app("S", pkg)
    assert calls == []


@pytest.mark.parametrize("pkg", ["", "bukan paket", "com.x; reboot", "../../etc", "com"])
def test_disable_and_enable_reject_invalid_names(calls, pkg):
    with pytest.raises(ADBError):
        packages.disable_app("S", pkg)
    with pytest.raises(ADBError):
        packages.enable_app("S", pkg)
    assert calls == []


def test_enable_app_allows_previously_protected_names(calls):
    # Mengaktifkan lagi harus selalu boleh, termasuk paket yang tidak boleh dimatikan.
    packages.enable_app("S", "com.android.systemui")
    assert calls == [("-s", "S", "shell", "pm", "enable", "com.android.systemui")]
