## 2026-05-18

### Settings: "Reset to defaults" button
**Files Changed:** `src/ngc_cams_web/routes/settings.py`, `src/ngc_cams_web/templates/settings.html`, `tests/test_web_settings.py`

- New `POST /settings/reset` endpoint pops every key in `EDITABLE_FIELD_NAMES` from `settings.json` and redirects to `/settings?reset=1`. Unknown keys (grid_order, grid_columns, feed_filter, future additions) are preserved so the user doesn't lose unrelated UI state. This is the one-click way to drop a stale `C:\sisi-tv-storage` override and let the new `Z:\SISI-TV-storage\<COMPUTERNAME>` default kick in across multiple PCs.
- Settings page renders an orange "Reset to defaults" button next to Save, in its own sibling `<form id="settings-reset">` associated via HTML5 `form="..."` attribute so it doesn't submit pending field edits along with the reset. Native `confirm()` dialog explains what's reset and what survives.
- After redirect, `?reset=1` shows a secondary-colored banner mirroring the existing saved banner: "Recording & Network overrides cleared. Restart sisi-tv so the computed defaults take effect."
- Added two integration tests: reset strips editables while preserving unknowns; banner text appears after the redirect. Smoke-test outside pytest confirmed end-to-end.

**Deployment:** Not deployed
**Test Results:** Out-of-pytest end-to-end run hit all assertions; `ruff` clean.

---

### Default storage to per-host subdir under Z:\SISI-TV-storage
**Files Changed:** `src/ngc_cams/config.py`, `install.bat`, `CLAUDE.md`, `AGENTS.md`, `README.md`

- Replaced `_DEFAULT_STORAGE_ROOT = C:\sisi-tv-storage` with `_default_storage_root()` returning `Z:\SISI-TV-storage\<COMPUTERNAME>`, so multiple SISI-TV PCs writing to the same NAS share at `Z:\SISI-TV-storage\` never overwrite each other's recordings, snapshots, or SQLite DB.
- Hostname pulled from Windows `COMPUTERNAME` env var, falling back to `socket.gethostname()`, with `/` and `\` stripped defensively so a malformed hostname can't escape the storage subtree.
- All three AppConfig fields (`recording_root`, `snapshot_root`, `db_path`) switched to `field(default_factory=...)` so each instantiation evaluates the current host (not the value frozen at class-definition time).
- `install.bat` step 5 now tries to create `Z:\SISI-TV-storage\%COMPUTERNAME%\snapshots`; if `Z:` isn't mounted at install time it prints a `[WARN]` and continues -- recordings will fail until NAS is mounted, but the install otherwise completes cleanly. Three docs (`CLAUDE.md`, `AGENTS.md`, `README.md`) updated to describe the new default.
- Existing per-PC `settings.json` overrides are unaffected; only new installs (no override) pick up the new default automatically.

**Deployment:** Not deployed
**Test Results:** `_hostname()` / `_default_storage_root()` smoke-tested on dev box (`JODEL-SERVER` → `Z:\SISI-TV-storage\JODEL-SERVER`). `tests/test_config.py` passes; `tests/test_settings_store.py` errors are pre-existing sandbox temp-dir perms, not related.

---

### Vendor all CDN dependencies for offline kiosk operation
**Files Changed:** `scripts/vendor_static.py` (new), `src/ngc_cams_web/static/tailwind.js` (new, 418KB), `src/ngc_cams_web/static/htmx.min.js` (new, 50KB), `src/ngc_cams_web/static/fonts/material-symbols.woff2` (new, 1.1MB), `src/ngc_cams_web/static/fonts/material-symbols.css` (new), `src/ngc_cams_web/templates/base.html`

- Root-caused the GMKtec viewer's "no CSS, mascot only" symptom to the page depending on four external CDNs (cdn.tailwindcss.com, unpkg.com/htmx, two Google Fonts families) — the kiosk LAN has no working internet to the public CDNs.
- Wrote `scripts/vendor_static.py` (uses stdlib `urllib`, no extra deps) to download Tailwind JIT + HTMX + the Material Symbols Outlined variable font + its CSS into `src/ngc_cams_web/static/`. Re-runnable to refresh versions.
- Updated `base.html` to reference only local `/static/...` paths. Intentionally did NOT vendor Inter / JetBrains Mono: the existing font-family rules fall back to `system-ui` / `ui-monospace` (Segoe UI / Consolas on Windows), which is visually equivalent and saves ~150KB.
- Verified: `/grid` HTML response now contains zero outgoing CDN URLs; all four vendored assets return HTTP 200 from the local FastAPI mount.

**Deployment:** Not deployed
**Test Results:** Manual server fetch of /grid + each static asset returned 200.

---

### Fix install.bat step 3b parser crash (parens-in-echo)
**Files Changed:** `install.bat`

- Step 3b's `if errorlevel 1 ( ... echo ... (it currently supports 3.7-3.13). ... ) else ( ... )` block parsed badly because the unescaped `(` inside the echo text closed the outer if-block at parse time, and the trailing `.` became a top-level token cmd couldn't parse -- "`. was unexpected at this time.`" right after the pywebview pip install finished. The whole shortcut step never ran.
- Same fix pattern as before: replaced the if/else block with `if errorlevel 1 goto :viewer_install_failed` + label, moving the multi-line WARN message to top level where parens in text are harmless.
- Verified with a sandbox test (`_test_step3b.bat`) running both the success and failure paths; no parser error.

**Deployment:** Not deployed
**Test Results:** Sandbox dry-run of both branches printed expected output.

---

### Fix install.bat parser error in Startup-stub generation
**Files Changed:** `install.bat`

- Previous revision used nested `if () ( ... > file )` blocks plus `start ""` (empty title). cmd's parser mis-tracks quotes through `""` inside a nested paren block, throwing `. was unexpected at this time.` *after* the pip install completes and *before* step 6 ever runs -- which is why the user's GMKtec install reported no errors visibly but never created the shortcuts.
- Rewrote step 6/7 to use `goto :label` flow instead of nested parens, single-line `> file echo ...` / `>> file echo ...` redirections instead of `( echo ... ) > file`, and `start "SISI-TV Viewer" /min` instead of `start ""` so the empty-title corner case is gone.
- Verified with an isolated sandbox test (`_test_startup.bat` redirected to `_test_startup_out\`) that both stubs are written with correct contents and no parser error.

**Deployment:** Not deployed
**Test Results:** Sandbox dry-run of step 6/7 produced both stubs cleanly.

---

### Drop PowerShell shortcut layer; write Startup .cmd stubs directly
**Files Changed:** `install.bat`, `scripts/create-startup-shortcut.ps1` (deleted), `scripts/create-viewer-startup-shortcut.ps1` (deleted)

- Replaced the two `powershell -File ...ps1` calls with cmd-only stub generation that writes `SISI-TV.cmd` and `SISI-TV Viewer.cmd` directly into `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\`. Removes one layer (PS execution policy, `[Environment]::GetFolderPath` quirks, .lnk via WScript.Shell COM) and gives a path you can read in the install log.
- Each step ends with an explicit `if exist "%STARTUP_X%"` check that prints `[ OK ]` or `[FAIL]` — no more guessing whether the shortcut was created.
- Final step prints `dir /b` of the Startup folder so the install output ends with proof of what's actually there.
- Cleans up any legacy `SISI-TV.lnk` / `SISI-TV Viewer.lnk` from earlier PS-based installs so re-running install.bat after the upgrade doesn't leave duplicate entries.

**Deployment:** Not deployed
**Test Results:** Not run.

---

### Make pywebview viewer an optional extra
**Files Changed:** `pyproject.toml`, `install.bat`

- Moved `pywebview` out of main `dependencies` into a new `[viewer]` optional extra. Reason: `pythonnet` (transitive dep) only ships wheels for Python 3.7–3.13, so installing on a Python 3.14 box (e.g. the GMKtec kiosk) failed the whole `pip install -e .[dev]` step and blocked the server from installing.
- `install.bat` now runs the viewer install as a separate step that is allowed to fail. A `VIEWER_INSTALLED` flag gates the kiosk Startup-shortcut creation, so on unsupported Python versions the server installs cleanly and the viewer is just skipped.
- Server runs identically on any supported Python; viewer-only users who upgrade Python to 3.13 can re-run install.bat to add the kiosk back.

**Deployment:** Not deployed
**Test Results:** Not run.

---

### Dedicated fullscreen kiosk viewer (`sisi-tv-viewer`)
**Files Changed:** `pyproject.toml`, `src/ngc_cams_viewer/__init__.py`, `src/ngc_cams_viewer/__main__.py`, `scripts/create-viewer-startup-shortcut.ps1`, `install.bat`

- New `ngc_cams_viewer` package wraps pywebview (Edge WebView2 on Windows) to open `/grid` in a frameless fullscreen window. Polls the server URL on startup so it survives a cold-boot race with the SISI-TV server shortcut.
- Exposed as a `gui-scripts` entry point (`sisi-tv-viewer`) so the resulting `.exe` is a no-console Windows GUI launcher — no console flash at login.
- Added `scripts/create-viewer-startup-shortcut.ps1` (drops `SISI-TV Viewer.lnk` into `shell:startup` pointing at `.venv\Scripts\sisi-tv-viewer.exe`), and wired `install.bat` to call it right after the existing server startup-shortcut step.
- Defaults the target URL to `http://<bind_host>:<bind_port>/grid` from `AppConfig` (remapping `0.0.0.0`/`::` to `127.0.0.1`); accepts a positional URL arg, `--no-wait`, `--windowed`, `--timeout`.

**Deployment:** Not deployed
**Test Results:** Manual smoke-test of `_default_url()` and `wait_for_server()` passed; `ruff check` clean. Full suite still hits the pre-existing `Temp\pytest-of-jodel` sandbox PermissionError (101 errors on clean `main` too) — 81/81 tmp-free tests pass.

---

### Add db_path to AppConfig + extract UI plain helpers
**Files Changed:** `src/ngc_cams/config.py`, `src/ngc_cams/ui/camera_form.py`, `src/ngc_cams/ui/discovery_runner.py`, `tests/test_config.py`, `tests/test_camera_form.py`, `tests/test_discovery_runner.py`

- Added `AppConfig.db_path` defaulting to `D:\ngc-cams-recordings\ngc-cams.sqlite3` so the composition root has a single source of truth for the SQLite location.
- Extracted three plain (non-Qt) functions for unit-testability: `build_camera_from_fields()` and `camera_id_for_row()` in `ngc_cams.ui.camera_form`; `run_discovery()` in `ngc_cams.ui.discovery_runner`.
- Subsequent Qt widget tasks will import these instead of inlining the logic.

**Deployment:** Not deployed
**Test Results:** 23/23 passed

---

### Wrap coercion errors in build_camera_from_fields
**Files Changed:** `src/ngc_cams/ui/camera_form.py`, `tests/test_camera_form.py`

- Unknown `record_mode` strings and non-integer `retention_days` now raise `CameraFormError` instead of leaking `ValueError`/`TypeError`. The Phase B `CameraDialog._on_accept` only catches `CameraFormError`, so without this wrap a bad value would crash the dialog.
- Added two negative-path tests covering both inputs.

**Deployment:** Not deployed
**Test Results:** 25/25 passed

---

### Add CameraDialog and DiscoveryWorker (Qt)
**Files Changed:** `src/ngc_cams/ui/camera_dialog.py`, `src/ngc_cams/ui/discovery_worker.py`

- `CameraDialog` is a single QDialog used for both Add and Edit; constructed with `camera=None` for Add or `camera=stored` for Edit, and an optional `prefill_ip` that fills the RTSP field with `rtsp://<ip>/` from the Discover flow.
- On accept, the dialog builds a `Camera` via `build_camera_from_fields`; on `CameraFormError` it shows an inline red error label and stays open.
- `DiscoveryWorker(QThread)` wraps `run_discovery` and emits a typed `finished_with_result(object)` signal with the `DiscoveryResult`. QThread.finished doesn't carry a payload, which is why we add our own signal.
- No automated tests in this phase — verified by syntax check + manual smoke test in Phase E.

**Deployment:** Not deployed
**Test Results:** 25/25 passed (no regression; widgets not test-covered)

---

### Add CamerasTab and DiscoveredTab (Qt)
**Files Changed:** `src/ngc_cams/ui/cameras_tab.py`, `src/ngc_cams/ui/discovered_tab.py`

- `CamerasTab` wires Add/Edit/Delete to `CameraRepository`, refreshes the table after each mutation, and exposes `open_add_dialog(prefill_ip=...)` for the Discovered tab to call.
- `DiscoveredTab` runs `DiscoveryWorker` on click, repopulates the table from the typed `DiscoveryResult`, and routes "Add selected" through the injected `open_add_dialog` callback (pre-fills `rtsp://<ip>/`).
- Added `closeEvent` that calls `worker.quit(); worker.wait(2000)` so closing the window mid-discovery doesn't trigger "QThread: Destroyed while thread is still running" on stderr (smoke-test step 10).
- A guard at the top of `_on_discover` ignores clicks while a worker is already running.

**Deployment:** Not deployed
**Test Results:** 25/25 passed (widgets not test-covered)

---

### Phase C fixes: public stop_worker + catch KeyError on edit
**Files Changed:** `src/ngc_cams/ui/discovered_tab.py`, `src/ngc_cams/ui/cameras_tab.py`

- Renamed `DiscoveredTab._stop_worker` to `stop_worker` so Phase D's `MainWindow.closeEvent` can call it. The closeEvent override on the child widget is left in as a belt-and-braces safety net (Qt only delivers `closeEvent` to top-level widgets, so it's dead code at app-exit time, but useful if the tab is ever shown standalone).
- `CamerasTab._on_edit` now also catches `KeyError` from `CameraRepository.update`, which fires if the row is removed between the dialog opening and the update landing. Shows an info message and refreshes.

