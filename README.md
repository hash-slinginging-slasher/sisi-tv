# ngc-cams

ONVIF Camera Manager is a personal Windows app for discovering ONVIF cameras, resolving RTSP URLs, viewing live streams, controlling PTZ, and recording segments with optional audio. The UI is a local FastAPI + HTMX web app on `127.0.0.1:8000` driven by `ngc-cams-web`.

The product scope is captured in `odm-replacement-prd_1.md`. The implementation pivot from Qt to a web UI is recorded in `kanban-to.md` and `docs/plans/2026-05-17-web-pivot.md`.

## Development

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
ngc-cams-web              # launch on 127.0.0.1:8000, opens browser
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
