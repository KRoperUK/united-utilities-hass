#!/usr/bin/env python3
"""Generate the in-repo brand assets HACS and Home Assistant look for.

home-assistant/brands no longer accepts custom components, so
``custom_components/<domain>/brand/`` is the only route. The mark is a plain
water droplet in a rounded square, drawn here from scratch. It deliberately
does not reuse United Utilities' logo or identity: this is an unofficial project.

Usage (Pillow ships with Home Assistant, so the dev venv already has it):

    python scripts/make_brand_assets.py
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BRAND_DIR = Path("custom_components/united_utilities/brand")
SCALE = 4  # supersample, then downscale for anti-aliasing

LIGHT = {"tile": (0, 114, 188, 255), "drop": (255, 255, 255, 255), "text": (33, 33, 33, 255)}
DARK = {"tile": (64, 164, 230, 255), "drop": (255, 255, 255, 255), "text": (235, 235, 235, 255)}


def _droplet(size: int) -> list[tuple[float, float]]:
    """Points of a droplet in a ``size`` box: a circle joined to a tip above it by tangents."""
    cx, cy, r = size / 2, size * 0.60, size * 0.24
    tip_y = size * 0.16
    # Angle (from straight up, clockwise) of the tangent points: cos(theta) = r / distance-to-tip.
    theta = math.acos(r / (cy - tip_y))
    steps = 96
    arc = [
        (cx + r * math.sin(phi), cy - r * math.cos(phi))
        for phi in (theta + (2 * math.pi - 2 * theta) * i / steps for i in range(steps + 1))
    ]
    return [(cx, tip_y), *arc]


def _icon(px: int, palette: dict[str, tuple[int, int, int, int]]) -> Image.Image:
    big = px * SCALE
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((0, 0, big - 1, big - 1), radius=big // 5, fill=palette["tile"])
    draw.polygon(_droplet(big), fill=palette["drop"])
    return img.resize((px, px), Image.Resampling.LANCZOS)


def _logo(height: int, palette: dict[str, tuple[int, int, int, int]]) -> Image.Image:
    width = height * 2
    big_w, big_h = width * SCALE, height * SCALE
    img = Image.new("RGBA", (big_w, big_h), (0, 0, 0, 0))
    icon = _icon(int(big_h * 0.8), palette)
    pad = (big_h - icon.height) // 2
    img.alpha_composite(icon, (pad, pad))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=big_h * 0.2)
    text_x = pad * 2 + icon.width
    draw.text((text_x, big_h * 0.30), "United", font=font, fill=palette["text"])
    draw.text((text_x, big_h * 0.52), "Utilities", font=font, fill=palette["text"])
    return img.resize((width, height), Image.Resampling.LANCZOS)


def main() -> None:
    BRAND_DIR.mkdir(parents=True, exist_ok=True)
    for prefix, palette in (("", LIGHT), ("dark_", DARK)):
        _icon(256, palette).save(BRAND_DIR / f"{prefix}icon.png")
        _icon(512, palette).save(BRAND_DIR / f"{prefix}icon@2x.png")
        _logo(256, palette).save(BRAND_DIR / f"{prefix}logo.png")
        _logo(512, palette).save(BRAND_DIR / f"{prefix}logo@2x.png")
    print(f"wrote brand assets to {BRAND_DIR}")


if __name__ == "__main__":
    main()