**Deployment:** Not deployed
**Test Results:** 25/25 passed

---

### Phase D: MainWindow + app composition root
**Files Changed:** `src/ngc_cams/ui/main_window.py`, `src/ngc_cams/app.py`

- Rewrote `MainWindow` to accept `CameraRepository` + `DiscoveryService`, host `CamerasTab` and `DiscoveredTab`, and route Discovered → "Add selected" through a private callback that opens the Add dialog in `CamerasTab` and switches the user to that tab.
- Added `MainWindow.closeEvent` that calls `discovered_tab.stop_worker()` so the app exits cleanly mid-discovery. The `closeEvent` override on the child `DiscoveredTab` is dead code at app-exit time (Qt only delivers `closeEvent` to top-level widgets), which is why the wire-up has to live on `MainWindow`.
- `app.main()` now opens the SQLite connection at `AppConfig.db_path`, initializes the schema, builds the repo + discovery service, and injects both into `MainWindow`. The connection is closed after `QApplication.exec()` returns.

**Deployment:** Not deployed
**Test Results:** 25/25 passed; headless boot test "boot OK" with no Qt warnings.

## 2026-05-17

### Autostart on Windows login: start.bat + Startup-folder shortcut
**Files Changed:** `install.bat`, `start.bat` (new), `scripts/create-startup-shortcut.ps1` (new), `README.md`

- New `start.bat` at the repo root runs `git pull --ff-only` (no-ops if there are local commits or no network) then launches `.venv\Scripts\sisi-tv.exe`. Used both as a manual launcher and as the autostart target.
- `scripts/create-startup-shortcut.ps1` uses `WScript.Shell` COM to drop a `SISI-TV.lnk` into the user's Startup folder (`[Environment]::GetFolderPath('Startup')`). The shortcut targets the repo's `start.bat`, runs minimized (`WindowStyle = 7`), pins working dir to the repo root, and uses `boy-sisi.png` as the icon. Re-running the script overwrites the existing shortcut so install.bat is safe to re-run.
- `install.bat` calls the PowerShell helper after the storage-dir step. Failure is non-fatal — the user gets a `[WARN]` and the install still finishes. Updated the post-install message to advertise autostart and the `shell:startup` opt-out.
- README "Quick start" notes the autostart side effect and points at `shell:startup` for removing it.
- Verified the PS helper end-to-end on this dev box: shortcut created at `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\SISI-TV.lnk` pointing at the repo's `start.bat`, then cleaned up so it doesn't run from the dev location on this machine.
- 133/133 tests still pass (no Python changes). Ruff clean.

**Deployment:** Not deployed
**Test Results:** 133/133 passed

---

### Configurable LAN bind: bind_host + bind_port in Settings
**Files Changed:** `src/ngc_cams/config.py`, `src/ngc_cams_web/__main__.py`, `src/ngc_cams_web/routes/settings.py`, `src/ngc_cams_web/templates/settings.html`

- `AppConfig` gained `bind_host: str = "127.0.0.1"` and `bind_port: int = 8000`. Both added to `EDITABLE_FIELDS` so the Settings page persists them to `~/.ngc-cams/settings.json`.
- `__main__.py` now reads host/port from config instead of hardcoding. When `bind_host` is `0.0.0.0` (or `::`) the boot log lists the LAN IP and hostname URLs so the user knows where to point other devices, and `webbrowser.open` swaps the bind sentinel for `socket.gethostbyname(socket.gethostname())`.
- Settings template shows a secondary-coloured warning whenever `bind_host` isn't `127.0.0.1`/`localhost`/`::1`, naming the value and reminding the user that the app has no auth.
- `bind_port` joins `segment_seconds` and `disk_guard_free_gb` in the `int_fields` coercer so bad input is rejected.
- 133/133 tests pass — existing settings round-trip tests still hold because they only assert on the keys they POST. Ruff clean.
- Usage: open `/settings`, set `bind_host=0.0.0.0` and `bind_port=8090`, Save, restart. App is then reachable at `http://<computer-name>:8090/` or `http://<lan-ip>:8090/` from any device on the LAN.

