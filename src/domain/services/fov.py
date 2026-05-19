"""Symmetric shadowcasting field-of-view computation.

Pure-function FOV consumed by AI wake-up (does this enemy see the
player?) and, eventually, the renderer (what tiles does the player see?).
The algorithm is symmetric in the sense of Albert Ford
(https://www.albertford.com/shadowcasting/): ``A in compute_fov(B, ...)``
iff ``B in compute_fov(A, ...)`` given the same ``blocks_sight``
predicate. Symmetry matters for combat fairness — an asymmetric FOV would
let an enemy ambush from a tile the player cannot see back through.

Slopes use ``fractions.Fraction`` so the algorithm is bit-exact across
CPython builds. Float slopes would introduce machine-epsilon drift at
corner cases (slopes like 1/3) that flips visibility unpredictably across
platforms — fatal for the planned replay system, where re-running a seed
must reproduce the rendered state exactly.
"""

import math
from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction
from typing import Final

_NORTH: Final[int] = 0
_EAST: Final[int] = 1
_SOUTH: Final[int] = 2
_WEST: Final[int] = 3


@dataclass(frozen=True)
class _Quadrant:
    """One of the four cardinal quadrants scanned outward from the origin.

    A quadrant's local frame is ``(depth, col)`` where ``depth`` increases
    away from the origin along the cardinal axis and ``col`` is the
    perpendicular offset. ``transform`` projects this into world ``(x, y)``.
    """

    cardinal: int
    ox: int
    oy: int

    def transform(self, depth: int, col: int) -> tuple[int, int]:
        if self.cardinal == _NORTH:
            return (self.ox + col, self.oy - depth)
        if self.cardinal == _EAST:
            return (self.ox + depth, self.oy + col)
        if self.cardinal == _SOUTH:
            return (self.ox + col, self.oy + depth)
        return (self.ox - depth, self.oy + col)


@dataclass
class _Row:
    """A scan row at fixed ``depth``, bounded by ``[start_slope, end_slope]``.

    Mutable because the algorithm tightens ``start_slope`` mid-scan after
    a wall→floor transition; the change applies to subsequent next-row
    spawns, not retroactively to the current row's already-materialised
    ``range``.
    """

    depth: int
    start_slope: Fraction
    end_slope: Fraction

    def tiles(self) -> range:
        min_col = _round_ties_up(self.depth * self.start_slope)
        max_col = _round_ties_down(self.depth * self.end_slope)
        return range(min_col, max_col + 1)

    def next_row(self) -> "_Row":
        return _Row(self.depth + 1, self.start_slope, self.end_slope)


def compute_fov(
    origin: tuple[int, int],
    *,
    blocks_sight: Callable[[int, int], bool],
    width: int,
    height: int,
    max_radius: int | None = None,
) -> frozenset[tuple[int, int]]:
    """Return the set of tiles visible from ``origin``.

    ``blocks_sight(x, y)`` decides whether a tile blocks vision. The
    function is only ever called with in-bounds ``(x, y)``; out-of-bounds
    coordinates are handled internally as blocking (neither visible nor
    transparent), so callers can index a grid without their own bounds
    check.

    ``max_radius`` bounds the scan in *Chebyshev* (square) distance. This
    is the natural shape for the row-by-row quadrant scan, and it matches
    the wake-up rule used by ``enemy_ai`` (``chebyshev_distance ≤ 8``).
    ``None`` (default) is unbounded except by the grid itself.

    Origin is always included in the result.
    """
    visible: set[tuple[int, int]] = {origin}
    if max_radius is not None and max_radius <= 0:
        return frozenset(visible)

    bound = max_radius if max_radius is not None else max(width, height)
    ox, oy = origin

    def bounded_blocks(x: int, y: int) -> bool:
        if not (0 <= x < width and 0 <= y < height):
            return True
        return blocks_sight(x, y)

    for cardinal in (_NORTH, _EAST, _SOUTH, _WEST):
        quadrant = _Quadrant(cardinal=cardinal, ox=ox, oy=oy)
        first_row = _Row(depth=1, start_slope=Fraction(-1), end_slope=Fraction(1))
        _scan(first_row, quadrant, visible, bounded_blocks, max_depth=bound)

    # Out-of-bounds tiles act as opaque walls during the scan (so vision
    # cannot leak past the grid edge), but they are not real tiles and
    # must never appear in the reported result.
    return frozenset((x, y) for x, y in visible if 0 <= x < width and 0 <= y < height)


def has_los(
    a: tuple[int, int],
    b: tuple[int, int],
    *,
    blocks_sight: Callable[[int, int], bool],
    width: int,
    height: int,
    max_radius: int | None = None,
) -> bool:
    """True iff ``a`` can see ``b`` under symmetric shadowcasting.

    Symmetric by construction: ``has_los(a, b, ...) == has_los(b, a, ...)``
    for any fixed ``blocks_sight``. A point is always in line-of-sight to
    itself.
    """
    if a == b:
        return True
    return b in compute_fov(
        a,
        blocks_sight=blocks_sight,
        width=width,
        height=height,
        max_radius=max_radius,
    )


def _scan(
    row: _Row,
    quadrant: _Quadrant,
    visible: set[tuple[int, int]],
    blocks: Callable[[int, int], bool],
    *,
    max_depth: int,
) -> None:
    if row.depth > max_depth:
        return
    prev_blocks: bool | None = None
    saw_tile = False
    for col in row.tiles():
        saw_tile = True
        wx, wy = quadrant.transform(row.depth, col)
        tile_blocks = blocks(wx, wy)
        if tile_blocks or _is_symmetric(row, col):
            visible.add((wx, wy))
        if prev_blocks is True and not tile_blocks:
            row.start_slope = _slope(row.depth, col)
        if prev_blocks is False and tile_blocks:
            next_row = row.next_row()
            next_row.end_slope = _slope(row.depth, col)
            _scan(next_row, quadrant, visible, blocks, max_depth=max_depth)
        prev_blocks = tile_blocks
    if saw_tile and prev_blocks is False:
        _scan(row.next_row(), quadrant, visible, blocks, max_depth=max_depth)


def _is_symmetric(row: _Row, col: int) -> bool:
    return col >= row.depth * row.start_slope and col <= row.depth * row.end_slope


def _slope(depth: int, col: int) -> Fraction:
    return Fraction(2 * col - 1, 2 * depth)


def _round_ties_up(n: Fraction) -> int:
    return math.floor(n + Fraction(1, 2))


def _round_ties_down(n: Fraction) -> int:
    return math.ceil(n - Fraction(1, 2))
