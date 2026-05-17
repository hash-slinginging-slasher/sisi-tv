from __future__ import annotations

from pathlib import Path

from ngc_cams.config import AppConfig


def test_app_config_default_db_path_lives_under_recording_root():
    config = AppConfig()
    assert config.db_path == config.recording_root / "ngc-cams.sqlite3"


def test_app_config_db_path_overridable():
    config = AppConfig(db_path=Path("X:/elsewhere/db.sqlite3"))
    assert config.db_path == Path("X:/elsewhere/db.sqlite3")


def test_app_config_default_vlc_log_lives_under_recording_root():
    config = AppConfig()
    assert config.vlc_log_path == config.recording_root / "logs" / "vlc-stderr.log"


def test_app_config_vlc_log_path_overridable():
    config = AppConfig(vlc_log_path=Path("X:/elsewhere/vlc.log"))
    assert config.vlc_log_path == Path("X:/elsewhere/vlc.log")
