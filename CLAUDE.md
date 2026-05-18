# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

SISI-TV is a single-user Windows app for ONVIF discovery, RTSP live view, PTZ, and continuous recording (formerly `ngc-cams` — Python packages are still named `ngc_cams` / `ngc_cams_web` internally; user-facing rename only). The authoritative scope and rationale lives in `odm-replacement-prd_1.md` — consult it before adding features or pushing back on requirements. `AGENTS.md` carries the repository conventions and is binding.

## Commands

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
sisi-tv                   # launch the web app on 127.0.0.1:8000
pytest                    # run the whole suite
pytest tests/test_db.py::test_initialize_creates_core_tables   # single test
ruff check .              # lint (configured in pyproject.toml, line-length 100)
```

If a globally installed pytest plugin breaks collection, disable autoload:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'; python -m pytest
```

Packaging target (not yet committed): `pyinstaller sisi-tv.spec` produces the portable `.exe`.

## Architecture

The package lives under `src/ngc_cams/` with the layout enforced by `AGENTS.md`. Each subpackage owns one concern and should not reach into another's internals:

- `ngc_cams_web` — FastAPI + HTMX web UI served on `127.0.0.1:8000`. Composition root in `composition.py` builds a `FastAPI` instance with every collaborator (`CameraRepository`, `DiscoveryService`, `RecordingManager`) attached to `app.state`. Routes split across `routes/cameras.py` (CRUD + detail), `routes/discovery.py`, and `routes/live.py` (MJPEG live view). `__main__.py` wires real collaborators, registers a poll lifespan that calls `RecordingManager.poll()` every second, and runs uvicorn. Templates in `templates/` (`base.html`, `index.html`, `camera_detail.html`, `_discovered.html`).
- `ngc_cams.onvif` — `discovery.py` (WS-Discovery → `DiscoveredCamera` with manufacturer pulled from ONVIF scope URIs) and `streams.py` (`get_stream_uris` calls `GetStreamUri` and returns up to a main + sub URI). The `wsdiscovery_class` / lazy `onvif.ONVIFCamera` imports exist so tests can inject fakes — preserve that seam.
- `ngc_cams.recording` — `ffmpeg.py` (`build_segment_command`: `-c copy`, TCP RTSP, segment muxer, audio toggled by `RecordMode`) and `paths.py` (`safe_camera_dir_name`, `segment_output_pattern` writing to `<root>/<camera>/<date>/%Y-%m-%d_%H-%M-%S.mp4`). All ffmpeg argv construction must stay centralized in `build_segment_command` so reconnect, audio, and segment options stay testable in one place.
- `ngc_cams.db` — schema bootstrap (`cameras`, `recording_segments` with `ON DELETE CASCADE`, `record_mode` CHECK constraint) and `connect()` which enables `PRAGMA foreign_keys = ON` and sets `Row` factory.
- `ngc_cams.cameras` — `CameraRepository` is the only path to the `cameras` table; UI / services should depend on it, not raw SQL.
- `ngc_cams.models` — `Camera` / `StoredCamera` dataclasses (frozen) and the `RecordMode` `StrEnum` (`off` / `video_only` / `video_audio`) whose values match the DB CHECK constraint. Adding a mode requires updating both.
- `ngc_cams.config` — `AppConfig` defaults including `recording_root=Z:\SISI-TV-storage\<COMPUTERNAME>`, `snapshot_root=Z:\SISI-TV-storage\<COMPUTERNAME>\snapshots`, `db_path=Z:\SISI-TV-storage\<COMPUTERNAME>\ngc-cams.sqlite3`, 600 s segments, 7-day retention. The per-host subdir comes from `_hostname()` (Windows `COMPUTERNAME` env var, falling back to `socket.gethostname()`) so multiple PCs sharing one NAS at `Z:\SISI-TV-storage` never overwrite each other. Keep these paths configurable; do not hardcode them elsewhere. User overrides live at `~/.ngc-cams/settings.json` via `AppConfig.from_settings()`.

`tests/` mirrors `src/` and currently exercises DB schema/repo, ffmpeg command construction, recording paths, discovery (with an injected fake `wsdiscovery_class`), and the FastAPI routes via `TestClient` with fakes attached to `app.state`. When extending discovery, ONVIF, ffmpeg, or web routes, follow the same pattern: mock the network / subprocess boundary rather than the real device.

## Conventions

- Python 3.11+, 4-space indent, type hints on public functions, `from __future__ import annotations` is used throughout — keep it.
- `snake_case` modules/functions/variables, `PascalCase` Qt classes, `UPPER_SNAKE_CASE` constants. Vocabulary tracks the PRD: discovery, RTSP URL, PTZ, grid view, segments, retention.
- All text files are UTF-8. On PowerShell read Markdown with `Get-Content -Encoding UTF8 <file>`.
- Never commit camera passwords, RTSP URLs containing credentials, SQLite databases, recordings, snapshots, or generated `.exe` files (also see `.gitignore`).
