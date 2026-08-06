import logging

from core.app_logging import LOG_FILE, get_logger
from core.settings import SettingsStore


def test_settings_store_round_trip(tmp_path):
    path = tmp_path / "settings.json"
    store = SettingsStore(path=path, defaults={"enabled": True})
    assert store.get("enabled") is True

    store.set("enabled", False)
    reloaded = SettingsStore(path=path, defaults={"enabled": True})
    assert reloaded.get("enabled") is False


def test_settings_store_recovers_from_invalid_json(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("not-json", encoding="utf-8")
    store = SettingsStore(path=path, defaults={"enabled": True})
    assert store.get("enabled") is True


def test_logger_is_configured_and_idempotent():
    logger = get_logger("test")
    assert logger.level == logging.INFO
    assert LOG_FILE.parent.exists()
    assert any(handler for handler in logger.handlers)
