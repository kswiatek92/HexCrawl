"""Colour-key a sprite draft's background to transparency (BOARD task 5.4).

The AI-generated sprite drafts under ``assets/sprites/{player,enemies,items}`` are
fully opaque: their background is a flat fill of one palette colour (the lightest
Game Boy green for the player draft). Drawn over the floor that background would be
an opaque block, so the renderer needs an alpha background instead.

This tool reads such a PNG, treats the **corner** pixel as the background colour,
flood-fills every background pixel that is *connected to the image border* to
alpha=0, and writes an 8-bit RGBA PNG. Flood-filling from the border (rather than
keying every pixel of that colour) preserves interior pixels that happen to reuse
the background colour as a highlight -- only the outer field becomes transparent.

    python assets/tools/key_sprites.py <input.png> <output.png>

Stdlib only -- no Pillow, matching gen_tiles.py. The PNG reader handles exactly the
shape the drafts use (8-bit, colour type 3 palette, non-interlaced); the writer
mirrors gen_tiles.py's RGBA encoder. This is an out-of-app authoring tool, not
application code; ``print`` is the CLI's own output, not logging.
"""

from __future__ import annotations

import struct
import sys
import zlib
from collections import deque
from pathlib import Path

RGBA = tuple[int, int, int, int]


def _read_chunks(data: bytes) -> list[tuple[bytes, bytes]]:
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG file")
    chunks: list[tuple[bytes, bytes]] = []
    i = 8
    while i < len(data):
        (length,) = struct.unpack(">I", data[i : i + 4])
        tag = data[i + 4 : i + 8]
        payload = data[i + 8 : i + 8 + length]
        chunks.append((tag, payload))
        i += 12 + length  # length + tag + data + crc
    return chunks


def _paeth(a: int, b: int, c: int) -> int:
    """PNG Paeth predictor: pick the neighbour closest to a+b-c."""
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def _unfilter(raw: bytes, width: int, height: int, bpp: int) -> bytearray:
    """Reverse PNG row filters into a flat sample buffer (bpp bytes per pixel)."""
    stride = width * bpp
    out = bytearray()
    prev = bytearray(stride)
    pos = 0
    for _ in range(height):
        ftype = raw[pos]
        pos += 1
        line = bytearray(raw[pos : pos + stride])
        pos += stride
        for x in range(stride):
            a = line[x - bpp] if x >= bpp else 0  # left
            b = prev[x]  # up
            c = prev[x - bpp] if x >= bpp else 0  # up-left
            if ftype == 0:
                pass
            elif ftype == 1:
                line[x] = (line[x] + a) & 0xFF
            elif ftype == 2:
                line[x] = (line[x] + b) & 0xFF
            elif ftype == 3:
                line[x] = (line[x] + (a + b) // 2) & 0xFF
            elif ftype == 4:
                line[x] = (line[x] + _paeth(a, b, c)) & 0xFF
            else:
                raise ValueError(f"unsupported PNG filter type {ftype}")
        out += line
        prev = line
    return out


def read_rgba(path: Path) -> tuple[int, int, list[list[RGBA]]]:
    """Decode an 8-bit, palette (colour type 3), non-interlaced PNG to RGBA pixels."""
    chunks = _read_chunks(path.read_bytes())
    header = next(p for t, p in chunks if t == b"IHDR")
    width, height, bit_depth, colour_type, _comp, _filt, interlace = struct.unpack(
        ">IIBBBBB", header
    )
    if (bit_depth, colour_type, interlace) != (8, 3, 0):
        raise ValueError(
            "only 8-bit palette (colour type 3), non-interlaced PNGs are supported"
        )
    plte = next(p for t, p in chunks if t == b"PLTE")
    palette = [
        (plte[i], plte[i + 1], plte[i + 2], 255) for i in range(0, len(plte), 3)
    ]
    idat = b"".join(p for t, p in chunks if t == b"IDAT")
    indices = _unfilter(zlib.decompress(idat), width, height, bpp=1)
    pixels = [
        [palette[indices[y * width + x]] for x in range(width)] for y in range(height)
    ]
    return width, height, pixels


def key_background(pixels: list[list[RGBA]], width: int, height: int) -> int:
    """Flood-fill border-connected background pixels to alpha=0. Returns the count.

    The background colour is sampled from the top-left corner. A breadth-first fill
    seeded from every border pixel of that colour spreads through 4-connected
    neighbours, so only the outer field is cleared -- interior pixels reusing the
    colour as a highlight are left opaque.
    """
    bg = pixels[0][0]
    if bg[3] == 0:
        return 0
    transparent = (bg[0], bg[1], bg[2], 0)

    queue: deque[tuple[int, int]] = deque()
    seen = [[False] * width for _ in range(height)]

    def seed(x: int, y: int) -> None:
        if not seen[y][x] and pixels[y][x] == bg:
            seen[y][x] = True
            queue.append((x, y))

    for x in range(width):
        seed(x, 0)
        seed(x, height - 1)
    for y in range(height):
        seed(0, y)
        seed(width - 1, y)

    cleared = 0
    while queue:
        x, y = queue.popleft()
        pixels[y][x] = transparent
        cleared += 1
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < width and 0 <= ny < height:
                seed(nx, ny)
    return cleared


def _png_bytes(pixels: list[list[RGBA]], width: int, height: int) -> bytes:
    raw = bytearray()
    for row in pixels:
        raw.append(0)  # per-row filter type 0 (None) -> trivially decodable
        for r, g, b, a in row:
            raw += bytes((r, g, b, a))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)  # 8-bit RGBA
    idat = zlib.compress(bytes(raw), 9)
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: python assets/tools/key_sprites.py <input.png> <output.png>")
        return 2
    src, dst = Path(argv[1]), Path(argv[2])
    width, height, pixels = read_rgba(src)
    cleared = key_background(pixels, width, height)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(_png_bytes(pixels, width, height))
    print(f"wrote {dst} ({width}x{height}, {cleared} background px -> transparent)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
