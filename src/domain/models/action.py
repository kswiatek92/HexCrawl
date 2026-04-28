"""Player-action type union — the typed input to ``GameService.process_turn``.

An ``Action`` is "what the player asked for at turn N". The WebSocket
entrypoint (``/ws/game/{session_id}``) deserialises raw JSON into one of
these typed instances; the domain never sees raw JSON. ``GameService``
then dispatches over the union via a ``match`` statement (mypy-strict
exhaustiveness-checked) and produces a new game state.

Every variant is a ``@dataclass(frozen=True)``: an action is recorded
once and never mutated after dispatch, mirroring the snapshot semantic of
``Score`` (see ADR 0002). Frozen dataclasses are also hashable, so a
turn log keyed on ``(session_id, turn_n)`` can use them as values without
custom hashing.

``Direction`` is orthogonal-only (no diagonals) for v1, matching the BSP
floor + 80×50 grid convention; diagonals slot in additively in v2 without
breaking existing match arms. The enum follows ADR 0001
(``StrEnum`` with ``value == name``) so it serialises cleanly as JSON
and is rename-safe.
"""

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class Direction(StrEnum):
    """Cardinal compass direction for one-tile moves, attacks, and door opens.

    Orthogonal-only for v1. ``StrEnum`` with ``value == name`` per ADR
    0001 — JSON-clean over the WebSocket turn loop and rename-safe.
    """

    NORTH = "NORTH"
    SOUTH = "SOUTH"
    EAST = "EAST"
    WEST = "WEST"


@dataclass(frozen=True)
class Move:
    """Walk one tile in ``direction``.

    Resolves to an attack if the target tile holds an enemy — attack is
    implicit on "move into enemy tile" (see ``QUESTIONS.md`` task 1.9).
    The standalone ``Attack`` variant is for explicit attacks where
    moving is not desired or possible.
    """

    direction: Direction


@dataclass(frozen=True)
class Attack:
    """Explicit attack on the adjacent tile in ``direction``.

    Used when the player wants to attack without moving (e.g. attacking
    a diagonal-adjacent enemy by hitting a cardinal direction first, or
    when the target tile is movement-blocked but still attackable).
    Reserved as the seam for future ranged / targeted attacks.
    """

    direction: Direction


@dataclass(frozen=True)
class Wait:
    """Skip the turn — pass to enemy AI without acting."""


@dataclass(frozen=True)
class PickUp:
    """Pick up the items on the player's current tile.

    Explicit (not auto-on-step) because ``Floor.items`` may stack many
    items on one tile and ``Player`` has fixed equipment slots / a
    cap-5 consumables stack — auto-pickup would silently drop or
    overwrite gear. The pickup logic in ``GameService`` decides which
    items fit and what gets dropped.
    """


@dataclass(frozen=True)
class UseItem:
    """Consume a single consumable from the consumables stack.

    Identified by ``item_id`` (matches ``Item.item_id``) rather than a
    stack index so the action is stable across reorderings. Only
    ``ItemType.POTION`` / ``ItemType.KEY`` are currently consumable —
    ``GameService`` rejects others.
    """

    item_id: UUID


@dataclass(frozen=True)
class Open:
    """Open the closed ``DOOR`` adjacent to the player in ``direction``.

    A discrete action (not folded into ``Move``) because closed doors
    block line-of-sight per the 1.3 ranged-LOS decision — the open
    transition has to be observable to the AI step that follows.
    """

    direction: Direction


@dataclass(frozen=True)
class Descend:
    """Take the down-staircase at the player's current position.

    Bounds-checked by ``GameService`` against ``Dungeon.current_floor_index``
    and ``TOTAL_FLOORS``; this dataclass is just the request.
    """


@dataclass(frozen=True)
class Abandon:
    """End the run without scoring.

    Distinct from death: ``Abandon`` short-circuits ``ScoreService`` and
    is the v1 equivalent of "quit run". The leaderboard never sees an
    abandoned run.
    """


type Action = Move | Attack | Wait | PickUp | UseItem | Open | Descend | Abandon
"""Discriminated union of every player-action variant.

Use ``match`` to dispatch (PEP 634), e.g.::

    match action:
        case Move(direction=d): ...
        case Attack(direction=d): ...
        case Wait(): ...
        case PickUp(): ...
        case UseItem(item_id=item_id): ...
        case Open(direction=d): ...
        case Descend(): ...
        case Abandon(): ...

mypy-strict exhaustiveness-checks the match — adding a new variant
without updating every call site fails type-check. The "unknown action"
case (``case _:``) belongs in entrypoints for raw-JSON guard, not in
``GameService`` (the union itself prevents unknown-variant inputs once
the entrypoint has done its job — see QUIZZES.md task 1.9 Q4 / Q5).
"""
