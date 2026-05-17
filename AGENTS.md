# Repository Guidelines

## Project Structure & Module Organization

This repository hosts SISI-TV (formerly `ngc-cams`), a single-user ONVIF camera manager. Python packages remain `ngc_cams` / `ngc_cams_web` internally; the rename is user-facing only. Product scope lives in `odm-replacement-prd_1.md`.

Python application layout:

- `src/ngc_cams/` for shared application code (models, config, db, cameras repo, segments repo, ONVIF, recording).
- `src/ngc_cams/onvif/` for discovery, probing, PTZ, and RTSP URL resolution.
- `src/ngc_cams/recording/` for ffmpeg process management, retention, and playback.
- `src/ngc_cams_web/` for the FastAPI + HTMX web UI (composition root, routes, templates, live MJPEG helpers).
- `tests/` for automated tests mirroring both packages.
- `assets/` for icons, UI resources, and packaging assets.

## Build, Test, and Development Commands

No build system is committed yet. Once implementation starts, prefer these commands and document changes in `README.md`:

- `python -m venv .venv` creates the local virtual environment.
- `.venv\Scripts\Activate.ps1` activates it on Windows PowerShell.
- `pip install -e ".[dev]"` installs the package and development dependencies.
- `pytest` runs the test suite.
- `sisi-tv` launches the FastAPI web UI on `127.0.0.1:8000` and opens the default browser.
- `pyinstaller sisi-tv.spec` builds the portable Windows executable (not yet committed).

## Coding Style & Naming Conventions

Target Python 3.11+. Use 4-space indentation, type hints for public functions, and small modules with focused responsibilities. Use `snake_case` for functions, modules, and variables; `PascalCase` for classes; and `UPPER_SNAKE_CASE` for constants. Keep terminology consistent with the PRD: discovery, RTSP URL, PTZ, segments, retention.

Keep ffmpeg command construction centralized so reconnect, audio, and segment options remain testable.

## Testing Guidelines

Use `pytest`. Name files `test_<module>.py` and test functions `test_<behavior>()`. Mock network cameras, ONVIF services, and ffmpeg subprocesses by default. Test FastAPI routes via `fastapi.testclient.TestClient` with fakes injected on `app.state`. Cover SQLite schema changes, RTSP URL fallbacks, recording command generation, retention cleanup, and PTZ behavior.

## Commit & Pull Request Guidelines

Use concise imperative commit messages such as `Add camera discovery service` or `Fix recording retention cleanup`.

Pull requests should include a short summary, test results, linked issue or requirement, and screenshots for UI changes. For camera, recording, or packaging changes, include the Windows version and camera models used for validation.

## Security & Configuration Tips

Do not commit camera passwords, RTSP URLs containing credentials, SQLite databases, recordings, snapshots, or generated `.exe` files. Keep storage paths configurable; the app defaults to `C:\sisi-tv-storage\` (recordings) and `C:\sisi-tv-storage\snapshots\`. Users can override via the Settings page (writes `~/.ngc-cams/settings.json`).
