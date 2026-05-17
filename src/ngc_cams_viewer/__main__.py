"""Entry point for the SISI-TV fullscreen viewer (`sisi-tv-viewer`).

Behavior at login:
  1. Resolve the URL (CLI arg, or default to local /grid based on AppConfig).
  2. Poll the URL until the server responds (server may still be booting via
     the SISI-TV.lnk Startup shortcut).
  3. Open a frameless fullscreen pywebview window on Edge WebView2.

ESC exits fullscreen the same way as any kiosk; Alt+F4 closes the window.
"""

from __future__ import annotations

import argparse
import sys
import time
import urllib.error
import urllib.request

import webview

from ngc_cams.config import AppConfig


def _default_url() -> str:
    config = AppConfig.from_settings()
    host = config.bind_host
    # 0.0.0.0 / :: are bind sentinels, not routable destinations. Localhost is
    # the right target when server + viewer share the same machine (the GMKtec
    # kiosk case); for a remote display, pass the URL as a CLI arg in the
    # shortcut.
    if host in ("0.0.0.0", "::", ""):
        host = "127.0.0.1"
    return f"http://{host}:{config.bind_port}/grid"


def wait_for_server(url: str, timeout_seconds: float = 60.0, interval: float = 1.0) -> bool:
    """Poll `url` until it answers (any HTTP status counts as up) or we time out."""
    deadline = time.monotonic() + timeout_seconds
    last_error: str | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2):  # noqa: S310 - local URL
                return True
        except urllib.error.HTTPError:
            # Server responded with an error code -- still "up" from our POV.
            return True
        except (urllib.error.URLError, OSError) as exc:
            last_error = str(exc)
            time.sleep(interval)
    print(
        f"[sisi-tv-viewer] server at {url} not reachable after {timeout_seconds:.0f}s: "
        f"{last_error}",
        file=sys.stderr,
    )
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sisi-tv-viewer",
        description="Fullscreen kiosk viewer for the SISI-TV /grid page.",
    )
    parser.add_argument(
        "url",
        nargs="?",
        default=None,
        help="Target URL (default: derived from AppConfig, http://<bind_host>:<bind_port>/grid).",
    )
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help="Skip polling the server before opening the window.",
    )
    parser.add_argument(
        "--windowed",
        action="store_true",
        help="Open windowed (1280x800) instead of fullscreen -- useful for debugging.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="How long to wait for the server in seconds (default: 60).",
    )
    args = parser.parse_args(argv)

    url = args.url or _default_url()

    if not args.no_wait:
        wait_for_server(url, timeout_seconds=args.timeout)

    webview.create_window(
        title="SISI-TV",
        url=url,
        fullscreen=not args.windowed,
        frameless=not args.windowed,
        background_color="#000000",
        width=1280,
        height=800,
        confirm_close=False,
    )
    webview.start()
    return 0


if __name__ == "__main__":
    sys.exit(main())
