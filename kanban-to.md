# ngc-cams Kanban

Source of truth for what's next on the personal-app roadmap. Move cards across columns as work progresses. Update dates in `## Done` so the audit trail matches `process/activity-log.md`.

---

## Backlog

- **Phase 1 — Tailscale for mobile/family access (no code).** Install Tailscale on the GMKtec (`winget install Tailscale.Tailscale`) and on each family member's phone. Set `bind_host = 0.0.0.0` in Settings so SISI-TV listens on the Tailscale interface. Family hits `http://gmktec:8000/grid` from anywhere — no public exposure, no port forwarding. Free Personal tier covers it. Document the setup steps in `README.md` after verifying on at least one phone.
- **Phase 2 — Simple app login (defense in depth).** Single password set in Settings, stored as `bcrypt` hash in `~/.ngc-cams/settings.json`. New FastAPI middleware checks a signed session cookie on every route except `/login`, `/static/*`, `/healthz`. `/login` template renders a single password field, sets the cookie on success. Session secret auto-generated on first run and persisted. ~80 lines of code + one template.
- **Phase 3 — Signed time-limited share links (the practical "share to Discord/Slack" answer).** "Share" button on `/camera/{id}` opens a modal that generates an HMAC-signed URL like `/share/<token>?ttl=4h`, valid for one camera for N hours. Login-bypass for that one camera only. User copy-pastes the URL into Discord/Slack the normal way; family member taps it on their phone and the link dies on its own. Avoids the full Slack-app / Discord-bot setup pain while delivering the same outcome.
- **Phase 4 (deferred, only if Phase 3 isn't enough) — Real Slack/Discord slash command.** `/sisi <camera>` in chat returns an ephemeral signed share link. Requires Slack Socket Mode (or Discord Gateway bot) so the server doesn't need a public webhook — it connects outbound from the GMKtec. Bot token + app config + verification. Large effort relative to value once Phase 3 ships; revisit only if family actively asks for it.

---

## In Progress

_empty_

---

## Done

- **2026-05-17** — Grid view at `GET /grid`. Responsive CSS grid of `<img src="/cameras/N/live.mjpg">` wrapped in `<a href="/cameras/N">` so clicking promotes to the detail page. Capped at 8 cells per PRD; if more cameras exist the page shows a "Showing 8 of N (capped at 8)" notice. Each tile shows the camera name and a `REC` badge when `record_mode != off`. Index page now has a "View grid →" link. 4 new tests, 114/114, ruff clean.
- **2026-05-17** — Closed: "Out-of-process video player (deferred alternative)" — the web pivot supplies the same crash-isolation (browser is the "player host"), the card was explicitly deferred to this case.
- **2026-05-17** — PTZ controls. New `ngc_cams.onvif.ptz.PTZService` wraps ONVIF `ContinuousMove` / `Stop` with an injectable `onvif_factory` for tests; covers up/down/left/right/zoom_in/zoom_out via a fixed velocity table. `POST /cameras/{id}/ptz/{direction}` + `POST /cameras/{id}/ptz/stop` routes drive it (404 unknown camera, 409 PTZ-disabled, 422 bad direction, 502 ONVIF error). `camera_detail.html` renders a 3x3 directional pad with mousedown/touchstart → move and mouseup/mouseleave/touchend → stop. Add-camera form gained a PTZ checkbox. 21 new tests, 110/110, ruff clean.
- **2026-05-17** — Disk guard wired into `RecordingManager.start()`. New `disk_guard_free_gb` + `disk_usage_fn` ctor args; `__main__.py` passes `config.disk_guard_free_gb`. When free space drops below the threshold, `start()` skips the ffmpeg spawn (transient — *not* added to `_failed_camera_ids`) and logs a one-shot warning; when disk recovers, logs a recovery info line and resumes. Five new tests cover low-disk block, log-once behaviour, recovery resume, guard-disabled, and fail-open on `shutil.disk_usage` errors. 90/90 tests, ruff clean.
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
