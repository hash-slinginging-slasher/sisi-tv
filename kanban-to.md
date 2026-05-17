# ngc-cams Kanban

Source of truth for what's next on the personal-app roadmap. Move cards across columns as work progresses. Update dates in `## Done` so the audit trail matches `process/activity-log.md`.

---

## Backlog

### Retention pruning task in the lifespan poller
`Camera.retention_days` is stored on every camera (default 7) but nothing actually deletes old `.mp4` segments — disk usage will grow forever. Wire pruning into the existing poller lifespan in `src/ngc_cams_web/composition.py`.

- **Touches:** new `src/ngc_cams/recording/retention.py` (pure function: given `recording_root`, `retention_days`, and a clock, returns the list of segment paths older than the cutoff and a list of `recording_segments` rows to delete). Call it from the poller on a slower cadence than the 1 s ffmpeg poll (every 5 min is plenty). DB cleanup via `SegmentRepository.delete_older_than(camera_id, cutoff)` (new method). `AppConfig.disk_guard_free_gb` should also factor in — pause new segment writes if disk is below threshold.
- **Open questions:** Per-camera `retention_days` vs. global override? PRD says per-camera. Should retention also remove the empty date directories left behind, or leave them?
- **Done when:** After 8 days of recording, segments older than 7 days are gone from disk and `recording_segments` table; new segments still land normally.

### Concurrency hardening: lock around `CameraRepository` / `SegmentRepository` writes
`ngc_cams.db.connect()` sets `check_same_thread=False` to make Starlette's threadpool dispatch work, but the shared `sqlite3.Connection` is now mutated from multiple threads (route handlers in the threadpool, poller on the event-loop thread, `RecordingManager._ingest_new_segments` from the segment-list reader). SQLite serializes individual statements, but read-modify-write patterns like `CameraRepository.update` (which does `execute(UPDATE)` then `get()`) are not atomic across calls. Concrete failure: two simultaneous record-toggles can interleave and one writer reads the other's mid-flight state.

- **Touches:** `src/ngc_cams/cameras.py` and `src/ngc_cams/segments.py` — wrap multi-statement methods in a shared `threading.RLock` (one lock per `Connection`). Alternative: per-request connection from a pool, but that complicates the recording manager which holds a long-lived handle. Stick with the lock for round 1.
- **Done when:** A regression test hammers `POST /cameras/{id}/record` from a threadpool while the poller runs concurrent `apply_modes`, with zero `database is locked` or stale-read failures over a 5 s loop.

### Surface poller failures in the log
`composition.py:28` and `:43` swallow every `Exception` from `recording_manager.poll()` and `stop_all()` with bare `pass`. If `apply_modes` starts raising in production (e.g. `find_ffmpeg_executable` returns None after an uninstall, or `_ingest_new_segments` hits a corrupt CSV), nothing will surface — the recording silently stops and the user has to notice via missing files. Replace `pass` with `logger.exception("recording poll tick failed")` so uvicorn's stderr captures the traceback. Same fix for `stop_all`.

- **Touches:** `src/ngc_cams_web/composition.py` — add `import logging` and `logger = logging.getLogger(__name__)`; replace the two `pass` lines.
- **Done when:** Inducing a deliberate raise in `poll()` (e.g. monkey-patching for one tick) shows a full traceback in the uvicorn console output; the poller still continues on the next tick.

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

- **2026-05-17** — FastAPI + HTMX web UI pivot replacing Qt. `ngc-cams-web` console entry boots uvicorn on 127.0.0.1:8000 with cameras CRUD (add/delete/toggle-record/detail), MJPEG live view (`/cameras/{id}/live.mjpg`), HTMX-driven discovery, and a `RecordingManager.poll()` lifespan. Qt UI + PyQt6/python-vlc deps removed.
- **2026-05-16** — Cameras CRUD + manual Discover (Phases A-E from `docs/plans/2026-05-16-ui-wireup.md`). 25/25 tests, ruff clean.
- **2026-05-17** — Live view (libvlc embedded in Qt) + auto-discovery on launch + native-HWND fix. Verified visually with camera 57 streaming into the viewer.
- **2026-05-17** — Auto-resolve RTSP for discovered devices via anonymous `get_stream_uris`. Discovered tab now shows Main RTSP and exposes Play / double-click to stream without going through Add. 27/27 tests, headless boot resolved 1 LAN camera on launch.
- **2026-05-17** — Snapshot button wired to libvlc `video_take_snapshot`; JPGs land at `D:\ngc-cams-snapshots\<safe-camera-dir>\<timestamp>.jpg`. Verified visually: `Left-Rotate\2026-05-17_06-15-47.jpg` (4.4 MB) on disk. 29/29 tests.
- **2026-05-17** — Silenced live555 buffer-overflow warnings. Bumped `--rtsp-frame-buffer-size=2000000` on the libvlc Instance and capture fd 2 into `D:\ngc-cams-recordings\logs\vlc-stderr.log` (rotates to `.old` at 5 MB) so anything that still slips through stays out of the console. 37/37 tests, ruff clean.
- **2026-05-17** — Record button + continuous-recording manager. `RecordingManager` spawns one ffmpeg per camera with `record_mode != off`, reconciles via `apply_modes`, tails ffmpeg's CSV segment list and inserts rows into `recording_segments`, and restarts crashed processes after a 5 s backoff. ViewerPanel Record button toggles `record_mode` between OFF and VIDEO_ONLY. 54/54 tests, ruff clean.
