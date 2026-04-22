from enum import StrEnum


class TileType(StrEnum):
    """Top-level tile category for a `Floor` grid.

    ``StrEnum`` (Python 3.11+) mirrors ``BehaviourType`` and ``ItemType``:
    str inheritance means variants serialise cleanly as JSON over the
    WebSocket turn loop and compare equal to their wire-format literals,
    while still being singletons (``TileType.WALL is TileType.WALL``) for
    fast, typo-proof game-logic comparisons. Passability rules live with
    the consumers (``GameService``), not on this enum.

    v1 surface is ``WALL | FLOOR | STAIRS | DOOR`` — matches the Key
    Domain Concepts in CLAUDE.md. Variants like ``TRAP`` / ``WATER`` are
    additive in a future phase without breaking existing pattern matches.
    """

    WALL = "WALL"
    FLOOR = "FLOOR"
    STAIRS = "STAIRS"
    DOOR = "DOOR"
