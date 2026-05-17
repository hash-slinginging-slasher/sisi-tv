# ONVIF Camera Manager — PRD v0.3

**Status:** Draft
**Owner:** Jodel
**Date:** 2026-05-16
**Codename:** `ngc-cams`

**Changelog**
- v0.3 (2026-05-16): Major scope cut. Cut all ONVIF device-config (time, users, network, log, certs, reboot). Reframed as V380-style personal app: discover → RTSP URL → live view + PTZ + record with audio toggle.
- v0.2: Added lightweight recording, cross-subnet, concurrency 3–8, removed app-level auth.
- v0.1: Initial draft.

---

## 1. Background

ODM is good at one thing: **finding ONVIF cameras on the LAN and surfacing the RTSP URL**. That's the bit we want.

V380 is good at being a **simple personal-grade viewer**: live view, PTZ, record with audio, playback. That's the rest.

Combine the two. Drop everything else.

## 2. Goals

- **ONVIF auto-discovery** → resolve each camera's RTSP URL automatically
- **Manage cameras**: add, edit, delete
- **Live view** (single + small grid)
- **PTZ control** (where supported)
- **Continuous recording with audio enable/disable per camera**
- Portable Windows `.exe`, no installer

## 3. Non-goals

- ONVIF device configuration (time, users, network, system log, certs, reboot, firmware)
- ONVIF events / alarm subscription
- Profile editing (just auto-pick main/sub)
- Motion detection, AI analytics
- Cloud / mobile / web
- Multi-user / RBAC
- Cross-machine sync

## 4. User

Single user (Jodel, personal app).

## 5. Tech Stack

| Layer        | Choice                                | Why                                         |
|--------------|---------------------------------------|---------------------------------------------|
| Language     | Python 3.11+                          | Local-app preference                        |
| UI           | PyQt6                                 | Native, libvlc embed works well             |
| ONVIF        | `onvif-zeep` + `wsdiscovery`          | Discovery + `GetStreamUri` for RTSP         |
| Video render | `python-vlc` (libvlc)                 | Best RTSP latency, hardware decode          |
| Recording    | `ffmpeg` subprocess (segment muxer)   | No re-encode; audio kept/dropped via flags  |
| Storage      | SQLite                                | Cameras, recording index                    |
| Packaging    | PyInstaller                           | Portable `.exe`                             |

## 6. Features

### 6.1 Discovery
- WS-Discovery on UDP 3702 → list ONVIF devices on LAN
- For each discovered device: probe `GetCapabilities` + `GetStreamUri` to resolve RTSP URL (main + sub stream)
- Show in "Discovered" tab with: IP, manufacturer, RTSP URL(s), [+ Add]

### 6.2 Camera Management
Single "Cameras" table:

| Field          | Notes                                          |
|----------------|------------------------------------------------|
| Name           | User-defined ("Front gate")                    |
| RTSP URL       | Auto-filled from discovery, manually editable  |
| Username       | Optional (some cams embed in URL)              |
| Password       | Optional                                       |
| Sub-stream URL | Optional, for grid view                        |
| PTZ enabled    | Bool                                           |
| Record         | Off / Video only / Video + Audio               |

Actions: **Add** (manual or from discovered), **Edit**, **Delete**. Stored in SQLite.

### 6.3 Live View
- **Single view**: click camera → fullscreen-able live stream, PTZ controls overlay (if enabled), snapshot button
- **Grid view**: 2x2 or 3x3 layout, uses sub-stream URLs (auto-fallback to main), double-click tile to expand
- Bottom status bar shows the RTSP URL being played (copy button)

### 6.4 PTZ
- ONVIF PTZ service: pan/tilt/zoom buttons (continuous-move on press, stop on release)
- Speed slider (1–10)
- 4 preset slots: save current position, recall, delete
- No PTZ tab if camera doesn't advertise PTZ service

