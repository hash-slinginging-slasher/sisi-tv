from __future__ import annotations

from pathlib import Path

from ngc_cams import settings_store
from ngc_cams.config import AppConfig


def test_load_returns_empty_dict_when_file_missing(tmp_path):
    target = tmp_path / "does-not-exist.json"
    assert settings_store.load(target) == {}


def test_load_returns_empty_dict_when_file_invalid_json(tmp_path):
    target = tmp_path / "settings.json"
    target.write_text("not-valid-json{", encoding="utf-8")
    assert settings_store.load(target) == {}


def test_load_returns_empty_dict_when_file_is_not_a_dict(tmp_path):
    target = tmp_path / "settings.json"
    target.write_text('["array", "not", "object"]', encoding="utf-8")
    assert settings_store.load(target) == {}


def test_save_then_load_round_trips(tmp_path):
    target = tmp_path / "nested" / "settings.json"
    payload = {"recording_root": r"E:\different", "segment_seconds": 1200}
    settings_store.save(payload, target)
    assert target.exists()
    assert settings_store.load(target) == payload


def test_save_preserves_unknown_keys(tmp_path):
    target = tmp_path / "settings.json"
    settings_store.save({"future_key": 42, "recording_root": "/a"}, target)
    assert settings_store.load(target)["future_key"] == 42


def test_app_config_from_settings_overrides_defaults(tmp_path):
    config = AppConfig.from_settings(
        {
            "recording_root": r"E:\custom",
            "snapshot_root": r"E:\snaps",
            "segment_seconds": 1200,
            "disk_guard_free_gb": 25,
        }
    )
    assert config.recording_root == Path(r"E:\custom")
    assert config.snapshot_root == Path(r"E:\snaps")
    assert config.segment_seconds == 1200
    assert config.disk_guard_free_gb == 25


def test_app_config_from_settings_ignores_unknown_keys():
    config = AppConfig.from_settings({"recording_root": "/a", "unknown_key": "x"})
    assert config.recording_root == Path("/a")
    assert not hasattr(config, "unknown_key")


def test_app_config_from_settings_falls_back_on_bad_values():
    default = AppConfig()
    config = AppConfig.from_settings({"segment_seconds": "not-a-number"})
    assert config.segment_seconds == default.segment_seconds


def test_app_config_from_settings_with_empty_dict_returns_defaults():
    assert AppConfig.from_settings({}) == AppConfig()
