"""Menu-bar icon rendering: template glyph when healthy, coloured dot on alert."""

from __future__ import annotations

import os

from AppKit import (
    NSBezierPath,
    NSBitmapImageFileTypePNG,
    NSBitmapImageRep,
    NSColor,
    NSCompositingOperationDestinationOut,
    NSCompositingOperationSourceOver,
    NSGraphicsContext,
    NSImage,
)

from ..core.health import HealthState

_DOT = {
    HealthState.WARNING: (1.00, 0.74, 0.00),  # amber
    HealthState.ERROR: (1.00, 0.27, 0.23),    # red
}


def _rect(x, y, w, h):
    return ((float(x), float(y)), (float(w), float(h)))


def _arrow(x_tail, x_tip, y, st, hl, hh):
    """A filled arrow from x_tail to x_tip at height y (direction inferred)."""
    d = 1.0 if x_tip > x_tail else -1.0
    hx = x_tip - d * hl
    p = NSBezierPath.bezierPath()
    p.moveToPoint_((x_tail, y + st / 2))
    p.lineToPoint_((hx, y + st / 2))
    p.lineToPoint_((hx, y + hh))
    p.lineToPoint_((x_tip, y))
    p.lineToPoint_((hx, y - hh))
    p.lineToPoint_((hx, y - st / 2))
    p.lineToPoint_((x_tail, y - st / 2))
    p.closePath()
    return p


def _draw_two_apps(C: float) -> None:
    """Draw the glyph (two tiles + exchange arrows) with the current fill colour."""
    tw, th = C * 0.23, C * 0.64
    ty = (C - th) / 2.0
    lx, rx = C * 0.08, C - C * 0.08 - tw
    r = C * 0.065
    NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(_rect(lx, ty, tw, th), r, r).fill()
    NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(_rect(rx, ty, tw, th), r, r).fill()
    st, hl, hh = C * 0.07, C * 0.115, C * 0.11
    _arrow(C * 0.35, C * 0.65, C * 0.575, st, hl, hh).fill()  # top → right
    _arrow(C * 0.65, C * 0.35, C * 0.425, st, hl, hh).fill()  # bottom → left


def _draw_dot(C: float, rgb) -> None:
    d = C * 0.40
    dx, dy = C - d, 0.0
    ring = C * 0.08
    ctx = NSGraphicsContext.currentContext()
    ctx.saveGraphicsState()
    ctx.setCompositingOperation_(NSCompositingOperationDestinationOut)
    NSColor.blackColor().set()
    NSBezierPath.bezierPathWithOvalInRect_(_rect(dx - ring, dy - ring, d + 2 * ring, d + 2 * ring)).fill()
    ctx.restoreGraphicsState()
    NSColor.colorWithSRGBRed_green_blue_alpha_(rgb[0], rgb[1], rgb[2], 1.0).set()
    NSBezierPath.bezierPathWithOvalInRect_(_rect(dx, dy, d, d)).fill()


def _render(C: int, glyph_color, dot_rgb=None) -> NSImage:
    img = NSImage.alloc().initWithSize_((C, C))
    img.lockFocus()
    glyph_color.set()
    _draw_two_apps(C)
    if dot_rgb is not None:
        _draw_dot(C, dot_rgb)
    img.unlockFocus()
    return img


def _png(img: NSImage) -> bytes:
    rep = NSBitmapImageRep.imageRepWithData_(img.TIFFRepresentation())
    return rep.representationUsingType_properties_(NSBitmapImageFileTypePNG, {})


def ensure_icons(directory: str, canvas: int = 44) -> dict:
    """Render the three menu-bar images; return paths keyed by 'template' / state."""
    os.makedirs(directory, exist_ok=True)
    paths = {}
    specs = {
        "template": (NSColor.blackColor(), None),  # OK — marked template, system-tinted
        HealthState.WARNING: (NSColor.whiteColor(), _DOT[HealthState.WARNING]),
        HealthState.ERROR: (NSColor.whiteColor(), _DOT[HealthState.ERROR]),
    }
    for key, (color, dot) in specs.items():
        name = key if isinstance(key, str) else key.value
        path = os.path.join(directory, f"icon_{name}.png")
        _png(_render(canvas, color, dot)).writeToFile_atomically_(path, True)
        paths[key] = path
    return paths


# Preview (dev only)
def _dump_preview(path: str, cell: int = 96) -> None:
    cells = [
        ((0.93, 0.93, 0.94), NSColor.blackColor(), None),                       # light bar, tinted black
        ((0.13, 0.13, 0.14), NSColor.whiteColor(), None),                       # dark bar, tinted white
        ((0.13, 0.13, 0.14), NSColor.whiteColor(), _DOT[HealthState.WARNING]),  # warning
        ((0.13, 0.13, 0.14), NSColor.whiteColor(), _DOT[HealthState.ERROR]),    # error
    ]
    canvas = NSImage.alloc().initWithSize_((cell * len(cells), cell))
    canvas.lockFocus()
    for i, (bg, color, dot) in enumerate(cells):
        x = i * cell
        NSColor.colorWithSRGBRed_green_blue_alpha_(bg[0], bg[1], bg[2], 1.0).set()
        NSBezierPath.bezierPathWithRect_(_rect(x, 0, cell, cell)).fill()
        icon = _render(cell, color, dot)
        inset = cell * 0.12
        icon.drawInRect_fromRect_operation_fraction_(
            _rect(x + inset, inset, cell - 2 * inset, cell - 2 * inset),
            _rect(0, 0, cell, cell),
            NSCompositingOperationSourceOver,
            1.0,
        )
    canvas.unlockFocus()
    _png(canvas).writeToFile_atomically_(path, True)
    print(f"wrote {path}")


if __name__ == "__main__":
    import sys

    _dump_preview(sys.argv[1] if len(sys.argv) > 1 else "/tmp/presencesync-twoapps.png")
