# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`ngc-cams` (ONVIF Camera Manager) is a single-user Windows desktop app for ONVIF discovery, RTSP live view, PTZ, and continuous recording. The authoritative scope and rationale lives in `odm-replacement-prd_1.md` — consult it before adding features or pushing back on requirements. `AGENTS.md` carries the repository conventions and is binding.

## Commands

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python -m ngc_cams        # launch the desktop app
pytest                    # run the whole suite
pytest tests/test_db.py::test_initialize_creates_core_tables   # single test
ruff check .              # lint (configured in pyproject.toml, line-length 100)
```

If a globally installed pytest plugin breaks collection, disable autoload:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'; python -m pytest
```

Packaging target (not yet committed): `pyinstaller ngc-cams.spec` produces the portable `.exe`.

## Architecture

The package lives under `src/ngc_cams/` with the layout enforced by `AGENTS.md`. Each subpackage owns one concern and should not reach into another's internals:

- `ngc_cams.app` — Qt bootstrap (`main()` constructs `QApplication`, shows `MainWindow`). The console entry point `ngc-cams` in `pyproject.toml` resolves to this.
- `ngc_cams.ui` — PyQt6 windows and widgets. Keep view models thin and free of ONVIF / ffmpeg imports.
- `ngc_cams.onvif` — `discovery.py` (WS-Discovery → `DiscoveredCamera` with manufacturer pulled from ONVIF scope URIs) and `streams.py` (`get_stream_uris` calls `GetStreamUri` and returns up to a main + sub URI). The `wsdiscovery_class` / lazy `onvif.ONVIFCamera` imports exist so tests can inject fakes — preserve that seam.
- `ngc_cams.recording` — `ffmpeg.py` (`build_segment_command`: `-c copy`, TCP RTSP, segment muxer, audio toggled by `RecordMode`) and `paths.py` (`safe_camera_dir_name`, `segment_output_pattern` writing to `<root>/<camera>/<date>/%Y-%m-%d_%H-%M-%S.mp4`). All ffmpeg argv construction must stay centralized in `build_segment_command` so reconnect, audio, and segment options stay testable in one place.
- `ngc_cams.db` — schema bootstrap (`cameras`, `recording_segments` with `ON DELETE CASCADE`, `record_mode` CHECK constraint) and `connect()` which enables `PRAGMA foreign_keys = ON` and sets `Row` factory.
- `ngc_cams.cameras` — `CameraRepository` is the only path to the `cameras` table; UI / services should depend on it, not raw SQL.
- `ngc_cams.models` — `Camera` / `StoredCamera` dataclasses (frozen) and the `RecordMode` `StrEnum` (`off` / `video_only` / `video_audio`) whose values match the DB CHECK constraint. Adding a mode requires updating both.
- `ngc_cams.config` — `AppConfig` defaults including `recording_root=D:\ngc-cams-recordings`, `snapshot_root=D:\ngc-cams-snapshots`, 600 s segments, 7-day retention. Keep these paths configurable; do not hardcode them elsewhere.

`tests/` mirrors `src/` and currently exercises DB schema/repo, ffmpeg command construction, recording paths, and discovery (with an injected fake `wsdiscovery_class`). When extending discovery, ONVIF, VLC, or ffmpeg code, follow the same pattern: mock the network / subprocess boundary rather than the real device.

## Conventions

- Python 3.11+, 4-space indent, type hints on public functions, `from __future__ import annotations` is used throughout — keep it.
- `snake_case` modules/functions/variables, `PascalCase` Qt classes, `UPPER_SNAKE_CASE` constants. Vocabulary tracks the PRD: discovery, RTSP URL, PTZ, grid view, segments, retention.
- All text files are UTF-8. On PowerShell read Markdown with `Get-Content -Encoding UTF8 <file>`.
- Never commit camera passwords, RTSP URLs containing credentials, SQLite databases, recordings, snapshots, or generated `.exe` files (also see `.gitignore`).
