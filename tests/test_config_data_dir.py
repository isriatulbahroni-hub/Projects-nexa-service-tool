"""Data pengguna harus keluar dari folder temp PyInstaller (--onefile)."""
import sys
from pathlib import Path

from core import config


def test_source_run_keeps_project_data_dir(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert config._app_data_root() == config.SOURCE_ROOT


def test_frozen_build_uses_permanent_user_data_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    root = config._app_data_root()
    assert root == Path(tmp_path) / "NexaServiceTool"
    assert config.SOURCE_ROOT not in root.parents and root != config.SOURCE_ROOT


def test_all_persistent_paths_live_under_data_dir():
    from core import database, service_cases, settings, parts, app_logging, db_backup, automation, licensing

    for path in (
        database.DB_PATH, service_cases.DB_PATH, settings.SETTINGS_PATH, parts.DB_PATH,
        app_logging.LOG_DIR, db_backup.APP_DB_PATH, db_backup.APP_SETTINGS_PATH,
        db_backup.DEFAULT_BACKUP_DIR, automation.MACROS_DIR, licensing.AUTH_FILE, licensing.LICENSE_FILE,
    ):
        assert config.DATA_DIR in Path(path).parents, path


def test_project_root_alias_follows_data_root_for_app_py():
    # app.py memakai PROJECT_ROOT / "data" / "case_photos"; harus ikut folder data pengguna.
    assert config.PROJECT_ROOT == config.APP_DATA_ROOT
    assert config.PROJECT_ROOT / "data" == config.DATA_DIR
