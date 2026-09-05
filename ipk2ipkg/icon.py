"""Generate PNG/ICO icons without third-party libraries."""

from __future__ import annotations

import struct
import zlib

# 5x7 bitmap font for A-Z, 0-9, hyphen
_FONT: dict[str, list[str]] = {
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "B": ["11110", "10001", "11110", "10001", "10001", "10001", "11110"],
    "C": ["01110", "10001", "10000", "10000", "10000", "10001", "01110"],
    "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "11110", "10000", "10000", "10000", "11111"],
    "F": ["11111", "10000", "11110", "10000", "10000", "10000", "10000"],
    "G": ["01110", "10001", "10000", "10111", "10001", "10001", "01110"],
    "H": ["10001", "10001", "11111", "10001", "10001", "10001", "10001"],
    "I": ["11111", "00100", "00100", "00100", "00100", "00100", "11111"],
    "J": ["00111", "00010", "00010", "00010", "00010", "10010", "01100"],
    "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "M": ["10001", "11011", "10101", "10001", "10001", "10001", "10001"],
    "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "Q": ["01110", "10001", "10001", "10001", "10101", "10010", "01101"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
    "W": ["10001", "10001", "10001", "10001", "10101", "10101", "01010"],
    "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
    "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
    "Z": ["11111", "00001", "00010", "00100", "01000", "10000", "11111"],
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "11111"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
    "3": ["01110", "10001", "00001", "00110", "00001", "10001", "01110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    "5": ["11111", "10000", "11110", "00001", "00001", "10001", "01110"],
    "6": ["01110", "10000", "11110", "10001", "10001", "10001", "01110"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "9": ["01110", "10001", "10001", "01111", "00001", "00001", "01110"],
    "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"],
    " ": ["00000", "00000", "00000", "00000", "00000", "00000", "00000"],
}


def _chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def encode_png(width: int, height: int, pixels: list[list[tuple[int, int, int, int]]]) -> bytes:
    raw = bytearray()
    for row in pixels:
        raw.append(0)
        for r, g, b, a in row:
            raw.extend((r, g, b, a))
    compressed = zlib.compress(bytes(raw), 9)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", compressed) + _chunk(b"IEND", b"")


def png_to_ico(png: bytes, size: int) -> bytes:
    count = 1
    header = struct.pack("<HHH", 0, 1, count)
    width_b = 0 if size >= 256 else size
    height_b = 0 if size >= 256 else size
    entry = struct.pack("<BBBBHHII", width_b, height_b, 0, 0, 1, 32, len(png), 6 + 16)
    return header + entry + png


def _blend(dst: tuple[int, int, int, int], src: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    sr, sg, sb, sa = src
    dr, dg, db, da = dst
    if sa == 255:
        return src
    if sa == 0:
        return dst
    a = sa / 255.0
    inv = 1.0 - a
    return (
        int(sr * a + dr * inv),
        int(sg * a + dg * inv),
        int(sb * a + db * inv),
        min(255, sa + da),
    )


def _fill_rect(
    pixels: list[list[tuple[int, int, int, int]]],
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    color: tuple[int, int, int, int],
    radius: int = 0,
) -> None:
    h = len(pixels)
    w = len(pixels[0])
    x0, x1 = max(0, x0), min(w, x1)
    y0, y1 = max(0, y0), min(h, y1)
    r = max(0, radius)
    for y in range(y0, y1):
        for x in range(x0, x1):
            if r:
                cx = x0 + r if x < x0 + r else (x1 - 1 - r if x > x1 - 1 - r else x)
                cy = y0 + r if y < y0 + r else (y1 - 1 - r if y > y1 - 1 - r else y)
                if (x - cx) ** 2 + (y - cy) ** 2 > r * r:
                    continue
            pixels[y][x] = _blend(pixels[y][x], color)


def _draw_char(
    pixels: list[list[tuple[int, int, int, int]]],
    ch: str,
    ox: int,
    oy: int,
    scale: int,
    color: tuple[int, int, int, int],
) -> None:
    glyph = _FONT.get(ch.upper(), _FONT[" "])
    for gy, row in enumerate(glyph):
        for gx, bit in enumerate(row):
            if bit != "1":
                continue
            for dy in range(scale):
                for dx in range(scale):
                    x = ox + gx * scale + dx
                    y = oy + gy * scale + dy
                    if 0 <= y < len(pixels) and 0 <= x < len(pixels[0]):
                        pixels[y][x] = color


def _draw_text_centered(
    pixels: list[list[tuple[int, int, int, int]]],
    text: str,
    cy: int,
    scale: int,
    color: tuple[int, int, int, int],
) -> None:
    text = "".join(ch if ch.upper() in _FONT else "-" for ch in text.upper())[:8]
    if not text:
        text = "APP"
    glyph_w = 5 * scale
    gap = max(1, scale)
    total = len(text) * glyph_w + (len(text) - 1) * gap
    w = len(pixels[0])
    ox = (w - total) // 2
    oy = cy - (7 * scale) // 2
    x = ox
    for ch in text:
        _draw_char(pixels, ch, x, oy, scale, color)
        x += glyph_w + gap


def _fill_circle(
    pixels: list[list[tuple[int, int, int, int]]],
    cx: float,
    cy: float,
    radius: float,
    color: tuple[int, int, int, int],
) -> None:
    h = len(pixels)
    w = len(pixels[0])
    r2 = radius * radius
    x0 = max(0, int(cx - radius) - 1)
    x1 = min(w, int(cx + radius) + 2)
    y0 = max(0, int(cy - radius) - 1)
    y1 = min(h, int(cy + radius) + 2)
    for y in range(y0, y1):
        for x in range(x0, x1):
            d2 = (x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2
            if d2 <= r2:
                pixels[y][x] = _blend(pixels[y][x], color)


def _draw_chevron(
    pixels: list[list[tuple[int, int, int, int]]],
    cx: int,
    cy: int,
    height: int,
    thickness: int,
    color: tuple[int, int, int, int],
) -> None:
    """Right-pointing chevron."""
    half = height // 2
    for y in range(-half, half + 1):
        x_mid = cx + abs(y) // 2
        for t in range(thickness):
            x = x_mid + t
            py = cy + y
            if 0 <= py < len(pixels) and 0 <= x < len(pixels[0]):
                pixels[py][x] = _blend(pixels[py][x], color)


def make_logo_png(size: int = 256) -> bytes:
    """Brand mark: package → converted package. Opaque so Tk/Windows icons render cleanly."""
    pixels = [[(0, 0, 0, 0) for _ in range(size)] for _ in range(size)]
    blue = (13, 110, 253, 255)
    blue_dark = (8, 72, 176, 255)
    white = (255, 255, 255, 255)
    frost = (255, 255, 255, 38)

    for y in range(size):
        t = y / max(1, size - 1)
        shade = (
            int(blue[0] * (1 - t) + blue_dark[0] * t),
            int(blue[1] * (1 - t) + blue_dark[1] * t),
            int(blue[2] * (1 - t) + blue_dark[2] * t),
            255,
        )
        for x in range(size):
            pixels[y][x] = shade

    pad = max(1, size // 18)
    radius = max(6, size // 5)
    _fill_rect(pixels, pad, pad, size - pad, size - pad, frost, radius=radius)

    lx0, ly0 = int(size * 0.16), int(size * 0.28)
    lx1, ly1 = int(size * 0.46), int(size * 0.74)
    _fill_rect(pixels, lx0, ly0, lx1, ly1, white, radius=max(3, size // 18))
    fold = max(4, size // 10)
    _fill_rect(pixels, lx1 - fold, ly0, lx1, ly0 + fold, blue, radius=0)
    line_color = (13, 110, 253, 220)
    inset = max(3, size // 22)
    for i in range(3):
        y = ly0 + int((ly1 - ly0) * (0.38 + i * 0.16))
        _fill_rect(pixels, lx0 + inset, y, lx1 - fold - 2, y + max(2, size // 48), line_color)

    rx0, ry0 = int(size * 0.54), int(size * 0.28)
    rx1, ry1 = int(size * 0.84), int(size * 0.74)
    _fill_rect(pixels, rx0, ry0, rx1, ry1, white, radius=max(3, size // 18))
    badge = max(5, size // 9)
    _fill_circle(pixels, rx1 - badge, ry1 - badge, badge * 0.72, (25, 180, 110, 255))
    cx, cy = rx1 - badge, ry1 - badge
    for t in range(max(2, size // 32)):
        for s in range(max(3, size // 22)):
            x = int(cx - badge * 0.28 + s)
            y = int(cy + s * 0.4 - t)
            if 0 <= y < size and 0 <= x < size:
                pixels[y][x] = white
        for s in range(max(4, size // 16)):
            x = int(cx - badge * 0.05 + s)
            y = int(cy + max(3, size // 22) * 0.4 - s * 0.55 - t)
            if 0 <= y < size and 0 <= x < size:
                pixels[y][x] = white

    _draw_chevron(
        pixels,
        cx=size // 2 - size // 28,
        cy=size // 2,
        height=max(10, size // 5),
        thickness=max(2, size // 22),
        color=white,
    )
    return encode_png(size, size, pixels)

    # left document
    lx0, ly0 = int(size * 0.16), int(size * 0.28)
    lx1, ly1 = int(size * 0.46), int(size * 0.74)
    _fill_rect(pixels, lx0, ly0, lx1, ly1, white, radius=max(3, size // 18))
    fold = max(4, size // 10)
    _fill_rect(pixels, lx1 - fold, ly0, lx1, ly0 + fold, blue, radius=0)
    # document lines
    line_color = (13, 110, 253, 220)
    inset = max(3, size // 22)
    for i in range(3):
        y = ly0 + int((ly1 - ly0) * (0.38 + i * 0.16))
        _fill_rect(pixels, lx0 + inset, y, lx1 - fold - 2, y + max(2, size // 48), line_color)

    # right document (slightly offset, “converted”)
    rx0, ry0 = int(size * 0.54), int(size * 0.28)
    rx1, ry1 = int(size * 0.84), int(size * 0.74)
    _fill_rect(pixels, rx0, ry0, rx1, ry1, white, radius=max(3, size // 18))
    badge = max(5, size // 9)
    _fill_circle(pixels, rx1 - badge, ry1 - badge, badge * 0.72, (25, 180, 110, 255))
    # check mark
    cx, cy = rx1 - badge, ry1 - badge
    for t in range(max(2, size // 32)):
        for s in range(max(3, size // 22)):
            x = int(cx - badge * 0.28 + s)
            y = int(cy + s * 0.4 - t)
            if 0 <= y < size and 0 <= x < size:
                pixels[y][x] = white
        for s in range(max(4, size // 16)):
            x = int(cx - badge * 0.05 + s)
            y = int(cy + max(3, size // 22) * 0.4 - s * 0.55 - t)
            if 0 <= y < size and 0 <= x < size:
                pixels[y][x] = white

    _draw_chevron(
        pixels,
        cx=size // 2 - size // 28,
        cy=size // 2,
        height=max(10, size // 5),
        thickness=max(2, size // 22),
        color=white,
    )
    return encode_png(size, size, pixels)


def make_app_icon_png(label: str, size: int = 256) -> bytes:
    """App-store style icon used inside the ipkg (`ui/ico/app.png`)."""
    bg = (14, 99, 214, 255)
    bg2 = (9, 72, 163, 255)
    fg = (255, 255, 255, 255)
    pixels = [[bg for _ in range(size)] for _ in range(size)]
    for y in range(size):
        t = y / max(1, size - 1)
        shade = (
            int(bg[0] * (1 - t) + bg2[0] * t),
            int(bg[1] * (1 - t) + bg2[1] * t),
            int(bg[2] * (1 - t) + bg2[2] * t),
            255,
        )
        for x in range(size):
            pixels[y][x] = shade
    pad = size // 12
    _fill_rect(pixels, pad, pad, size - pad, size - pad, (255, 255, 255, 28), radius=size // 8)
    letters = "".join(c for ch in label.upper() for c in ch if ch.isalnum() or ch == "-")[:4] or "APP"
    scale = max(4, size // (8 + max(0, len(letters) - 2) * 2))
    _draw_text_centered(pixels, letters, size // 2, scale, fg)
    return encode_png(size, size, pixels)


def make_exe_icon_ico(size: int = 256) -> bytes:
    png = make_logo_png(size)
    return png_to_ico(png, size)