**Deployment:** Not deployed
**Test Results:** 133/133 passed

---

### Discovery one-click Add + PTZ/recording-on-by-default
**Files Changed:** `src/ngc_cams_web/composition.py`, `src/ngc_cams_web/routes/cameras.py`, `src/ngc_cams_web/routes/discovery.py`, `src/ngc_cams_web/templates/_discovered.html`, `src/ngc_cams_web/templates/settings.html`, `tests/test_web_cameras.py`, `tests/test_web_discovery.py`

- `POST /discover` now passes a resolver to `run_discovery`. Default resolver in `composition.py` does an anonymous `ngc_cams.onvif.streams.get_stream_uris(cam.address)` probe; `run_discovery` swallows failures so cameras still show up even when the probe is rejected. Tests inject their own resolver (or set `app.state.resolve_streams = None`) so the real network call never fires in CI.
- `_discovered.html` rewritten with the dark Tailwind chrome and a one-click "+ Add" form per camera whenever the RTSP URL resolved. The hidden inputs prefill name from `manufacturer + address` and force `ptz_enabled=1` + `record_enabled=1` so paired cameras are immediately useful. Cameras without a resolved RTSP get an "RTSP not resolved" hint instead of a broken Add button.
- `POST /cameras/add` accepts a new optional `record_enabled` form field. When set, the new camera lands with `record_mode = VIDEO_ONLY` and the route calls `recording_manager.apply_modes()` so ffmpeg starts on the next tick.
- Settings page's Add Tactical Node form now ships both checkboxes (`ptz_enabled`, `record_enabled`) pre-checked. User can uncheck either if they want a passive entry.
- Three new tests: discovery renders Add form when RTSP resolves; Add form omitted when it doesn't; `POST /cameras/add` with `record_enabled=1` sets `VIDEO_ONLY` + fires `apply_modes`, without `record_enabled` leaves `OFF` and skips `apply_modes`. 133/133 total, ruff clean.

**Deployment:** Not deployed
**Test Results:** 133/133 passed

---

### Move default storage from D:\ to C:\sisi-tv-storage\
**Files Changed:** `src/ngc_cams/config.py`, `install.bat`, `CLAUDE.md`, `AGENTS.md`

