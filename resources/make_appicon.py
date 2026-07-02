"""Generate the app-bundle icon (PresenceSync.icns): a rounded tile with the
two-apps glyph. Renders each required size natively, then `iconutil` packs them.

    python resources/make_appicon.py /tmp/preview.png          # single preview
    python resources/make_appicon.py --iconset resources/PresenceSync.iconset
    iconutil -c icns resources/PresenceSync.iconset -o resources/PresenceSync.icns
"""

from __future__ import annotations

import os
import sys

from AppKit import (
    NSBezierPath,
    NSBitmapImageFileTypePNG,
    NSBitmapImageRep,
    NSColor,
    NSDeviceRGBColorSpace,
    NSGradient,
    NSGraphicsContext,
)


def _rect(x, y, w, h):
    return ((float(x), float(y)), (float(w), float(h)))


def _arrow(x_tail, x_tip, y, st, hl, hh):
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


def _draw_glyph(ox, oy, g):
    NSColor.whiteColor().set()
    tw, th = g * 0.23, g * 0.64
    ty = oy + (g - th) / 2
    lx = ox + g * 0.08
    rx = ox + g - g * 0.08 - tw
    r = g * 0.065
    NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(_rect(lx, ty, tw, th), r, r).fill()
    NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(_rect(rx, ty, tw, th), r, r).fill()
    st, hl, hh = g * 0.07, g * 0.115, g * 0.11
    _arrow(ox + g * 0.35, ox + g * 0.65, oy + g * 0.575, st, hl, hh).fill()
    _arrow(ox + g * 0.65, ox + g * 0.35, oy + g * 0.425, st, hl, hh).fill()


def _draw_icon(S):
    inset = S * 0.098
    tw = S - 2 * inset
    r = tw * 0.223
    tile = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(_rect(inset, inset, tw, tw), r, r)
    bottom = NSColor.colorWithSRGBRed_green_blue_alpha_(0.20, 0.28, 0.72, 1.0)
    top = NSColor.colorWithSRGBRed_green_blue_alpha_(0.36, 0.50, 1.0, 1.0)
    NSGradient.alloc().initWithStartingColor_endingColor_(bottom, top).drawInBezierPath_angle_(tile, 90.0)
    g = tw * 0.82
    origin = inset + (tw - g) / 2
    _draw_glyph(origin, origin, g)


def render_png(S: int) -> bytes:
    rep = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, S, S, 8, 4, True, False, NSDeviceRGBColorSpace, 0, 0
    )
    ctx = NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.setCurrentContext_(ctx)
    _draw_icon(S)
    NSGraphicsContext.restoreGraphicsState()
    return rep.representationUsingType_properties_(NSBitmapImageFileTypePNG, {})


_MAP = {
    16: ["icon_16x16.png"],
    32: ["icon_16x16@2x.png", "icon_32x32.png"],
    64: ["icon_32x32@2x.png"],
    128: ["icon_128x128.png"],
    256: ["icon_128x128@2x.png", "icon_256x256.png"],
    512: ["icon_256x256@2x.png", "icon_512x512.png"],
    1024: ["icon_512x512@2x.png"],
}


def write_iconset(directory: str) -> None:
    os.makedirs(directory, exist_ok=True)
    for size, names in _MAP.items():
        data = render_png(size)
        for name in names:
            data.writeToFile_atomically_(os.path.join(directory, name), True)
    print("wrote iconset:", directory)


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--iconset":
        write_iconset(sys.argv[2])
    else:
        out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/ps-appicon.png"
        render_png(512).writeToFile_atomically_(out, True)
        print("wrote preview:", out)
