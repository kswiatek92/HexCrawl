"""Hand-authored 16x16 dungeon tiles for the HexCrawl renderer (BOARD task 5.2).

Stdlib only -- no Pillow. Each tile is defined as a 16x16 grid of palette indices
(0..3) into the locked Game Boy 4-colour ramp (docs/palettes/gameboy-4.gpl), then
encoded to an 8-bit RGBA PNG. Run

    python assets/tools/gen_tiles.py

to regenerate assets/sprites/tiles/{wall,floor,stairs,door}.png.

WALL and FLOOR are designed to tile seamlessly on all four edges:
  - FLOOR keeps every edge pixel on the base colour (uniform border -> no seam).
  - WALL is periodic with horizontal and vertical period 8 (period | 16 -> wraps).
STAIRS and DOOR are single tiles and need not tile.

This is an out-of-app authoring tool, not application code; `print` is the CLI's
own output, not logging (the "use structlog" rule is for src/).
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

SIZE = 16

# Palette index -> (R, G, B). Mirrors docs/palettes/gameboy-4.gpl, darkest..lightest.
DARKEST, DARK, LIGHT, LIGHTEST = 0, 1, 2, 3
PALETTE: list[tuple[int, int, int]] = [
    (15, 56, 15),  # 0 darkest
    (48, 98, 48),  # 1 dark
    (139, 172, 15),  # 2 light
    (155, 188, 15),  # 3 lightest
]

Grid = list[list[int]]


def _blank(fill: int) -> Grid:
    return [[fill] * SIZE for _ in range(SIZE)]


def floor_tile() -> Grid:
    """Low-contrast cobble: DARK base, sparse DARKEST grout + a few LIGHT flecks.

    All edge pixels stay DARK so the texture tiles with no visible seam, and the
    low contrast keeps player/enemy sprites readable on top.
    """
    grid = _blank(DARK)
    grout = [(2, 5), (3, 11), (5, 3), (6, 9), (8, 13), (9, 6), (11, 2), (12, 10), (13, 7)]
    flecks = [(4, 8), (7, 12), (10, 4), (13, 13)]
    for r, c in grout:
        grid[r][c] = DARKEST
    for r, c in flecks:
        grid[r][c] = LIGHT
    return grid


def wall_tile() -> Grid:
    """Running-bond brick. Mortar (DARKEST) on each 4px course bottom and on
    half-offset vertical joints; LIGHTEST highlight on each brick's top row.

    Horizontal joints repeat every 8 px and courses every 8 rows, so the pattern
    is periodic with period 8 on both axes (period | 16) and tiles on every edge.
    """
    grid = _blank(LIGHT)
    for r in range(SIZE):
        course = r // 4
        for c in range(SIZE):
            if r % 4 == 3:  # horizontal mortar line at course bottom
                grid[r][c] = DARKEST
                continue
            joint_col = 0 if course % 2 == 0 else 4  # half-offset per course
            if c % 8 == joint_col:  # vertical mortar joint
                grid[r][c] = DARKEST
            elif r % 4 == 0:  # brick top highlight
                grid[r][c] = LIGHTEST
            else:
                grid[r][c] = LIGHT
    return grid


def stairs_tile() -> Grid:
    """Top-down descending staircase: DARKEST frame, four stacked steps each with a
    LIGHTEST lip and a DARKEST drop edge, darkening toward a DARK pit at the bottom.
    """
    grid = _blank(LIGHT)
    for i in range(SIZE):  # frame
        grid[0][i] = grid[SIZE - 1][i] = DARKEST
        grid[i][0] = grid[i][SIZE - 1] = DARKEST
    for step in range(4):
        top = 1 + step * 3  # 1, 4, 7, 10
        tread = LIGHT if step < 2 else DARK  # nearer steps read darker (deeper)
        for c in range(1, SIZE - 1):
            grid[top][c] = LIGHTEST  # step lip (leading edge)
            grid[top + 1][c] = tread  # tread surface
            grid[top + 2][c] = DARKEST  # step drop
    for r in (13, 14):  # deep pit below the last step
        for c in range(1, SIZE - 1):
            grid[r][c] = DARK
    return grid


def door_tile() -> Grid:
    """Closed dungeon door: DARKEST frame/background, vertical plank body with
    LIGHT highlights and DARKEST seams, and a LIGHTEST handle. Sits in a wall cell.
    """
    grid = _blank(DARKEST)
    for r in range(1, SIZE - 1):  # plank panel, inset by 2 on each side
        for c in range(2, SIZE - 2):
            grid[r][c] = DARK
    for c in (3, 6, 9, 12):  # plank face highlights
        for r in range(2, SIZE - 2):
            grid[r][c] = LIGHT
    for c in (5, 8, 11):  # seams between planks
        for r in range(2, SIZE - 2):
            grid[r][c] = DARKEST
    grid[8][11] = grid[9][11] = LIGHTEST  # door handle
    return grid


def _png_bytes(grid: Grid) -> bytes:
    raw = bytearray()
    for row in grid:
        raw.append(0)  # per-row filter type 0 (None) -> trivially decodable
        for idx in row:
            r, g, b = PALETTE[idx]
            raw += bytes((r, g, b, 255))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", SIZE, SIZE, 8, 6, 0, 0, 0)  # 8-bit RGBA, no interlace
    idat = zlib.compress(bytes(raw), 9)
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


TILES = {
    "wall": wall_tile,
    "floor": floor_tile,
    "stairs": stairs_tile,
    "door": door_tile,
}


def main() -> None:
    out = Path(__file__).resolve().parents[1] / "sprites" / "tiles"
    out.mkdir(parents=True, exist_ok=True)
    for name, build in TILES.items():
        (out / f"{name}.png").write_bytes(_png_bytes(build()))
        print(f"wrote {out / f'{name}.png'}")


if __name__ == "__main__":
    main()
