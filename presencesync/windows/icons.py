"""Tray icon rendering with PIL: white two-tiles glyph, coloured dot on alert."""

from __future__ import annotations

from PIL import Image, ImageDraw

from ..core.health import HealthState

_DOT = {
    HealthState.WARNING: (255, 189, 0, 255),
    HealthState.ERROR: (255, 69, 58, 255),
}
_WHITE = (255, 255, 255, 255)


def _draw_glyph(draw: ImageDraw.ImageDraw, c: int) -> None:
    tw, th = c * 0.23, c * 0.64
    ty = (c - th) / 2
    r = c * 0.065
    for x in (c * 0.08, c - c * 0.08 - tw):
        draw.rounded_rectangle([x, ty, x + tw, ty + th], radius=r, fill=_WHITE)

    st, hl, hh = c * 0.07, c * 0.115, c * 0.11
    for y, x0, x1 in ((c * 0.425, c * 0.35, c * 0.65), (c * 0.575, c * 0.65, c * 0.35)):
        d = 1 if x1 > x0 else -1
        hx = x1 - d * hl
        draw.line([x0, y, hx, y], fill=_WHITE, width=max(1, round(st)))
        draw.polygon([(x1, y), (hx, y - hh), (hx, y + hh)], fill=_WHITE)


def make_image(state: HealthState, size: int = 64) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    _draw_glyph(draw, size)
    if state in _DOT:
        d = size * 0.40
        ring = size * 0.08
        x0, y0 = size - d, size - d
        draw.ellipse([x0 - ring, y0 - ring, size + ring, size + ring], fill=(0, 0, 0, 0))
        draw.ellipse([x0, y0, size, size], fill=_DOT[state])
    return img
