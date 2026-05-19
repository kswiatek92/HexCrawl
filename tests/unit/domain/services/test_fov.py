"""Tests for ``src.domain.services.fov`` — symmetric shadowcasting.

The contract under test:
* origin is always visible;
* tiles are visible when no opaque tile sits on the line between them;
* tile and origin agree about each other (the symmetric invariant);
* ``max_radius`` constrains the scan in Chebyshev distance;
* out-of-bounds tiles never appear in the result.
"""

from collections.abc import Callable

from src.domain.services.fov import compute_fov, has_los


def _grid_blocker(rows: list[str]) -> tuple[Callable[[int, int], bool], int, int]:
    """Compile a string-grid into a ``blocks_sight`` callable plus dims.

    ``'#'`` is an opaque tile, ``'.'`` (and anything else) is transparent.
    Top row is ``y=0``; the grid is row-major ``rows[y][x]`` to mirror
    the ``Floor.tiles`` layout from the domain.
    """
    height = len(rows)
    width = len(rows[0]) if height > 0 else 0

    def blocks(x: int, y: int) -> bool:
        return rows[y][x] == "#"

    return blocks, width, height


def test_origin_is_always_visible_even_when_radius_is_zero() -> None:
    blocks, w, h = _grid_blocker(["...", "...", "..."])
    fov = compute_fov((1, 1), blocks_sight=blocks, width=w, height=h, max_radius=0)
    assert fov == frozenset({(1, 1)})


def test_open_field_sees_every_in_range_tile() -> None:
    blocks, w, h = _grid_blocker(["." * 5] * 5)
    fov = compute_fov((2, 2), blocks_sight=blocks, width=w, height=h)
    expected = frozenset((x, y) for y in range(h) for x in range(w))
    assert fov == expected


def test_chebyshev_radius_caps_the_visible_set() -> None:
    # A clear 7x7 field; radius 2 should expose exactly the 5x5 Chebyshev
    # square around the origin.
    blocks, w, h = _grid_blocker(["." * 7] * 7)
    fov = compute_fov((3, 3), blocks_sight=blocks, width=w, height=h, max_radius=2)
    expected = frozenset((x, y) for y in range(1, 6) for x in range(1, 6))
    assert fov == expected


def test_wall_directly_north_hides_tile_behind_it_but_reveals_the_wall() -> None:
    # Origin (1, 2); wall at (1, 1); the tile at (1, 0) should be hidden
    # but the wall itself is visible (you see the wall's surface).
    blocks, w, h = _grid_blocker(
        [
            "...",
            ".#.",
            "...",
        ]
    )
    fov = compute_fov((1, 2), blocks_sight=blocks, width=w, height=h)
    assert (1, 1) in fov  # wall surface visible
    assert (1, 0) not in fov  # tile behind wall hidden


def test_visibility_is_symmetric_across_a_pillar() -> None:
    # Two open tiles separated by a wall in between — neither can see
    # the other, and the relationship is symmetric.
    blocks, w, h = _grid_blocker(
        [
            "...",
            ".#.",
            "...",
        ]
    )
    fov_from_top = compute_fov((1, 0), blocks_sight=blocks, width=w, height=h)
    fov_from_bot = compute_fov((1, 2), blocks_sight=blocks, width=w, height=h)
    assert (1, 2) not in fov_from_top
    assert (1, 0) not in fov_from_bot


def test_symmetric_invariant_across_many_pairs_in_a_walled_room() -> None:
    # 5x5 with a vertical wall splitting it at x=2; for every pair (a, b),
    # b in fov(a) iff a in fov(b). This is the load-bearing invariant.
    rows = [
        ".....",
        "..#..",
        "..#..",
        "..#..",
        ".....",
    ]
    blocks, w, h = _grid_blocker(rows)
    fovs: dict[tuple[int, int], frozenset[tuple[int, int]]] = {}
    points = [(x, y) for y in range(h) for x in range(w) if rows[y][x] != "#"]
    for p in points:
        fovs[p] = compute_fov(p, blocks_sight=blocks, width=w, height=h)
    for a in points:
        for b in points:
            assert (b in fovs[a]) == (a in fovs[b]), f"symmetry violated for {a} <-> {b}"


def test_out_of_bounds_tiles_are_never_in_the_result() -> None:
    blocks, w, h = _grid_blocker(["." * 5] * 5)
    fov = compute_fov((0, 0), blocks_sight=blocks, width=w, height=h)
    for x, y in fov:
        assert 0 <= x < w and 0 <= y < h


def test_has_los_is_true_for_identical_points() -> None:
    blocks, w, h = _grid_blocker(["#"])  # a one-tile wall grid
    assert has_los((0, 0), (0, 0), blocks_sight=blocks, width=w, height=h)


def test_has_los_agrees_with_compute_fov() -> None:
    blocks, w, h = _grid_blocker(
        [
            ".....",
            ".....",
            "..#..",
            ".....",
            ".....",
        ]
    )
    a = (0, 2)
    b = (4, 2)
    fov_a = compute_fov(a, blocks_sight=blocks, width=w, height=h)
    assert has_los(a, b, blocks_sight=blocks, width=w, height=h) == (b in fov_a)


def test_has_los_is_symmetric_around_obstacles() -> None:
    blocks, w, h = _grid_blocker(
        [
            ".....",
            ".....",
            "..#..",
            ".....",
            ".....",
        ]
    )
    # Pairs spanning the pillar from various angles.
    pairs = [((0, 2), (4, 2)), ((1, 1), (3, 3)), ((2, 0), (2, 4)), ((0, 0), (4, 4))]
    for a, b in pairs:
        forward = has_los(a, b, blocks_sight=blocks, width=w, height=h)
        backward = has_los(b, a, blocks_sight=blocks, width=w, height=h)
        assert forward == backward, f"asymmetry: {a} <-> {b}"


def test_long_corridor_sees_end_to_end() -> None:
    # A 1-tile-wide corridor 7 tiles long; the endpoints see each other.
    blocks, w, h = _grid_blocker(
        [
            "#########",
            "#.......#",
            "#########",
        ]
    )
    assert has_los((1, 1), (7, 1), blocks_sight=blocks, width=w, height=h)
    assert has_los((7, 1), (1, 1), blocks_sight=blocks, width=w, height=h)


def test_radius_bounded_los_rejects_distant_target_even_with_clear_line() -> None:
    blocks, w, h = _grid_blocker(["." * 20] * 3)
    # Clear horizontal line — but radius=5 means Chebyshev>5 is excluded.
    assert has_los((0, 1), (5, 1), blocks_sight=blocks, width=w, height=h, max_radius=5)
    assert not has_los((0, 1), (15, 1), blocks_sight=blocks, width=w, height=h, max_radius=5)


def test_compute_fov_is_deterministic() -> None:
    # Determinism guards against accidental float math in slope handling.
    blocks, w, h = _grid_blocker(
        [
            "........",
            "..#..#..",
            ".......#",
            "....#...",
            "##......",
            ".....#..",
        ]
    )
    a = compute_fov((3, 3), blocks_sight=blocks, width=w, height=h)
    b = compute_fov((3, 3), blocks_sight=blocks, width=w, height=h)
    assert a == b
