# SISI-TV

SISI-TV is a personal Windows app for discovering ONVIF cameras, resolving RTSP URLs, viewing live streams, controlling PTZ, and recording segments with optional audio. The UI is a local FastAPI + HTMX web app on `127.0.0.1:8000` driven by `sisi-tv`.

The product scope is captured in `odm-replacement-prd_1.md`. The implementation pivot from Qt to a web UI is recorded in `kanban-to.md` and `docs/plans/2026-05-17-web-pivot.md`.

## Quick start (Windows)

```cmd
git clone https://github.com/hash-slinginging-slasher/sisi-tv.git
cd sisi-tv
install.bat
.venv\Scripts\sisi-tv.exe
```

`install.bat` checks for Python 3.11+, creates `.venv`, installs the Python deps, installs ffmpeg via winget if missing, and pre-creates the default storage dirs.

## Development

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
sisi-tv                   # launch on 127.0.0.1:8000, opens browser
pytest                    # run the whole suite
```

If a globally installed pytest plugin fails before collection, run tests with plugin autoload disabled:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'; python -m pytest
```

## Encoding

All repository text files should be UTF-8. In Windows PowerShell, read Markdown with:

```powershell
Get-Content -Encoding UTF8 odm-replacement-prd_1.md
```

## Notes

- The Python packages are still named `ngc_cams` and `ngc_cams_web` (internal — not visible to users). Recordings and saved settings live at the paths under the original `ngc-cams` names so existing data is preserved across the rename.
