# Repository Guidelines

## Project Structure & Module Organization

This repository currently contains the product requirements document `odm-replacement-prd_1.md` for the `ngc-cams` ONVIF camera manager. Keep planning documents at the repository root until implementation begins.

When code is added, use this Python application layout:

- `src/ngc_cams/` for application code.
- `src/ngc_cams/ui/` for PyQt6 windows, widgets, and view models.
- `src/ngc_cams/onvif/` for discovery, probing, PTZ, and RTSP URL resolution.
- `src/ngc_cams/recording/` for ffmpeg process management, retention, and playback.
- `tests/` for automated tests mirroring the `src/` package structure.
- `assets/` for icons, UI resources, and packaging assets.

## Build, Test, and Development Commands

No build system is committed yet. Once implementation starts, prefer these commands and document changes in `README.md`:

- `python -m venv .venv` creates the local virtual environment.
- `.venv\Scripts\Activate.ps1` activates it on Windows PowerShell.
- `pip install -e ".[dev]"` installs the package and development dependencies.
- `pytest` runs the test suite.
- `python -m ngc_cams` starts the desktop app.
- `pyinstaller ngc-cams.spec` builds the portable Windows executable.

## Coding Style & Naming Conventions

Target Python 3.11+. Use 4-space indentation, type hints for public functions, and small modules with focused responsibilities. Use `snake_case` for functions, modules, and variables; `PascalCase` for PyQt classes; and `UPPER_SNAKE_CASE` for constants. Keep terminology consistent with the PRD: discovery, RTSP URL, PTZ, grid view, segments, retention.

Keep ffmpeg command construction centralized so reconnect, audio, and segment options remain testable.

## Testing Guidelines

Use `pytest` when tests are introduced. Name files `test_<module>.py` and test functions `test_<behavior>()`. Mock network cameras, ONVIF services, VLC, and ffmpeg subprocesses by default. Cover SQLite schema changes, RTSP URL fallbacks, recording command generation, retention cleanup, and PTZ behavior.

## Commit & Pull Request Guidelines

This directory is not currently a Git repository, so no local commit history is available. Use concise imperative commit messages such as `Add camera discovery service` or `Fix recording retention cleanup`.

Pull requests should include a short summary, test results, linked issue or requirement, and screenshots for UI changes. For camera, recording, or packaging changes, include the Windows version and camera models used for validation.

## Security & Configuration Tips

Do not commit camera passwords, RTSP URLs containing credentials, SQLite databases, recordings, snapshots, or generated `.exe` files. Keep storage paths configurable; the PRD defaults to `D:\ngc-cams-recordings\` and `D:\ngc-cams-snapshots\`.
