# ngc-cams Kanban

Source of truth for what's next on the personal-app roadmap. Move cards across columns as work progresses. Update dates in `## Done` so the audit trail matches `process/activity-log.md`.

---

## Backlog

### Disk guard for `AppConfig.disk_guard_free_gb`
Retention pruning landed but the disk-guard half of the original card didn't: when free disk under the configured threshold, new segment writes should pause until pruning catches up. Live view should continue regardless.

- **Touches:** `src/ngc_cams/recording/manager.py` — check free space before spawning each ffmpeg in `start()`; if below threshold, log a warning and skip (manager already has a `_failed_camera_ids` pattern for similar one-shot opt-outs). Or hold off in `apply_modes()` until free space recovers. Pull the check into a tiny helper for testing (`shutil.disk_usage`).
- **Done when:** Simulating low free space (mock `shutil.disk_usage`) prevents new ffmpeg spawns, and recovering free space resumes recording on the next `apply_modes` tick.

### Out-of-process video player (deferred alternative)
Could keep Qt but isolate libvlc in a separate child process for crash resilience — ODM uses this pattern (`odm.player.host.exe` separate from the main WPF app). Defer unless the web pivot stalls; web naturally provides the same isolation (browser is the "player host").

### PTZ controls
For cameras with `ptz_enabled=True`, surface a directional pad (up / down / left / right / zoom in / zoom out / stop) on the camera detail page. Buttons POST to `/cameras/{id}/ptz/{direction}` and `/cameras/{id}/ptz/stop`; the ONVIF call itself stays in `src/ngc_cams/onvif/ptz.py` (UI-agnostic).

- **Touches:** new `src/ngc_cams/onvif/ptz.py` (wraps `ContinuousMove` / `Stop`, accepts an injected ONVIF service factory for tests), new PTZ route in `src/ngc_cams_web/routes/`, PTZ controls block in `templates/camera_detail.html` rendered only when `camera.ptz_enabled`, tests for the service wrapper with a fake ONVIF.
- **Open questions:** Step-based vs. continuous moves? Start with continuous-while-button-pressed and Stop on release; keyboard-arrow support is YAGNI for round 1.
- **Done when:** With a PTZ-capable camera selected, pressing a direction moves the camera; releasing stops it; cameras without PTZ don't see the controls.

### Grid view of multiple cameras
A CSS grid of `<img src="/cameras/N/live.mjpg">` elements showing every camera at once; clicking a cell promotes it to the single-camera detail page.

- **Touches:** new `GET /grid` route + template; cap at 8 cells (PRD limit) and warn if more cameras than cells.
- **Open questions:** 2×2 default scaling up to 3×3? Browser tab close releases the MJPEG fetches automatically (no manual teardown).
- **Done when:** `/grid` renders every active camera's MJPEG feed side-by-side; clicking a tile navigates to that camera's detail page.

---

## In Progress

_empty_

---

## Done

- **2026-05-17** — Concurrency hardening: per-connection `threading.RLock` around every `CameraRepository` / `SegmentRepository` method. New `ngc_cams.db.lock_for(connection)` returns the same `RLock` for every caller sharing one connection; the registry is a module-level dict keyed by `id(connection)` because `sqlite3.Connection` is a C type that doesn't accept attribute assignment. Concurrency regression tests hammer 8 threads × 20 record-mode toggles and 6 threads × 25 segment inserts with no exceptions and exact final counts. 85/85 tests, ruff clean.
- **2026-05-17** — Surface poller failures in the log. Replaced the bare `pass` on `recording_manager.poll()` / `stop_all()` failures with `logger.exception("recording poll tick failed")` and `... stop_all failed` so uvicorn's stderr captures the traceback. Regression test wires a `_FlakyRecordingManager` that raises on tick 1, asserts the message is logged with `exc_info`, and that the poller keeps ticking. 80/80 tests, ruff clean.
- **2026-05-17** — Retention pruning in the lifespan. `SegmentRepository.delete_older_than` + new `ngc_cams.recording.retention.prune_all` use each camera's `retention_days` to remove old `recording_segments` rows and unlink the matching `.mp4` files. Wired into the FastAPI lifespan on a 5-minute cadence next to the existing 1-s recording-manager poller. 79/79 tests, ruff clean.
- **2026-05-17** — FastAPI + HTMX web UI pivot replacing Qt. `ngc-cams-web` console entry boots uvicorn on 127.0.0.1:8000 with cameras CRUD (add/delete/toggle-record/detail), MJPEG live view (`/cameras/{id}/live.mjpg`), HTMX-driven discovery, and a `RecordingManager.poll()` lifespan. Qt UI + PyQt6/python-vlc deps removed.
- **2026-05-16** — Cameras CRUD + manual Discover (Phases A-E from `docs/plans/2026-05-16-ui-wireup.md`). 25/25 tests, ruff clean.
- **2026-05-17** — Live view (libvlc embedded in Qt) + auto-discovery on launch + native-HWND fix. Verified visually with camera 57 streaming into the viewer.
- **2026-05-17** — Auto-resolve RTSP for discovered devices via anonymous `get_stream_uris`. Discovered tab now shows Main RTSP and exposes Play / double-click to stream without going through Add. 27/27 tests, headless boot resolved 1 LAN camera on launch.
- **2026-05-17** — Snapshot button wired to libvlc `video_take_snapshot`; JPGs land at `D:\ngc-cams-snapshots\<safe-camera-dir>\<timestamp>.jpg`. Verified visually: `Left-Rotate\2026-05-17_06-15-47.jpg` (4.4 MB) on disk. 29/29 tests.
- **2026-05-17** — Silenced live555 buffer-overflow warnings. Bumped `--rtsp-frame-buffer-size=2000000` on the libvlc Instance and capture fd 2 into `D:\ngc-cams-recordings\logs\vlc-stderr.log` (rotates to `.old` at 5 MB) so anything that still slips through stays out of the console. 37/37 tests, ruff clean.
- **2026-05-17** — Record button + continuous-recording manager. `RecordingManager` spawns one ffmpeg per camera with `record_mode != off`, reconciles via `apply_modes`, tails ffmpeg's CSV segment list and inserts rows into `recording_segments`, and restarts crashed processes after a 5 s backoff. ViewerPanel Record button toggles `record_mode` between OFF and VIDEO_ONLY. 54/54 tests, ruff clean.