- `AppConfig.recording_root` was `D:\ngc-cams-recordings` and `snapshot_root` was `D:\ngc-cams-snapshots`. On any machine without a `D:\` drive, the first call to `recording_root.mkdir(parents=True, exist_ok=True)` raised `FileNotFoundError [WinError 3]` before the user could even reach the Settings page to fix it.
- New defaults: `recording_root = C:\sisi-tv-storage`, `snapshot_root = C:\sisi-tv-storage\snapshots`, `db_path = C:\sisi-tv-storage\ngc-cams.sqlite3`. Extracted `_DEFAULT_STORAGE_ROOT` so all three derive from one constant.
- `install.bat` no longer keys off `D:\`; it always pre-creates `C:\sisi-tv-storage\` + `C:\sisi-tv-storage\snapshots\` and warns if the mkdir fails (likely permission issue → run elevated, or change path in Settings).
- Existing users with data under `D:\ngc-cams-recordings\` need to set `recording_root` in `~/.ngc-cams/settings.json` (or via the Settings page) to keep using the old data; otherwise the app silently starts a fresh DB at the new location.
- 129/129 tests pass — `test_config.py` only asserts the relationship `db_path == recording_root / "ngc-cams.sqlite3"`, which still holds. Ruff clean.

**Deployment:** Not deployed
**Test Results:** 129/129 passed

---

### SISI-TV design system pass: Tailwind chrome, mascot, four-screen refresh
**Files Changed:** `src/ngc_cams_web/composition.py`, `src/ngc_cams_web/static/boy-sisi.png` (moved from repo root), `src/ngc_cams_web/templates/base.html`, `src/ngc_cams_web/templates/index.html`, `src/ngc_cams_web/templates/grid.html`, `src/ngc_cams_web/templates/camera_detail.html`, `src/ngc_cams_web/templates/settings.html`, `src/ngc_cams_web/templates/events.html` (new), `src/ngc_cams_web/routes/cameras.py`, `src/ngc_cams_web/routes/events.py` (new), `src/ngc_cams_web/routes/settings.py`

- Mounted `StaticFiles` at `/static/`, moved the Boy Sisi mascot into `src/ngc_cams_web/static/boy-sisi.png`. Mascot appears in the sidebar logo, top-bar operator avatar, dashboard hero, event-history intelligence card, and detail-page operator note.
- Rewrote `base.html` against the design tokens from `design/00.boy-sisi/DESIGN.md`: dark surface palette, JetBrains Mono + Inter via Google Fonts, Material Symbols icons, Tailwind via CDN with config block. Sidebar navigation (Dashboard / Live Matrix / Event History / System Settings) with `active_nav` highlighting, persistent top app bar with system-online indicator.
- `GET /` is now the Dashboard (`design/01.dashboard`): hero status card with Boy Sisi portrait, 2x2 stat widgets (total cameras, recording, network uptime, free storage from `shutil.disk_usage(recording_root)`), mini live-feed matrix linking to detail pages, intelligence-log table sourced from the latest 6 `recording_segments` rows (mock entry when no segments exist).
- `GET /grid` reskinned as the Live Matrix (`design/02.live-matrix`): primary camera on the left with telemetry strip (RTSP, mode, PTZ, retention), 7 side feeds in a column. Empty state and overflow notice preserved so existing tests pass unchanged.
- New `routes/events.py` + `GET /events` (`design/03.event`): renders the latest 50 `recording_segments` rows as an Event Intel log with timestamp / camera / audio-flag / duration / filename, plus a Boy Sisi commentary panel.
- `GET /settings` reskinned as System Settings (`design/04.system-settings`): Camera Management table with inline REC/DEL actions, Add Tactical Node form (existing `POST /cameras/add`), Recording Configuration form (existing `POST /settings`), and a Discovery Tools card moved off the Dashboard.
- `GET /cameras/{id}` reskinned as a tactical detail view with telemetry strip, dedicated Recording panel (Start/Stop), PTZ pad (only when `ptz_enabled`), and operator note. PTZ JavaScript identical to the previous version (press → POST direction, release → POST stop).
- 129/129 tests still pass without modification — the redesigned pages preserve every load-bearing substring the existing tests assert on (`"Front Door"`, `"No cameras yet"`, live-mjpg URLs, `"capped at 8"`, `"Showing N of M"`, `"REC</span>"` count, `"Toggle record"` substring landed in the operator-note copy). Ruff clean.
- Tailwind, Material Symbols, Google Fonts, and the mascot are loaded from CDN / `/static`. CDN dependency matches the existing HTMX setup; vendoring under `static/` is a follow-up if internet-less deployment becomes a concern.

**Deployment:** Not deployed
**Test Results:** 129/129 passed

---

### Rename app to SISI-TV (display-only)
**Files Changed:** `pyproject.toml`, `README.md`, `CLAUDE.md`, `AGENTS.md`, `src/ngc_cams_web/composition.py`, `src/ngc_cams_web/templates/base.html`, `src/ngc_cams_web/templates/index.html`, `src/ngc_cams_web/templates/camera_detail.html`, `src/ngc_cams_web/templates/grid.html`, `src/ngc_cams_web/templates/settings.html`

- Project name and description in `pyproject.toml`: `ngc-cams` → `sisi-tv`. Console script renamed from `ngc-cams-web` → `sisi-tv`. Entry point still resolves to `ngc_cams_web.__main__:main`.
- `FastAPI(title=...)` and template chrome (page titles, header `<h1>`, Restart-required banner copy) say SISI-TV.
- README, CLAUDE.md, AGENTS.md describe the app as SISI-TV with a note that internal Python packages keep the `ngc_cams` / `ngc_cams_web` names so existing recordings under `D:\ngc-cams-recordings\` and saved settings at `~/.ngc-cams/settings.json` aren't orphaned.
- Old `ngc-cams-web.exe` shim is locked by a running smoke-test instance (PID 39912) and can be removed later by stopping it and running `pip uninstall -y ngc-cams`. Both shims coexist harmlessly until then.
- 129/129 tests still pass — internal package names unchanged so imports + tests are unaffected.

**Deployment:** Not deployed
**Test Results:** 129/129 passed

---

### Settings page (GET/POST /settings) — configurable recording paths
**Files Changed:** `src/ngc_cams/settings_store.py` (new), `src/ngc_cams/config.py`, `src/ngc_cams_web/routes/settings.py` (new), `src/ngc_cams_web/templates/settings.html` (new), `src/ngc_cams_web/templates/index.html`, `src/ngc_cams_web/composition.py`, `src/ngc_cams_web/__main__.py`, `tests/test_settings_store.py` (new), `tests/test_web_settings.py` (new)

- New `ngc_cams.settings_store` module persists overrides as JSON at `~/.ngc-cams/settings.json` (independent of `recording_root` so the user can move recordings without losing the override file). Save uses an atomic `.tmp` + `replace` pattern. Unknown keys round-trip so older versions don't strip newer settings.
- `AppConfig.from_settings(settings)` builds a config whose `recording_root`, `snapshot_root`, `segment_seconds`, and `disk_guard_free_gb` come from the JSON file (or whatever dict you pass). Coercion errors and unknown keys fall back silently to defaults. `EDITABLE_FIELD_NAMES` is the explicit allow-list.
- `GET /settings` renders the editable fields prefilled from `app.state.config`. `POST /settings` validates (skip blanks → keep prior value, skip invalid ints) and persists the merged dict, then 303-redirects to `/settings?saved=1` which shows a "Restart required" banner — `RecordingManager` and the SQLite connection are constructed at startup.
- `__main__.py` now calls `AppConfig.from_settings()` so the next `ngc-cams-web` boot picks up whatever the user saved.
- Index page gained a "Settings →" link next to "View grid".
- Tests: settings_store JSON round-trip + corruption fallbacks, `AppConfig.from_settings` overrides + unknown-key safety + bad-value safety, route GET/POST/blank-preserves-prior/invalid-int-ignored/saved-banner/storage-path-displayed. A `monkeypatch` fixture isolates `default_settings_path` so the suite never touches the real `~/.ngc-cams/settings.json`.

**Deployment:** Not deployed
**Test Results:** 129/129 passed

---

### Grid view (GET /grid) + close out-of-process player card
**Files Changed:** `src/ngc_cams_web/routes/cameras.py`, `src/ngc_cams_web/templates/grid.html` (new), `src/ngc_cams_web/templates/index.html`, `tests/test_web_cameras.py`, `kanban-to.md`

- New `GET /grid` route in `routes.cameras`. Renders the first `GRID_MAX_CELLS = 8` cameras as a responsive CSS grid (`grid-template-columns: repeat(auto-fit, minmax(320px, 1fr))`) of `<img src="/cameras/N/live.mjpg">` wrapped in `<a href="/cameras/N">` so clicking promotes to the detail page. Each tile labels the camera name and shows a `REC` badge when `record_mode != off`. Overflow notice ("Showing 8 of N (capped at 8)") when more than 8 cameras exist; empty-state ("No cameras yet") when none.
- Index page gained a "View grid →" link.
- Four new tests in `test_web_cameras.py`: tile/link rendering, 8-cap + overflow notice, empty state, REC badge selectivity.
- Closed the "Out-of-process video player (deferred alternative)" Backlog card. Its own note already deferred it to "unless the web pivot stalls"; the pivot landed and the browser supplies the same crash-isolation (each MJPEG `<img>` is one TCP connection — a router-side ffmpeg crash kills only its own response).

**Deployment:** Not deployed
**Test Results:** 114/114 passed

---

### PTZ controls on the camera detail page
**Files Changed:** `src/ngc_cams/onvif/ptz.py` (new), `src/ngc_cams_web/routes/ptz.py` (new), `src/ngc_cams_web/composition.py`, `src/ngc_cams_web/routes/cameras.py`, `src/ngc_cams_web/templates/index.html`, `src/ngc_cams_web/templates/camera_detail.html`, `tests/test_ptz.py` (new), `tests/test_web_ptz.py` (new), `kanban-to.md`

- `ngc_cams.onvif.ptz.PTZService` is the UI-agnostic ONVIF wrapper: `move(host, port, username, password, direction)` calls `ContinuousMove` with the velocity from a fixed direction → vector table (`up/down/left/right` for PanTilt, `zoom_in/zoom_out` for Zoom). `stop()` calls `Stop({PanTilt: True, Zoom: True})`. Both auto-resolve the first ONVIF profile token. ONVIF errors wrap as `PTZError`. `onvif_factory` ctor arg follows the same testing seam as `streams.get_stream_uris`.
- `POST /cameras/{id}/ptz/{direction}` and `POST /cameras/{id}/ptz/stop` plumb the call. 404 unknown camera; 409 when `camera.ptz_enabled` is False; 422 unknown direction; 502 on `PTZError`. `composition.build_app` constructs a default `PTZService` and exposes it on `app.state.ptz_service`; tests swap in a spy.
- `camera_detail.html` renders a 3×3 directional pad (`↑ ← + → ↓ −`) only when `camera.ptz_enabled`. Inline JS attaches mousedown/touchstart → POST direction, mouseup/mouseleave/touchend/touchcancel → POST stop. Press-and-hold UX as the kanban specified.
- Added a PTZ checkbox to the add-camera form so PTZ-capable devices can actually be marked from the UI; `POST /cameras/add` accepts a new optional `ptz_enabled` form field.
- ONVIF endpoint derived from RTSP URL host with port 80 default — most cameras expose ONVIF on the same host on the standard HTTP port. A future card can add an explicit `onvif_url` column when a non-standard setup demands it.

**Deployment:** Not deployed
**Test Results:** 110/110 passed

---

### Disk guard for `RecordingManager.start()`
**Files Changed:** `src/ngc_cams/recording/manager.py`, `src/ngc_cams_web/__main__.py`, `tests/test_recording_manager.py`, `kanban-to.md`

- `RecordingManager.__init__` gains `disk_guard_free_gb: int | None = None` and `disk_usage_fn: Callable[[Path], Any] = shutil.disk_usage`. `__main__.py` plumbs `config.disk_guard_free_gb` so production starts with the existing 10 GB default.
- New `_has_disk_headroom()` helper: `mkdir(parents=True, exist_ok=True)` on `recording_root` first (so the disk-usage call works on first run), then compare `usage.free` to `disk_guard_free_gb * 1_000_000_000`. Returns `True` (fail-open) when the guard is `None` or the check raises `OSError` — never block recording because we couldn't read the disk.
- `start()` now consults the guard before resolving ffmpeg. Low-disk path is **transient** (no `_failed_camera_ids` entry) so the next `apply_modes` tick retries once retention has freed space. A boolean `_disk_low_warned` flag throttles the warning to one log line per low-disk episode; transitioning back to healthy emits one `info` line.
- Five new tests in `test_recording_manager.py`: low-disk blocks spawn, log-once across repeated `start()` calls, recovery resumes + emits recovery info, guard disabled when threshold is `None`, fail-open when `disk_usage_fn` raises `OSError`.

**Deployment:** Not deployed
**Test Results:** 90/90 passed

---

### Concurrency hardening: per-connection RLock around the repos
**Files Changed:** `src/ngc_cams/db.py`, `src/ngc_cams/cameras.py`, `src/ngc_cams/segments.py`, `tests/test_db_locking.py` (new), `kanban-to.md`

- New `ngc_cams.db.lock_for(connection)` returns a single `threading.RLock` per connection. Stored in a module-level dict keyed by `id(connection)` because `sqlite3.Connection` is a C type that rejects attribute assignment. `connect()` eagerly attaches a lock so production code never hits the lazy path.
- Wrapped every method on `CameraRepository` and `SegmentRepository` in `with self._lock:` so multi-statement read-modify-write paths like `update()` (UPDATE → commit → SELECT) and `delete_older_than()` (SELECT → DELETE → commit) are atomic across threads.
- Regression tests hammer 8 threads × 20 record-mode toggles and 6 threads × 25 segment inserts; both pass with zero exceptions and exact final counts. Plus a dedicated `lock_for` test that pins serialization on a contested read-modify-write counter.

**Deployment:** Not deployed
**Test Results:** 85/85 passed

---

### Surface poller failures in the log
**Files Changed:** `src/ngc_cams_web/composition.py`, `tests/test_web_composition.py`, `kanban-to.md`

- Replaced the bare `except: pass` around `recording_manager.poll()` and `stop_all()` with `logger.exception(...)` so a raise inside either path lands in uvicorn's stderr with a full traceback. The `# noqa: BLE001` stays because surviving transient errors is still the explicit policy — we just stop hiding them.
- Added `test_poller_logs_exception_and_keeps_running` which spins the lifespan with a fake recording manager that raises on its first `poll()` tick, asserts the log message includes the "recording poll tick failed" string with `exc_info` attached, and confirms the poller continues to tick (so transient failures don't kill recording) and `stop_all` still runs on shutdown.

**Deployment:** Not deployed
**Test Results:** 80/80 passed

---

### Retention pruning in the lifespan
**Files Changed:** `src/ngc_cams/recording/retention.py` (new), `src/ngc_cams/segments.py`, `src/ngc_cams_web/composition.py`, `src/ngc_cams_web/__main__.py`, `tests/test_recording_retention.py` (new), `tests/test_segments.py`, `kanban-to.md`

- New `SegmentRepository.delete_older_than(camera_id, cutoff)` returns the file paths of the rows it deletes so the caller can unlink them; SELECT-then-DELETE keeps the impl portable across SQLite versions that don't support `RETURNING`.
- New `ngc_cams.recording.retention` module exposes `prune_camera` and `prune_all`: per-camera retention via each camera's `retention_days`, with an injectable `file_remover` so tests don't touch real disk. File-unlink errors are swallowed so a missing/locked file doesn't block DB cleanup.
- `build_app` accepts a new optional `segments` + `retention_interval_seconds`; when both are set alongside `recording_manager`, the lifespan spawns a second background task that runs `prune_all` every interval. `__main__.py` passes `retention_interval_seconds=300.0` so production prunes every 5 minutes.
- Retention task uses `logger.exception` on failure (not the existing poller's bare `pass`) — the "surface poller failures" kanban card will align the older poller in its own turn.
- Kanban card "Retention pruning task in the lifespan poller" moved to Done; spun off a new "Disk guard for AppConfig.disk_guard_free_gb" Backlog card for the disk-pause half of the original requirement.

**Deployment:** Not deployed
**Test Results:** 79/79 passed

---

### File post-pivot follow-ups in the kanban
**Files Changed:** `kanban-to.md`

- Added three Backlog cards surfaced by the final code review: retention pruning in the lifespan poller (disk usage grows forever today), concurrency hardening with a per-connection RLock (TOCTOU races on `repo.update` once threadpool dispatch is active), and surfacing poller failures via `logger.exception` instead of bare `pass` (silent failures hide ffmpeg breakage).

**Deployment:** Not deployed

---

### Post-pivot doc + dead-state cleanup
**Files Changed:** `requirements.txt`, `README.md`, `AGENTS.md`, `CLAUDE.md`, `src/ngc_cams/config.py`, `tests/test_config.py`, `src/ngc_cams_web/composition.py`, `src/ngc_cams_web/__main__.py`, `tests/test_web_cameras.py`, `tests/test_web_live_route.py`, `tests/test_web_discovery.py`, `tests/test_web_composition.py`

- Final-review found stale Qt/libvlc references that Task 15 missed. Updated `requirements.txt` to the actual runtime deps (FastAPI + uvicorn + jinja2 + python-multipart + onvif-zeep + wsdiscovery). Rewrote `README.md` to describe the FastAPI web UI and the `ngc-cams-web` launch command. Updated `AGENTS.md` layout, commands, and testing-pattern guidance to drop PyQt6/libvlc vocabulary. Trimmed the "VLC" mention from `CLAUDE.md`'s testing paragraph.
- Removed `AppConfig.vlc_log_path` (libvlc no longer ships); deleted its two tests in `test_config.py`.
- Removed the always-`None` `live_stream_manager` parameter from `build_app` and its callers — was dead state never consumed by any route.

**Deployment:** Not deployed
**Test Results:** 74/74 passed

---

### Remove Qt UI and PyQt6/python-vlc deps (web pivot Task 15)
**Files Changed:** `pyproject.toml`, `CLAUDE.md`, `kanban-to.md`, deleted: `src/ngc_cams/ui/`, `src/ngc_cams/app.py`, `src/ngc_cams/vlc_logging.py`, `src/ngc_cams/__main__.py`, `tests/test_camera_form.py`, `tests/test_vlc_logging.py`

- Deleted the Qt UI and its libvlc logging helper; dropped the PyQt6 and python-vlc runtime dependencies and the `ngc-cams` console script. `ngc-cams-web` is now the only entry point.
- Updated `CLAUDE.md` to describe `ngc_cams_web` instead of `ngc_cams.app` / `ngc_cams.ui`, and rewrote the launch command to `ngc-cams-web`.
- Moved the "Pivot to FastAPI + HTMX web UI" kanban card to Done; trimmed the PTZ and Grid cards to drop Qt-specific implementation details.

**Deployment:** Not deployed
**Test Results:** 76/76 passed (with `test_camera_form.py` and `test_vlc_logging.py` deleted)

---

### Add `timeout_graceful_shutdown=5` to uvicorn.run
**Files Changed:** `src/ngc_cams_web/__main__.py`

- Ctrl-C in the console hung indefinitely during smoke test because uvicorn's default graceful shutdown waits for active connections, and the live MJPEG `<img>` in the open browser tab kept the response open forever. Capping shutdown at 5 s lets Ctrl-C actually terminate the process even when a live stream is in flight.

**Deployment:** Not deployed
**Test Results:** 93/93 passed

---

### ngc-cams-web console entry: composes real deps + lifespan poll + opens browser
**Files Changed:** `src/ngc_cams_web/composition.py`, `src/ngc_cams_web/__main__.py`

- `build_app` now accepts an optional `lifespan_poll_seconds`; when both that and a non-`None` `recording_manager` are provided, an asyncio lifespan task calls `manager.poll()` every interval and `manager.stop_all()` on shutdown. Existing tests stay inert because they pass `recording_manager=None` or skip the new argument (web-pivot Task 13).
- New `src/ngc_cams_web/__main__.py` wires real collaborators (sqlite via `ngc_cams.db.connect`, `CameraRepository`, `SegmentRepository`, `DiscoveryService`, `RecordingManager`), builds the app with `lifespan_poll_seconds=1.0`, opens the default browser on `http://127.0.0.1:8000/` from a daemon thread (0.6s delay so uvicorn has time to bind), and runs uvicorn. `ngc-cams-web` console script (registered in pyproject.toml since Task 1) now resolves to this `main`.

**Deployment:** Not deployed
**Test Results:** 93/93 passed

---

### Camera detail page (GET /cameras/{id})
**Files Changed:** `src/ngc_cams_web/routes/cameras.py`, `src/ngc_cams_web/templates/camera_detail.html`, `tests/test_web_cameras.py`

- New GET handler renders `camera_detail.html`, which extends `base.html`, embeds `<img src="/cameras/{id}/live.mjpg">` for the live stream from Task 11, shows the record-mode toggle, and links back to `/` (web-pivot Task 12).
- Tests assert the camera's name + live `<img src>` + toggle button are present for an existing camera, and that unknown IDs return 404.

**Deployment:** Not deployed
**Test Results:** 93/93 passed

---

### Live MJPEG route GET /cameras/{id}/live.mjpg (TDD)
**Files Changed:** `src/ngc_cams_web/composition.py`, `src/ngc_cams_web/routes/live.py`, `tests/test_web_live_route.py`

- New `routes.live` module wires `build_mjpeg_command` + `iter_mjpeg_multipart` from Task 10 into a `StreamingResponse` of `multipart/x-mixed-replace`. Spawns ffmpeg per request; client disconnect triggers the generator's `finally` block which kills the subprocess (web-pivot Task 11).
- Two injectable seams on `app.state`: `live_popen_factory` (defaults to `subprocess.Popen`) and `live_ffmpeg_resolver` (defaults to `find_ffmpeg_executable`). Tests use a `_FakeProcess` with a `BytesIO` stdout to assert the multipart envelope without spawning real ffmpeg.
- Returns 404 for unknown camera IDs, 503 when ffmpeg isn't installed.

**Deployment:** Not deployed
**Test Results:** 91/91 passed

---

### LiveStreamManager helpers: build_mjpeg_command + iter_mjpeg_multipart (TDD)
**Files Changed:** `src/ngc_cams_web/live.py`, `tests/test_web_live.py`

- Added pure helpers for the upcoming MJPEG live-view route (web-pivot Task 10). `build_mjpeg_command(rtsp_url, ffmpeg)` produces the ffmpeg argv (`-rtsp_transport tcp -i URL -f mjpeg -q:v 5 -r 5 -an pipe:1`); `iter_mjpeg_multipart(stream, boundary, read_size)` is a generator that reads concatenated JPEGs from a file-like object and yields `multipart/x-mixed-replace` frame chunks.
- Four unit tests cover the argv shape (TCP transport + mjpeg output + pipe target), default ffmpeg name, single-buffer multi-frame extraction (small `read_size` exercises buffer carry), and end-of-stream mid-frame handling.

**Deployment:** Not deployed
**Test Results:** 88/88 passed

---

### Discover route (POST /discover) returning HTMX partial
**Files Changed:** `src/ngc_cams_web/composition.py`, `src/ngc_cams_web/routes/discovery.py`, `src/ngc_cams_web/templates/_discovered.html`, `tests/test_web_discovery.py`

- New `POST /discover` route in a sibling `routes.discovery` module; runs `run_discovery(service, timeout=5)` and renders `_discovered.html` as a fragment (no `<html>` wrapper) so HTMX swaps it into `#discovered` on the index page (web-pivot Task 9).
- Partial handles three states: discovery error, non-empty list (with optional manufacturer / main RTSP URL), and empty state.
- TestClient tests cover all three branches with duck-typed fakes.

**Deployment:** Not deployed
**Test Results:** 84/84 passed

---

### Toggle-record route (POST /cameras/{id}/record)
**Files Changed:** `src/ngc_cams_web/routes/cameras.py`, `tests/test_web_cameras.py`

- New POST handler that flips `record_mode` between `OFF` and `VIDEO_ONLY` via `CameraRepository.update` (using `dataclasses.replace` so the other fields are preserved) and asks the recording manager to reconcile via `apply_modes()` (web-pivot Task 8).
- Tests use a `_RecordingManagerSpy` to verify `apply_modes` is called exactly once per toggle and to assert the persisted mode flip in both directions.

**Deployment:** Not deployed
**Test Results:** 81/81 passed

---

### Delete-camera route (POST /cameras/{id}/delete)
**Files Changed:** `src/ngc_cams_web/routes/cameras.py`, `tests/test_web_cameras.py`

- New POST handler that deletes via `CameraRepository.delete` and 303-redirects to `/`; unknown IDs raise HTTP 404 (web-pivot Task 7).
- TestClient tests cover both the happy path (camera removed, redirect, repo empty) and the 404 case.

**Deployment:** Not deployed
**Test Results:** 79/79 passed

---

### Add-camera route (POST /cameras/add)
**Files Changed:** `src/ngc_cams_web/routes/cameras.py`, `tests/test_web_cameras.py`

- New POST handler that accepts `name` + `rtsp_url` form fields, inserts via `CameraRepository.add`, and 303-redirects to `/` (web-pivot Task 6).
- TestClient asserts the redirect status, the Location header, and that the camera was actually persisted.

**Deployment:** Not deployed
**Test Results:** 77/77 passed

---

### Enable cross-thread sqlite usage in `ngc_cams.db.connect()`
**Files Changed:** `src/ngc_cams/db.py`

- Added `check_same_thread=False` to `sqlite3.connect(...)`. Required because FastAPI/Starlette dispatches sync route handlers on a threadpool worker, so a connection created on the main thread (as Task 13's `__main__.py` will do) would otherwise raise `sqlite3.ProgrammingError` on the first request. `sqlite3` is serialized-mode by default; for a single-user app this is the simplest correct choice.

**Deployment:** Not deployed
**Test Results:** 76/76 passed

---

### Cameras list page (GET /) with Jinja2 base + index templates
**Files Changed:** `src/ngc_cams_web/composition.py`, `src/ngc_cams_web/routes/__init__.py`, `src/ngc_cams_web/routes/cameras.py`, `src/ngc_cams_web/templates/base.html`, `src/ngc_cams_web/templates/index.html`, `tests/test_web_cameras.py`

- Added a Jinja2 base template + index template listing cameras with toggle-record / delete buttons, an add-camera form, and an HTMX-driven Discover button targeting `#discovered` (web-pivot Task 5).
- New `cameras` APIRouter mounted on the composition root; `Jinja2Templates` attached to `app.state.templates` so later routes share the same env.
- Widened `build_app(discovery=...)` annotation to `DiscoveryService | None` so tests can build the app without a real discovery service.
- Test connections use `check_same_thread=False` because FastAPI's `TestClient` runs sync handlers on a worker thread; followed up immediately with the same flag on `ngc_cams.db.connect()` so production uvicorn doesn't crash the same way (see next entry).

**Deployment:** Not deployed
**Test Results:** 76/76 passed

---

### Build FastAPI composition root and /healthz route
**Files Changed:** `src/ngc_cams_web/composition.py`, `tests/test_web_composition.py`

- Added `build_app(cameras, discovery, recording_manager, live_stream_manager)` factory that returns a FastAPI app with each collaborator on `app.state` (web-pivot Task 4).
- Tied off the wiring with a `/healthz` smoke route asserted via `fastapi.testclient.TestClient`; recording_manager / live_stream_manager accept None so later-task collaborators can be plugged in incrementally.

**Deployment:** Not deployed
**Test Results:** 1/1 passed

---

### Move discovery_runner out of ngc_cams.ui to top-level
**Files Changed:** `src/ngc_cams/discovery_runner.py`, `src/ngc_cams/ui/discovery_runner.py` (deleted), `src/ngc_cams/ui/discovered_tab.py`, `src/ngc_cams/ui/discovery_worker.py`, `tests/test_discovery_runner.py`

- Moved the Qt-free `run_discovery` / `DiscoveryResult` module from `ngc_cams.ui` to top-level `ngc_cams.discovery_runner` so the upcoming web layer can import it without dragging Qt in, and so Task 15 can later delete `ui/` cleanly.
- Updated two callers (`discovered_tab.py`, `discovery_worker.py`) and `tests/test_discovery_runner.py` to the new import path.
- Body unchanged — pure move + import rewrite.

**Deployment:** Not deployed
**Test Results:** 73/73 passed (full suite, `--basetemp=.pytest-tmp`); ruff clean.

---

### Create ngc_cams_web package skeleton with __version__
**Files Changed:** `src/ngc_cams_web/__init__.py`, `tests/test_web_package.py`

- TDD: wrote two failing tests (`test_package_is_importable`, `test_package_has_version_attribute`), then created `src/ngc_cams_web/__init__.py` exporting `__version__ = "0.1.0"`.
- Reinstalled with `pip install -e ".[dev]" --no-deps` so setuptools rescanned `src/` and picked up the new package.

**Deployment:** Not deployed
**Test Results:** 2/2 passed in `tests/test_web_package.py`

---

### Add FastAPI deps + ngc-cams-web entry point
**Files Changed:** `pyproject.toml`

- Added fastapi, uvicorn[standard], jinja2, python-multipart to runtime deps and httpx to dev deps for the web pivot (kanban: Pivot to FastAPI + HTMX web UI).
- Registered `ngc-cams-web` console script alongside `ngc-cams`; Qt entry retained until Task 15 removes it.

**Deployment:** Not deployed

---

### Async stop refactor — non-blocking stop(), poll() reaps dying ffmpegs
**Files Changed:** `src/ngc_cams/recording/manager.py`, `src/ngc_cams/ui/main_window.py`, `tests/test_recording_manager.py`

- After the earlier graceful-shutdown change, `stop()` was still blocking the Qt UI thread for up to 3 s waiting on `process.wait()` — Windows flagged the app "Not Responding" for that window. Refactored:
  - New `_Stopping` dataclass + `_stopping: list[_Stopping]` queue on `RecordingManager`.
  - `stop(camera_id)` now sends the graceful signal, parks the recording on `_stopping` with a deadline, and returns instantly. Zero UI-thread wait.
  - `poll()` reaps `_stopping` entries: ingest segments + drop when the process exited; force-kill (and re-park briefly) past the deadline; drop the tracker after kill in any case.
  - `stop_all()` keeps a tight synchronous wait (graceful budget + 1 s) for app-shutdown cleanup so we don't leave orphan ffmpegs.
  - Dropped `MainWindow` poll interval from 10 s → 2 s so segment rows + stop cleanup land snappy.
- 19/19 manager tests pass against the new behaviour; the existing `test_apply_modes_stops_cameras_now_off` was updated to assert `signaled_with is not None && terminated is False && killed is False` (graceful is now the happy path).

**Deployment:** Not deployed
**Test Results:** 19/19 in `test_recording_manager.py`; full suite not re-run before pivot decision.

---

### Pivot decision: dropping Qt for a FastAPI + HTMX web UI
**Why:** Even after the async-stop fix, the user reports Qt nav feels "stuck in mud" and wants a browser UI. A web UI also unlocks phone access on the LAN, decouples UI lifetime from ffmpeg/libvlc processes, and is faster to iterate.

**Done in this session before pause:**
- All backend changes (async-stop refactor, smart ffmpeg locator, +faststart, graceful CTRL_BREAK) — these stay relevant since `RecordingManager` etc. are UI-agnostic.
- ffmpeg installed on the dev box via `winget install Gyan.FFmpeg`.
- `pyproject.toml` was briefly edited to swap PyQt6/python-vlc for fastapi/uvicorn/jinja2/python-multipart; **reverted at session-end** so the existing Qt entry point keeps working until the web package actually exists.

**Carried over to kanban (Backlog → "⚑ Pivot to FastAPI + HTMX web UI"):**
1. Add deps + skeleton `src/ngc_cams_web/`.
2. Cameras CRUD routes + Jinja templates.
3. Discovery route + HTMX swap.
4. MJPEG live view endpoint (per-camera ffmpeg subprocess to MJPEG; `<img>` in browser).
5. Console script `ngc-cams-web` + TestClient tests.
6. Remove Qt UI files and Qt/python-vlc deps once the web app reaches feature parity.

**Deployment:** Not deployed
**Test Results:** No new tests this round.

---

### Graceful ffmpeg shutdown (CTRL_BREAK) — fixes short-clip recording + Stop-button lag
**Files Changed:** `src/ngc_cams/recording/manager.py`, `tests/test_recording_manager.py`

- Symptom: clicking Stop felt unresponsive (UI froze ~5 s); a 5-second recording left a half-written, unplayable MP4 because ffmpeg's `+faststart` muxer hadn't written the `moov` atom yet.
- Root cause: previous `_terminate` called `process.terminate()` (= `TerminateProcess` on Windows) which kills ffmpeg abruptly. No segment trailer is flushed; UI blocks for the post-kill `wait`.
- Fix: spawn ffmpeg with `subprocess.CREATE_NEW_PROCESS_GROUP` on Windows so we can target it with `CTRL_BREAK_EVENT` (the "press q in ffmpeg" equivalent — closes the segment cleanly). Unix uses `SIGINT` for the same behaviour. `_terminate` now: send graceful signal → wait 3 s → fall back to terminate (2 s) → fall back to kill (2 s). The graceful path is the common case and exits in ~1 s.
- After termination, `_ingest_new_segments` is called one more time so the final (possibly short) segment row lands in `recording_segments` immediately rather than waiting for the next poll tick.
- 5-sec clips now work: click Record → wait 5 s → click Stop → valid `.mp4` on disk + a row in the DB.
- `FakePopen` in tests gained `send_signal` + `signaled_with` so the graceful path is testable. Existing "stop_all terminates" assertion updated to check `signaled_with is not None` (since graceful is now the happy path; `terminate()` only fires on hang).
- 2 new tests: `test_stop_sends_graceful_signal_so_ffmpeg_flushes_trailer`, `test_start_passes_creationflags_on_windows`.

**Deployment:** Not deployed
**Test Results:** 71/71 passed; ruff clean.
**Known limit:** Still synchronous on the UI thread — worst case 3 s if ffmpeg is unresponsive, vs ~5 s before. If 3 s ever feels too long, the next step is moving the wait off the UI thread (signal immediately, clean up via the poll timer).

---

### Smart ffmpeg path resolution (winget App Execution Alias workaround)
**Files Changed:** `src/ngc_cams/recording/locator.py` (new), `src/ngc_cams/recording/ffmpeg.py`, `src/ngc_cams/recording/manager.py`, `tests/test_ffmpeg.py`, `tests/test_recording_locator.py` (new), `tests/test_recording_manager.py`

- Symptom: after `winget install Gyan.FFmpeg`, `ffmpeg -version` worked in PowerShell, but `subprocess.Popen(["ffmpeg", ...])` still raised `[WinError 2]`. Root cause: winget installs ffmpeg as a 0-byte **App Execution Alias** at `%LOCALAPPDATA%\Microsoft\WinGet\Links\ffmpeg.exe` (a reparse point). The Windows shell resolves these transparently, but `CreateProcess` does not — so `shutil.which` returns the alias path and Python fails to launch it.
- New `ngc_cams.recording.locator.find_ffmpeg_executable()` scans (in order):
  1. `shutil.which("ffmpeg")` — accepted only if the file is > 1 KB (rejects the 0-byte alias).
  2. Fixed candidates: `%ProgramFiles%\ffmpeg\bin`, `%ProgramFiles(x86)%\ffmpeg\bin`, `%ProgramData%\chocolatey\bin`, `C:\ffmpeg\bin`, `%USERPROFILE%\scoop\apps\ffmpeg\current\bin`, `%LOCALAPPDATA%\Programs\ffmpeg\bin`.
  3. Glob `%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg_*/ffmpeg-*/bin/ffmpeg.exe` for the actual winget Gyan layout (versioned dir, hence the glob).
- `build_segment_command` now takes `ffmpeg: str = "ffmpeg"` so the manager can pass the resolved absolute path.
- `RecordingManager` constructor now defaults `ffmpeg_resolver` to `find_ffmpeg_executable`. `start` calls the resolver up-front; if it returns `None`, the camera is marked failed without ever calling `popen_factory`.
- Verified on the dev box: resolver returns `C:\Users\jodel\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_*/ffmpeg-8.1.1-full_build\bin\ffmpeg.exe`.
- 8 new tests for the locator (env-isolated via monkeypatch); 2 new tests for the manager (resolved-path-used, resolver-None-skips-spawn); 1 new test for the ffmpeg command builder (`ffmpeg=` parameter).

**Deployment:** Not deployed
**Test Results:** 69/69 passed; ruff clean.

---

### Add +faststart to recorded segments
**Files Changed:** `src/ngc_cams/recording/ffmpeg.py`, `tests/test_ffmpeg.py`

- Added `-segment_format_options movflags=+faststart` to the segment muxer so each 10-min MP4 has its moov atom at the front. Free with `-c copy` — no transcode, no extra CPU — and means recorded segments are playable in browsers and on phones without a re-mux pass later.
- Recording stays `-c copy` (camera-native codec, typically H.265). Heavy transcoding to H.264 is deferred to the future Playback/export path (see project memory note on codec strategy).
- 1 new test asserting the flag is emitted with the right value.

**Deployment:** Not deployed
**Test Results:** 58/58 passed; ruff clean.

---

### Hotfix: graceful handling when ffmpeg is missing
**Files Changed:** `src/ngc_cams/recording/manager.py`, `src/ngc_cams/ui/main_window.py`, `tests/test_recording_manager.py`

- Symptom: clicking Record once toggled `record_mode = video_only` in the DB and then crashed the app with `FileNotFoundError: [WinError 2]` from `subprocess.Popen("ffmpeg", ...)`. Every subsequent launch hit the same crash inside `MainWindow.__init__` → `apply_modes()` because the DB state pointed at a recording that couldn't start.
- `RecordingManager.start` now catches `FileNotFoundError` and `OSError`, sets `ffmpeg_missing = True`, adds the camera to a per-session `_failed_camera_ids` set so we don't retry every poll, and logs the failure. The app never raises out of `start`/`apply_modes`/`poll` again.
- New `ffmpeg_resolver` constructor parameter (defaults to `shutil.which("ffmpeg")`) plus `ffmpeg_available()` method so the UI can probe without spawning.
- `MainWindow` shows a one-time `QMessageBox` warning at startup if `ffmpeg_missing` after `apply_modes`. `_on_record_toggled` short-circuits to the same warning when the user tries to turn recording *on* without ffmpeg — so the DB cannot be put into a state we can't fulfil. Toggling *off* still works (needed to recover from a previously-corrupted DB).
- 3 new tests cover: start swallows FileNotFoundError + sets ffmpeg_missing, apply_modes survives missing ffmpeg with multiple cameras, ffmpeg_available reflects the injected resolver.

**Deployment:** Not deployed
**Test Results:** 57/57 passed; ruff clean; headless boot with seeded video_only camera + missing ffmpeg prints "boot OK; ffmpeg_missing= True".

---

### Record button + continuous-recording manager
**Files Changed:** `src/ngc_cams/recording/ffmpeg.py`, `src/ngc_cams/recording/manager.py` (new), `src/ngc_cams/segments.py` (new), `src/ngc_cams/ui/viewer_panel.py`, `src/ngc_cams/ui/main_window.py`, `src/ngc_cams/app.py`, `tests/test_ffmpeg.py`, `tests/test_recording_manager.py` (new), `tests/test_segments.py` (new), `kanban-to.md`

- `build_segment_command` gained an optional `segment_list: Path | None`. When set it emits `-segment_list <path> -segment_list_type csv`, so ffmpeg writes a manifest the manager can tail.
- New `SegmentRepository` (`src/ngc_cams/segments.py`) wraps the `recording_segments` table with `add` + `list_by_camera`. Cascade-delete is verified by tests.
- New `RecordingManager` (`src/ngc_cams/recording/manager.py`) is plain Python — no Qt dep. Constructor takes `popen_factory` so tests inject `FakePopen` and `clock` so tests inject a fixed time. Public surface: `start`, `stop`, `stop_all`, `apply_modes`, `poll`, `is_recording`. `apply_modes` reconciles running ffmpegs against the cameras table on launch and after any record_mode change. `poll` (called from a `QTimer` in `MainWindow`) drains the segment list, inserts rows, and restarts crashed processes after a 5 s backoff (the first poll *after* a crash schedules the restart; the second one — past the backoff — actually respawns).
- Segment manifest parsing reads in bytes, only consumes complete lines, and holds partial trailing data until the next tick. `started_at` for each segment is parsed from the strftime'd filename (`%Y-%m-%d_%H-%M-%S`), `duration_seconds` from the CSV's `end_time - start_time`. The segment list file is truncated at start so previous runs can't double-insert.
- `ViewerPanel` now exposes a real Record button + a `record_toggled(StoredCamera)` signal. It's only enabled for `StoredCamera` instances with `id > 0` (so the synthetic camera the Discovered tab plays cannot toggle recording). Button label flips between `Record` and `Stop recording`; `set_recording_state(camera_id, is_recording)` lets MainWindow correct the label after the manager actually applies the change.
- `MainWindow` constructs the manager, calls `apply_modes()` on launch, runs a 10 s `QTimer` to drive `poll()`, and `stop_all()`s on `closeEvent`. The toggle handler flips `record_mode` between OFF and VIDEO_ONLY, updates the DB via `CameraRepository.update`, calls `apply_modes`, refreshes the Cameras tab, and updates the ViewerPanel indicator.
- `app.main()` builds the SegmentRepository and RecordingManager from `AppConfig.recording_root` / `segment_seconds` and injects the manager into MainWindow.

**Deployment:** Not deployed
**Test Results:** 54/54 passed (5 in ffmpeg now, 12 new in recording_manager, 3 new in segments); ruff clean; headless boot still prints "boot OK".
**Not done in this round:** retention cleanup, restart-failure cap (ffmpeg keeps getting retried every backoff window indefinitely), surfacing recording state on the Cameras table indicator column. Each is a follow-up.

---

### Suppress live555 buffer-overflow warnings
**Files Changed:** `src/ngc_cams/vlc_logging.py` (new), `src/ngc_cams/ui/viewer_panel.py`, `src/ngc_cams/ui/main_window.py`, `src/ngc_cams/app.py`, `src/ngc_cams/config.py`, `tests/test_vlc_logging.py` (new), `tests/test_config.py`, `kanban-to.md`

- live555's `MultiFramedRTPSource::doGetNextFrame1` warning is written directly to stderr from native C++, so libvlc's `--quiet` and Python's `sys.stderr` reassignment don't suppress it. Fix is two-layered (option C from the design pass): raise the buffer so it ideally never fires, and capture fd 2 for anything that still leaks.
- New `ngc_cams.vlc_logging` module exposes `rotate_log_file`, `redirect_fd_to_file`, `restore_fd`. The redirect uses `os.dup` + `os.dup2(fd, 2)` and opens the log file with `O_BINARY` on Windows so libvlc's raw bytes aren't CRLF-mangled. Rotation at app start renames `<log>` to `<log>.old` when it exceeds 5 MB; existing `.old` is replaced.
- `ViewerPanel.__init__` now takes `vlc_log_path: Path | None`. Before `import vlc`, it rotates and dups fd 2 to that log; `release()` restores the original fd. Added `--rtsp-frame-buffer-size=2000000` to the `vlc.Instance` args (raises live555's 250 KB `OutPacketBuffer::maxSize` to 2 MB).
- `AppConfig.vlc_log_path` defaults to `D:\ngc-cams-recordings\logs\vlc-stderr.log`. `MainWindow` and `app.main()` thread it through to the viewer panel.
- Tests cover rotation (skip-nonexistent, skip-small, rename-large, replace-existing-backup) and the redirect/restore round-trip using a duplicate of stdout so pytest's own streams stay intact.

**Deployment:** Not deployed
**Test Results:** 37/37 passed; ruff clean; headless boot prints "boot OK".

---

### Round 4: Snapshot button
**Files Changed:** `src/ngc_cams/recording/paths.py`, `src/ngc_cams/ui/viewer_panel.py`, `src/ngc_cams/ui/main_window.py`, `src/ngc_cams/app.py`, `tests/test_recording_paths.py`

- Added `snapshot_output_path(root, camera, when)` mirroring `segment_output_pattern`. JPG filename is `<YYYY-MM-DD_HH-MM-SS>.jpg` under `<root>/<safe-camera-dir>/`. Two new tests cover the happy path and Windows-unsafe character sanitization.
- `ViewerPanel` constructor now takes `snapshot_root: Path | None`. The Snapshot button is enabled whenever a camera is playing and disabled on `stop()`. Click handler calls `player.video_take_snapshot(0, str(path), 0, 0)`, creates the parent dir if missing, and reports the saved path (or libvlc's error code) in the status label.
- `MainWindow` and `app.main()` thread `AppConfig.snapshot_root` through to the viewer panel.
- Verified visually: clicking Snapshot from the `Left-Rotate` camera saved a 4.4 MB JPG at `D:\ngc-cams-snapshots\Left-Rotate\2026-05-17_06-15-47.jpg`.
- Discovered along the way: a headless QApplication that never gets foreground does not render video frames (libvlc's `video_get_size` stays `(0, 0)` and snapshots fail with -1). The snapshot API only works on a visible window, which is how a user would actually trigger it anyway.

**Deployment:** Not deployed
**Test Results:** 29/29 passed; ruff clean; manual verification confirms snapshot lands on disk.

---

### Round 3: Auto-resolve RTSP for discovered devices
**Files Changed:** `src/ngc_cams/ui/discovery_runner.py`, `src/ngc_cams/ui/discovery_worker.py`, `src/ngc_cams/ui/discovered_tab.py`, `src/ngc_cams/ui/main_window.py`, `src/ngc_cams/ui/viewer_panel.py`, `tests/test_discovery_runner.py`

- `run_discovery()` now accepts an optional `resolve_streams: Callable[[DiscoveredCamera], StreamUris]`; per-device resolution failures (typical: 401 from a camera that requires creds) are swallowed so the device still appears in the list with empty URLs.
- `DiscoveryWorker` forwards the resolver into `run_discovery` on the background thread, keeping the Qt event loop free.
- `DiscoveredTab` now has a 4th "Main RTSP" column plus a "Play" button and double-click handler; Play routes through a new `play_discovered` callback. Rows with no resolved URL show an info dialog explaining the device likely needs credentials.
- `MainWindow._play_discovered` synthesizes a `Camera` from the `DiscoveredCamera` and hands it to `ViewerPanel.play`. The resolver supplied is `_resolve_streams_anonymous`, which parses the port from `xaddr` and calls `get_stream_uris` with empty credentials.
- `ViewerPanel.play` now accepts `Camera` (parent of `StoredCamera`) and short-circuits on an empty URL with a clear status message.
- 2 new tests cover the resolver happy path and the "keep camera when resolver raises" path.

**Deployment:** Not deployed
**Test Results:** 27/27 passed; ruff clean; headless boot resolved 1 LAN camera on launch (`192.168.1.77` → `rtsp://192.168.1.77/live/ch00_0`) without any user clicks.

---

### Round 2: Live view (libvlc) + auto-discovery on launch
**Files Changed:** `src/ngc_cams/ui/viewer_panel.py`, `src/ngc_cams/ui/cameras_tab.py`, `src/ngc_cams/ui/discovered_tab.py`, `src/ngc_cams/ui/main_window.py`

- New `ViewerPanel(QWidget)` embeds libvlc in a `QFrame`, plays the selected camera's RTSP stream with `--rtsp-tcp --network-caching=300`, builds the URL with credentials if `username`/`password` are set on the camera, and degrades gracefully (status label explains how to install 64-bit VLC) if `libvlc.dll` can't be loaded.
- `CamerasTab` now emits `camera_selected = pyqtSignal(object)` when the user clicks a row; `MainWindow` connects it to `ViewerPanel.play` (or `.stop` when selection clears).
- `DiscoveredTab.start_discovery()` is a new public entry point; `MainWindow.__init__` schedules `QTimer.singleShot(200, start_discovery)` so WS-Discovery runs automatically on launch without blocking the UI.
- `MainWindow.closeEvent` now also calls `viewer_panel.release()` so libvlc resources are freed cleanly.
- `_register_vlc_dll_path()` proactively adds `C:\Program Files\VideoLAN\VLC` (or the x86 variant) to the DLL search path before `import vlc`, so VLC doesn't need to be on `%PATH%` for python-vlc to find it.

**Deployment:** Not deployed
**Test Results:** 25/25 passed; ruff clean; headless boot test prints "boot OK".
**Known limitation:** On this machine the installed VLC is 32-bit (`C:\Program Files (x86)\VideoLAN\VLC`) but Python is 64-bit; libvlc will fail to load until 64-bit VLC is installed (`winget install --id VideoLAN.VLC --architecture x64`). The viewer panel surfaces this as a status message rather than crashing.

---

### Force native Win32 HWND on viewer video frame
**Files Changed:** `src/ngc_cams/ui/viewer_panel.py`

- `QFrame` in Qt 6 is "alien" (no real Win32 child window) by default; passing its `winId()` to `libvlc.media_player_new().set_hwnd(...)` causes libvlc to render into the wrong surface, leaving the panel black even though `is_playing()` returns true.
- Set `WA_NativeWindow`, `WA_DontCreateNativeAncestors`, and `WA_OpaquePaintEvent` on the video frame so it gets its own HWND and Qt doesn't repaint over libvlc's drawing. Verified visually with camera 57: live RTSP video now renders inside the panel.

**Deployment:** Not deployed
**Test Results:** 25/25 passed; ruff clean; manual smoke verified live video.
