"""Contract test for the hand-authored 16x16 tile set (BOARD task 5.2).

The renderer (5.3) loads these tiles by `TileType` name, so the committed PNGs must
honour a fixed contract: 16x16, palette-pure (only the 4 Game Boy colours), all four
present, seamless for the textures, and wired into the manifest. This test decodes the
committed bytes independently (stdlib only -- no Pillow, no trust in the generator), so
reverting a tile to an off-palette draft or dropping `stairs.png` fails it.
"""

from __future__ import annotations

import json
import struct
import zlib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
TILE_DIR = REPO_ROOT / "assets" / "sprites" / "tiles"
MANIFEST = REPO_ROOT / "assets" / "manifest.json"
PALETTE_GPL = REPO_ROOT / "docs" / "palettes" / "gameboy-4.gpl"

TILES = ["wall", "floor", "stairs", "door"]
TILE_TYPES = ["WALL", "FLOOR", "STAIRS", "DOOR"]
SEAMLESS = ["wall", "floor"]  # WALL/FLOOR must tile edge-to-edge

RGB = tuple[int, int, int]
Pixels = list[list[RGB]]


def _decode_png(data: bytes) -> tuple[int, int, Pixels]:
    """Minimal decoder for our own 8-bit RGBA, filter-0, non-interlaced PNGs."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    pos = 8
    width = height = 0
    idat = bytearray()
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        tag = data[pos + 4 : pos + 8]
        chunk = data[pos + 8 : pos + 8 + length]
        pos += 12 + length  # length + tag + data + crc
        if tag == b"IHDR":
            width, height, bit_depth, color_type, compression, filter_method, interlace = (
                struct.unpack(">IIBBBBB", chunk[:13])
            )
            assert bit_depth == 8 and color_type == 6, "expected 8-bit RGBA"
            assert (compression, filter_method, interlace) == (
                0,
                0,
                0,
            ), "expected non-interlaced PNG"
        elif tag == b"IDAT":
            idat += chunk
        elif tag == b"IEND":
            break
    raw = zlib.decompress(bytes(idat))
    stride = width * 4
    assert len(raw) == height * (stride + 1), "decoded IDAT length does not match dimensions"
    rows: Pixels = []
    for y in range(height):
        start = y * (stride + 1)
        assert raw[start] == 0, "expected filter type 0 (None)"
        line = raw[start + 1 : start + 1 + stride]
        rows.append([(line[x * 4], line[x * 4 + 1], line[x * 4 + 2]) for x in range(width)])
    return width, height, rows


def _palette() -> set[RGB]:
    colours: set[RGB] = set()
    for line in PALETTE_GPL.read_text().splitlines():
        parts = line.split()
        if len(parts) >= 3 and all(p.isdigit() for p in parts[:3]):
            colours.add((int(parts[0]), int(parts[1]), int(parts[2])))
    return colours


def test_palette_has_four_colours() -> None:
    assert len(_palette()) == 4


def test_all_tiles_present() -> None:
    for name in TILES:
        assert (TILE_DIR / f"{name}.png").is_file(), f"{name}.png missing"


@pytest.mark.parametrize("name", TILES)
def test_dimensions_are_16x16(name: str) -> None:
    width, height, _ = _decode_png((TILE_DIR / f"{name}.png").read_bytes())
    assert (width, height) == (16, 16)


@pytest.mark.parametrize("name", TILES)
def test_only_palette_colours(name: str) -> None:
    palette = _palette()
    _, _, rows = _decode_png((TILE_DIR / f"{name}.png").read_bytes())
    used = {px for row in rows for px in row}
    assert used <= palette, f"{name}.png has off-palette colours: {used - palette}"


@pytest.mark.parametrize("name", SEAMLESS)
def test_floor_and_wall_tile_seamlessly(name: str) -> None:
    """A texture tiles seamlessly iff it is spatially periodic with a period dividing
    16 on each axis: FLOOR has a uniform 1-colour border (period 1), WALL has period 8.
    Both hold here, so wrapping a copy beside/below shows no discontinuity.
    """
    _, _, rows = _decode_png((TILE_DIR / f"{name}.png").read_bytes())
    if name == "floor":
        edges = set(rows[0]) | set(rows[15])
        edges |= {rows[y][0] for y in range(16)} | {rows[y][15] for y in range(16)}
        assert len(edges) == 1, "FLOOR border must be a single colour to tile seamlessly"
    else:  # wall: period 8 on both axes
        for y in range(16):
            for x in range(8):
                assert rows[y][x] == rows[y][x + 8], "WALL not horizontally period-8"
        for y in range(8):
            assert rows[y] == rows[y + 8], "WALL not vertically period-8"


def test_manifest_tiles_synced() -> None:
    tiles = json.loads(MANIFEST.read_text())["tiles"]
    for tile_type in TILE_TYPES:
        entry = tiles[tile_type]
        assert entry["sprite"], f"{tile_type} has no sprite path"
        assert entry["size"] == 16
        assert entry["status"] != "todo", f"{tile_type} still marked todo"
        assert (REPO_ROOT / entry["sprite"]).is_file(), f"{tile_type} sprite path is broken"