### 6.5 Recording
- Toggle per camera: **Off** / **Video only** / **Video + Audio**
- Implementation: `ffmpeg -i <rtsp> -c copy -map 0:v [-map 0:a | -an] -f segment -segment_time 600 -reset_timestamps 1 <path>/%Y-%m-%d_%H-%M-%S.mp4`
- "Video only" passes `-an` (drop audio); "Video + Audio" passes `-map 0:a` (include audio if present)
- Segment length: 10 min default (configurable globally)
- Storage path: configurable, default `D:\ngc-cams-recordings\<camera_name>\<YYYY-MM-DD>\`
- Retention: delete segments older than N days (default 7, configurable per camera)
- Disk-space guard: if free < 10 GB, delete oldest first
- Indicator: red dot on camera tile when recording

### 6.6 Playback (minimal)
- Pick camera + date → list segments for that day
- Click segment → play in same viewer with VLC scrub bar
- Snapshot from playback → JPG
- That's it. No timeline scrubbing across days, no clip export in v1.

### 6.7 Snapshot
- One-click JPG from live or playback view → `D:\ngc-cams-snapshots\<camera_name>\<timestamp>.jpg`

## 7. UX Layout

V380-style: list left, viewer right.

```
┌──────────────────────────────────────────────────────────┐
│ [Cameras] [Discovered] [Settings]                        │
├────────────────────┬─────────────────────────────────────┤
│ My Cameras         │ Live View                           │
│ ● Front gate    ●R │                                     │
│ ● Lobby            │                                     │
│ ● Stockroom     ●R │      [   video pane   ]             │
│ ● Carpark          │                                     │
│                    │                                     │
│ [+ Add]            │ ┌─PTZ─┐    [snap] [● rec] [grid]    │
│ [Grid view]        │ │ ↑ ↓ │                             │
│                    │ │ ← → │   rtsp://192.168.1.18/...   │
│                    │ │ +/- │                             │
│                    │ └─────┘                             │
└────────────────────┴─────────────────────────────────────┘
```

Status dots: green=online, gray=offline, red=recording.

## 8. Success Metrics

- Discover ≥95% of ONVIF cameras on LAN within 5 sec
- One-click add from "Discovered" → camera in "My Cameras" with working RTSP URL
- Live latency ≤1.5 sec on LAN
- 8 cameras recording continuously (no re-encode) < 15% CPU on Beelink SER-class mini PC

## 9. Storage Math

At 1 Mbps sub-stream, 8 cameras continuous: ~86 GB/day, ~605 GB / 7 days. 1 TB external disk handles default retention comfortably.

## 10. Roadmap

| Version | Scope                                                              |
|---------|--------------------------------------------------------------------|
| v1.0    | MVP per §6                                                         |
| v1.1    | Scheduled recording windows, motion-trigger (OpenCV frame-diff)    |
| v1.2    | Two-way audio (if supported by camera), clip export                |

## 11. Risks

- **Camera quirks**: cheap ONVIF cams often have wrong RTSP URLs in `GetStreamUri` responses. Mitigation: manual URL edit field on every camera record.
- **Audio in MP4 segments**: not all cameras stream audio; ffmpeg `-map 0:a?` (optional) avoids failure when no audio track present.
- **H.265 in grid**: more CPU. Document: prefer sub-stream H.264 in grid view.
- **ffmpeg RTSP drops**: use `-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -rtsp_transport tcp` for resilience.
- **WS-Discovery firewall**: Windows Defender may block UDP 3702 on first run.

## 12. Implementation Slices

1. **Cameras + Discovery**: SQLite schema, WS-Discovery, GetStreamUri, "Cameras" + "Discovered" tabs, add/edit/delete
2. **Live single-cam**: libvlc embed, snapshot
3. **PTZ overlay**: ONVIF PTZ service, continuous-move, presets
4. **Recording**: ffmpeg subprocess manager, audio toggle, segment index, retention
5. **Grid view**: multi-libvlc tiles using sub-stream URLs
6. **Playback (minimal)**: date picker, segment list, playback in same viewer
7. **Packaging**: PyInstaller portable

## 13. References

- ONVIF Core Spec — `GetStreamUri`, PTZ service
- `onvif-zeep`: <https://github.com/FalkTannhaeuser/python-onvif-zeep>
- `python-vlc`: <https://pypi.org/project/python-vlc/>
- ffmpeg segment muxer + `-rtsp_transport tcp`
- V380 (UX reference, not a code ref)
