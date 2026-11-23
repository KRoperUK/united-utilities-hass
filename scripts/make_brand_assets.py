#!/usr/bin/env python3
"""Generate the in-repo brand images Home Assistant and HACS look for.

Sources are the SVGs in ``scripts/brand_src/``. They were converted from the
vector logo (``res/drawable/ic_logo.xml``) in the United Utilities Android app:
the full logo for ``logo``, and just its "U" symbol for ``icon``. The light
versions use the brand green from the app (``#0c4d42``, its launcher
background); the ``dark_`` versions are white, as the app ships them.

Output follows the home-assistant/brands image specification: PNG with
transparency, trimmed to the artwork, icons square at 256 and 512 px, and logos
with their shortest side at the 256 / 512 px maximum.

Usage (needs ``rsvg-convert``: ``brew install librsvg``; Pillow ships with HA):

    python scripts/make_brand_assets.py
"""

from __future__ import annotations

import io
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image

SRC_DIR = Path("scripts/brand_src")
BRAND_DIR = Path("custom_components/united_utilities/brand")
RENDER_HEIGHT = 2048  # render large, trim, then downscale for clean edges


def _render_trimmed(svg: Path) -> Image.Image:
    png = subprocess.run(
        ["rsvg-convert", "--height", str(RENDER_HEIGHT), str(svg)],
        check=True,
        capture_output=True,
    ).stdout
    image = Image.open(io.BytesIO(png)).convert("RGBA")
    bbox = image.getchannel("A").getbbox()
    if bbox is None:
        raise SystemExit(f"{svg} rendered empty")
    return image.crop(bbox)


def _icon(art: Image.Image, size: int) -> Image.Image:
    """Square canvas with the artwork fitted edge to edge on its longer side."""
    scale = size / max(art.size)
    fitted = art.resize((round(art.width * scale), round(art.height * scale)), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.alpha_composite(fitted, ((size - fitted.width) // 2, (size - fitted.height) // 2))
    return canvas


def _logo(art: Image.Image, shortest: int) -> Image.Image:
    """Trimmed logo with its shortest side at ``shortest`` pixels."""
    scale = shortest / min(art.size)
    return art.resize((round(art.width * scale), round(art.height * scale)), Image.Resampling.LANCZOS)


def main() -> None:
    if shutil.which("rsvg-convert") is None:
        sys.exit("rsvg-convert not found; install librsvg (brew install librsvg)")
    BRAND_DIR.mkdir(parents=True, exist_ok=True)
    for prefix in ("", "dark_"):
        icon = _render_trimmed(SRC_DIR / f"{prefix}icon.svg")
        logo = _render_trimmed(SRC_DIR / f"{prefix}logo.svg")
        outputs = {
            f"{prefix}icon.png": _icon(icon, 256),
            f"{prefix}icon@2x.png": _icon(icon, 512),
            f"{prefix}logo.png": _logo(logo, 256),
            f"{prefix}logo@2x.png": _logo(logo, 512),
        }
        for name, image in outputs.items():
            image.save(BRAND_DIR / name, optimize=True)
            print(f"{name}: {image.width}x{image.height}")


if __name__ == "__main__":
    main()
