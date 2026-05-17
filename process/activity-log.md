## 2026-05-16

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
