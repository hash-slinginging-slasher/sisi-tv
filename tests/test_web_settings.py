from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ngc_cams import settings_store
from ngc_cams.cameras import CameraRepository
from ngc_cams.config import AppConfig
from ngc_cams.db import initialize
from ngc_cams_web.composition import build_app


@pytest.fixture()
def isolated_settings(tmp_path, monkeypatch):
    """Redirect ngc_cams.settings_store.default_settings_path() to a tmp file
    so the test never reads/writes the real ~/.ngc-cams/settings.json."""
    target = tmp_path / "settings.json"
    monkeypatch.setattr(settings_store, "default_settings_path", lambda: target)
    return target


def _build(config: AppConfig | None = None):
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    connection.row_factory = sqlite3.Row
    initialize(connection)
    repo = CameraRepository(connection)
    app = build_app(
        cameras=repo,
        discovery=None,
        recording_manager=None,
        config=config or AppConfig(),
    )
    return app


def test_get_settings_shows_current_config_values(isolated_settings):
    config = AppConfig(
        recording_root=Path(r"E:\here"),
        segment_seconds=900,
    )
    app = _build(config)
    with TestClient(app) as client:
        response = client.get("/settings")
    assert response.status_code == 200
    assert "E:\\here" in response.text or "E:/here" in response.text
    assert "900" in response.text


def test_post_settings_persists_to_json(isolated_settings):
    app = _build()
    with TestClient(app) as client:
        response = client.post(
            "/settings",
            data={
                "recording_root": r"E:\custom",
                "snapshot_root": r"E:\snaps",
                "segment_seconds": "1200",
                "disk_guard_free_gb": "25",
            },
            follow_redirects=False,
        )
    assert response.status_code == 303
    assert response.headers["location"] == "/settings?saved=1"
    data = json.loads(isolated_settings.read_text(encoding="utf-8"))
    assert data == {
        "recording_root": r"E:\custom",
        "snapshot_root": r"E:\snaps",
        "segment_seconds": 1200,
        "disk_guard_free_gb": 25,
    }


def test_post_settings_skips_blank_fields_and_keeps_prior_values(isolated_settings):
    # Pre-existing settings.
    settings_store.save({"recording_root": r"E:\old", "segment_seconds": 600})
    app = _build()
    with TestClient(app) as client:
        client.post(
            "/settings",
            data={
                "recording_root": "",  # blank — should NOT clobber
                "segment_seconds": "1200",  # new value
            },
            follow_redirects=False,
        )
    data = json.loads(isolated_settings.read_text(encoding="utf-8"))
    assert data["recording_root"] == r"E:\old"  # preserved
    assert data["segment_seconds"] == 1200  # updated


def test_post_settings_ignores_invalid_integers(isolated_settings):
    settings_store.save({"segment_seconds": 600})
    app = _build()
    with TestClient(app) as client:
        client.post(
            "/settings",
            data={"segment_seconds": "not-a-number"},
            follow_redirects=False,
        )
    data = json.loads(isolated_settings.read_text(encoding="utf-8"))
    assert data["segment_seconds"] == 600  # untouched


def test_settings_saved_banner_appears_after_redirect(isolated_settings):
    app = _build()
    with TestClient(app) as client:
        response = client.get("/settings?saved=1")
    assert response.status_code == 200
    assert "Restart" in response.text


def test_settings_page_shows_storage_path(isolated_settings):
    app = _build()
    with TestClient(app) as client:
        response = client.get("/settings")
    assert str(isolated_settings) in response.text
