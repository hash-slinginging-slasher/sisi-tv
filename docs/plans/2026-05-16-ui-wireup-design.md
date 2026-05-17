# UI Wire-up Design — Cameras CRUD + Discovery

**Date:** 2026-05-16
**Scope:** Replace the static `MainWindow` placeholders with a working Cameras CRUD flow and a Discovery flow against the existing `CameraRepository` and `DiscoveryService`. No streaming, no recording start/stop — those remain placeholders for a later round.

## Goals

- Cameras table reflects `cameras` rows from SQLite on launch and after every change.
- Add / Edit / Delete actually mutate the DB and refresh the table.
- Discover button runs WS-Discovery without freezing the UI and lists results.
- Discovered → Add opens the Add dialog with the device IP pre-filled.

## Non-goals

- Auto-resolving RTSP URLs via `get_stream_uris()` from the Discover flow (user types the URL themselves).
- Live view, snapshot, record, playback, grid, PTZ controls.
- Settings tab editing — it stays read-only labels.
- Migrations beyond the existing `db.initialize()` schema.

## Architecture

**Constructor injection.** `app.main()` is the composition root: it builds the connection, repo, and discovery service, then hands them to `MainWindow`. Widgets and dialogs never reach for the DB themselves. This matches the existing test seam in `DiscoveryService(wsdiscovery_class=...)`.

```
app.main()
  └── connect(db_path) → initialize() → CameraRepository
      DiscoveryService()
      MainWindow(repo, discovery)
          ├── CamerasTab(repo)
          │     ├── refresh()  ← repo.list()
          │     └── opens CameraDialog for Add/Edit
          └── DiscoveredTab(discovery, on_add=lambda d: open_add_dialog(prefill_ip=d.address))
                └── DiscoveryWorker(QThread) → emits results back to UI thread
```

### New / changed modules

- `ngc_cams.config.AppConfig` — add `db_path: Path = Path(r"D:\ngc-cams-recordings\ngc-cams.sqlite3")`. Keeps the PRD's `D:\` convention and matches the DB already on disk.
- `ngc_cams.app.main()` — open DB, build repo + discovery, pass into `MainWindow`.
- `ngc_cams.ui.main_window.MainWindow` — accept `repo` and `discovery` in `__init__`, delegate tabs to dedicated widget classes.
- `ngc_cams.ui.cameras_tab.CamerasTab` *(new)* — owns the table + Add/Edit/Delete buttons, holds the repo, calls `refresh()` after each mutation.
- `ngc_cams.ui.camera_dialog.CameraDialog` *(new)* — single dialog used for both Add and Edit. Constructed with an optional `Camera` (None = Add mode) and optional `prefill_ip` (used by Discover → Add to fill the RTSP URL field with `rtsp://<ip>/`). Returns a `Camera` instance on accept.
- `ngc_cams.ui.discovered_tab.DiscoveredTab` *(new)* — table of discovered devices, Discover button, per-row Add. Owns a `DiscoveryWorker` instance per click.
- `ngc_cams.ui.discovery_worker.DiscoveryWorker` *(new)* — `QThread` subclass that calls `discovery.discover(timeout=5)` and emits `finished(list[DiscoveredCamera])` or `failed(str)`.

### Data flow

- **Launch:** `app.main()` → DB connects/inits → `MainWindow` constructed with repo → `CamerasTab.refresh()` populates table from `repo.list()`.
- **Add:** Add button → `CameraDialog(parent=self)` → on `Accepted` → `repo.add(camera)` → `refresh()`.
- **Edit:** select row → Edit → `CameraDialog(parent=self, camera=stored)` → on `Accepted` → `repo.update(stored.id, camera)` → `refresh()`.
- **Delete:** select row → Delete → `QMessageBox.question` confirm → `repo.delete(id)` → `refresh()`.
- **Discover:** Discover button → button disabled, spinner-ish "Discovering..." label → `DiscoveryWorker.start()` → on `finished` signal, populate Discovered table on UI thread, re-enable button. On `failed`, show a `QMessageBox.warning` with the error string.
- **Discover → Add:** select discovered row → Add → `CameraDialog(parent=self, prefill_ip=discovered.address)` → falls through into the normal Add path on accept.

### Error handling

- DB errors on add/update/delete: catch `sqlite3.Error`, show `QMessageBox.critical` with the message, do not refresh on failure (preserves user's form via re-opening dialog is out of scope — they can retry).
- Discovery errors: any exception inside the worker is caught and re-emitted as `failed(str(exc))`. The UI shows a warning box.
- Invalid form input (empty name or empty RTSP URL): dialog's `accept()` validates first; on validation failure, show inline `QLabel` error and don't close.

### Threading

- One rule: the repo is only touched from the Qt main thread. The discovery worker only does ONVIF/WS-Discovery work and emits results — it never touches the repo or widgets.

### Testing

Existing tests stay green. New tests, all without spinning up `QApplication`:

- `CameraDialog` is structured so the validation and "build `Camera` from current field values" logic lives in a plain method that can be tested by instantiating the dialog under `pytest-qt` *or* — preferred — by extracting `build_camera_from_fields(fields: dict) -> Camera` as a module-level function that the dialog also calls. Test the function directly.
- `DiscoveryWorker.run()` body is delegated to a plain function `run_discovery(discovery, timeout) -> list[DiscoveredCamera]` so it can be tested with a fake `DiscoveryService` that returns a canned list.
- `CamerasTab` row→camera-id mapping: extract a helper `camera_id_for_row(rows: list[StoredCamera], index: int) -> int | None` and unit-test it.

We do **not** add `pytest-qt` as a dependency in this round. UI smoke testing is manual: `python -m ngc_cams`, verify the three rows appear, add a fourth, edit, delete, click Discover.

## Open questions resolved

- DB location: `D:\ngc-cams-recordings\ngc-cams.sqlite3` (kept).
- Discover → Add UX: pre-fill IP only, user types the RTSP URL.

## Out of scope reminders (for the next round)

- Wiring the Settings tab to `AppConfig` so paths and segment length are editable.
- Saving discovered camera resolution (calling `get_stream_uris`) before opening the dialog.
- The actual video viewer and recording controls.
