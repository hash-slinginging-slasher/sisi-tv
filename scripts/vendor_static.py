"""Download CDN dependencies into src/ngc_cams_web/static/.

The kiosk display PC may be on a LAN with no internet, so every asset the
templates pull (Tailwind JIT, HTMX, Material Symbols icon font) is vendored
locally. Re-run this script when you want to refresh to newer versions.

Usage (from repo root, with the dev venv active):
    python scripts/vendor_static.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = REPO_ROOT / "src" / "ngc_cams_web" / "static"
FONTS_DIR = STATIC_DIR / "fonts"

# Use a modern UA so Google Fonts hands us .woff2 (not legacy .ttf).
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
)


def fetch(url: str) -> bytes:
    print(f"  GET {url}")
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=30) as resp:  # noqa: S310 - vetted URLs only
        return resp.read()


def write(path: Path, data: bytes | str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        path.write_text(data, encoding="utf-8")
    else:
        path.write_bytes(data)
    print(f"  wrote {path.relative_to(REPO_ROOT)} ({len(data):,} bytes)")


def vendor_tailwind() -> None:
    print("Tailwind JIT (cdn.tailwindcss.com + forms plugin) ...")
    js = fetch("https://cdn.tailwindcss.com?plugins=forms")
    write(STATIC_DIR / "tailwind.js", js)


def vendor_htmx() -> None:
    print("HTMX 2.0.3 ...")
    js = fetch("https://unpkg.com/htmx.org@2.0.3/dist/htmx.min.js")
    write(STATIC_DIR / "htmx.min.js", js)


def vendor_hls() -> None:
    print("hls.js (HLS live-view player) ...")
    js = fetch("https://cdn.jsdelivr.net/npm/hls.js@1.5.15/dist/hls.min.js")
    write(STATIC_DIR / "hls.min.js", js)


def vendor_material_symbols() -> None:
    print("Material Symbols Outlined (variable font) ...")
    css_url = (
        "https://fonts.googleapis.com/css2"
        "?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1"
        "&display=swap"
    )
    css = fetch(css_url).decode("utf-8")

    # Google's CSS contains @font-face blocks like:
    #     src: url(https://fonts.gstatic.com/.../foo.woff2) format('woff2');
    # We pull each woff2 down, save it, and rewrite the URL to point at our
    # local static/fonts/<name>.woff2.
    url_re = re.compile(r"url\((https://fonts\.gstatic\.com/[^)]+\.woff2)\)")
    matches = url_re.findall(css)
    if not matches:
        raise SystemExit("No .woff2 URLs found in Google Fonts CSS for Material Symbols.")

    rewritten = css
    for i, woff_url in enumerate(dict.fromkeys(matches)):
        # Material Symbols variable font is usually a single file, but the
        # response can contain multiple slices when the font has been split
        # by glyph subset. Number each so they don't collide.
        suffix = "" if i == 0 else f"-{i}"
        local_name = f"material-symbols{suffix}.woff2"
        woff_bytes = fetch(woff_url)
        write(FONTS_DIR / local_name, woff_bytes)
        rewritten = rewritten.replace(woff_url, f"/static/fonts/{local_name}")

    # Prepend a comment so future grep tells you where this came from.
    header = (
        "/* Vendored from Google Fonts via scripts/vendor_static.py. "
        "Do not hand-edit -- re-run the script to refresh. */\n"
    )
    write(FONTS_DIR / "material-symbols.css", header + rewritten)


def main() -> int:
    if not STATIC_DIR.exists():
        STATIC_DIR.mkdir(parents=True)
    print(f"Vendoring into {STATIC_DIR}\n")
    vendor_tailwind()
    print()
    vendor_htmx()
    print()
    vendor_hls()
    print()
    vendor_material_symbols()
    print("\nDone. Update base.html to point at /static/... local paths.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
