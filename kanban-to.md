# ngc-cams Kanban

Source of truth for what's next on the personal-app roadmap. Move cards across columns as work progresses. Update dates in `## Done` so the audit trail matches `process/activity-log.md`.

---

## Backlog

### ⚑ Pivot to FastAPI + HTMX web UI (replaces Qt)
**Why:** Qt UI navigation feels laggy on the user's Windows box, and the Stop button froze the app ("Not Responding") because subprocess waits ran on the UI thread. A web UI separates frontend from backend, lets the existing Python services stay, and lets the user view feeds from any device on the LAN. Async-stop work landed already (see `recording.manager`), but the freezing was the trigger to abandon Qt entirely.

**Keep:** `ngc_cams.cameras`, `ngc_cams.segments`, `ngc_cams.db`, `ngc_cams.config`, `ngc_cams.models`, `ngc_cams.onvif.*`, `ngc_cams.recording.*`. These are UI-agnostic and tested.

**Delete (after pivot lands):** `src/ngc_cams/ui/*`, `src/ngc_cams/app.py`, `src/ngc_cams/vlc_logging.py` (libvlc-specific — no longer needed). Drop `PyQt6` and `python-vlc` deps. Tests in `test_camera_form.py` / `test_discovery_runner.py` may move into web-layer tests.

**Add:**
- `src/ngc_cams_web/` package — FastAPI app, Jinja2 templates, HTMX for partial updates.
- `python-multipart` for form posts; `fastapi`, `uvicorn[standard]`, `jinja2` deps.
- Console entry `ngc-cams-web` that boots uvicorn on localhost and auto-opens the default browser.
- Routes (round 1): `GET /` (camera list), `POST /add` (form), `POST /{id}/delete`, `POST /{id}/record` (toggle off↔video_only), `POST /discover`, `GET /cameras/{id}/live.mjpg` (MJPEG live view streamed from a per-camera ffmpeg child).
- Live view: round 1 = MJPEG via ffmpeg (`<img src="/cameras/N/live.mjpg">` — works in every browser, no JS player needed). Round 2 upgrade to HLS (hls.js, `-c copy` so CPU stays low, ~5 s latency).
- Tests via `fastapi.testclient.TestClient`; mock the discovery + recording manager as before. Add `httpx` to dev deps.

**Open questions:**
- Auth? Single user on LAN → likely none. If exposed beyond localhost, a single token header is enough.
- One ffmpeg per camera for live MJPEG vs. shared with the recording ffmpeg? Probably separate processes — keeps recording-segment integrity decoupled from view restarts when a browser tab opens/closes. Cost: 2x ffmpeg per camera when both live-viewing and recording.

**Done when:** Running `ngc-cams-web` opens a browser tab showing the cameras list. Add/Delete/Discover/Record work end-to-end. Clicking a camera shows the live MJPEG stream. Closing the browser doesn't kill any ffmpeg; closing the console process does via signal-handler-driven `stop_all`.

**WIP tasks (carried over from session):**
1. Add FastAPI deps + skeleton package (`src/ngc_cams_web/`) — `pyproject.toml` edit was reverted; reapply when starting.
2. Cameras CRUD routes + Jinja templates.
3. Discovery route + UI (HTMX swap for the "Discovered" list).
4. MJPEG live view endpoint (per-camera ffmpeg subprocess).
5. Console script + TestClient tests.
6. Move Qt cards in this kanban under a "Web rewrite" sub-section or delete the Qt-specific ones (PTZ, Grid — they need redesign for HTML).

### Out-of-process video player (deferred alternative)
Could keep Qt but isolate libvlc in a separate child process for crash resilience — ODM uses this pattern (`odm.player.host.exe` separate from the main WPF app). Defer unless the web pivot stalls; web naturally provides the same isolation (browser is the "player host").

### PTZ controls
For cameras with `ptz_enabled=True`, surface a small directional pad (up / down / left / right / zoom in / zoom out / stop) on `ViewerPanel`. Each button calls `ONVIFCamera.create_ptz_service().ContinuousMove(...)` against the selected camera's `host:port`.

> **Note:** This card was written for the Qt UI. After the web pivot, redesign as buttons in the camera detail page that POST to `/cameras/{id}/ptz/{direction}` and `/cameras/{id}/ptz/stop`. The ONVIF call itself stays in `src/ngc_cams/onvif/ptz.py` — UI-agnostic.
For cameras with `ptz_enabled=True`, surface a small directional pad (up / down / left / right / zoom in / zoom out / stop) on `ViewerPanel`. Each button calls `ONVIFCamera.create_ptz_service().ContinuousMove(...)` against the selected camera's `host:port`.

- **Touches:** new `src/ngc_cams/onvif/ptz.py` (wraps `ContinuousMove` / `Stop`, accepts an injected ONVIF service factory for tests), `src/ngc_cams/ui/viewer_panel.py` (PTZ widget shown only when `camera.ptz_enabled`), tests for the service wrapper with a fake ONVIF.
- **Open questions:** Step-based vs. continuous moves? Start with continuous-while-button-pressed and Stop on release for the directional pad; keyboard-arrow support is YAGNI for round 1.
- **Done when:** With a PTZ-capable camera selected, pressing a direction moves the camera; releasing stops it; ensemble cameras without PTZ don't see the controls.

### Grid view of multiple cameras
Replace single-stream view with an N×N grid (2×2 then 3×3) of mini-viewers when "Grid" is clicked. Selecting a cell promotes it to single view.

> **Note:** Originally specced for the Qt `ViewerPanel`. After the web pivot, this becomes a CSS grid of `<img src="/cameras/N/live.mjpg">` elements — much simpler than libvlc-per-cell. Cap at 8 cells (PRD limit) and warn if more cameras than cells. Browser tab close releases the MJPEG fetches automatically (no manual teardown).

---

## In Progress

_empty_ — web pivot is paused; pick up from the "Pivot to FastAPI + HTMX web UI" card in Backlog.

---

## Done

- **2026-05-16** — Cameras CRUD + manual Discover (Phases A-E from `docs/plans/2026-05-16-ui-wireup.md`). 25/25 tests, ruff clean.
- **2026-05-17** — Live view (libvlc embedded in Qt) + auto-discovery on launch + native-HWND fix. Verified visually with camera 57 streaming into the viewer.
- **2026-05-17** — Auto-resolve RTSP for discovered devices via anonymous `get_stream_uris`. Discovered tab now shows Main RTSP and exposes Play / double-click to stream without going through Add. 27/27 tests, headless boot resolved 1 LAN camera on launch.
- **2026-05-17** — Snapshot button wired to libvlc `video_take_snapshot`; JPGs land at `D:\ngc-cams-snapshots\<safe-camera-dir>\<timestamp>.jpg`. Verified visually: `Left-Rotate\2026-05-17_06-15-47.jpg` (4.4 MB) on disk. 29/29 tests.
- **2026-05-17** — Silenced live555 buffer-overflow warnings. Bumped `--rtsp-frame-buffer-size=2000000` on the libvlc Instance and capture fd 2 into `D:\ngc-cams-recordings\logs\vlc-stderr.log` (rotates to `.old` at 5 MB) so anything that still slips through stays out of the console. 37/37 tests, ruff clean.
- **2026-05-17** — Record button + continuous-recording manager. `RecordingManager` spawns one ffmpeg per camera with `record_mode != off`, reconciles via `apply_modes`, tails ffmpeg's CSV segment list and inserts rows into `recording_segments`, and restarts crashed processes after a 5 s backoff. ViewerPanel Record button toggles `record_mode` between OFF and VIDEO_ONLY. 54/54 tests, ruff clean.
