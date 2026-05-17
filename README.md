# ngc-cams

ONVIF Camera Manager is a personal Windows desktop app for discovering ONVIF cameras, resolving RTSP URLs, viewing live streams, controlling PTZ, and recording segments with optional audio.

The product scope is captured in `odm-replacement-prd_1.md`.

## Development

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python -m ngc_cams
pytest
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
