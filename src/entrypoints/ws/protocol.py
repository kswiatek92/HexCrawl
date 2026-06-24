"""WebSocket wire protocol for the turn loop: parse inbound, serialise outbound.

The socket carries raw JSON; this module is the **anti-corruption boundary**
(QUIZZES task 3.9 Q3): it turns an inbound ``{"action": "move", ...}`` frame
into a typed domain :class:`~src.domain.models.Action`, and turns the domain
:class:`~src.domain.models.TurnEvent` narrative back into JSON-safe dicts. The
domain never sees a bare ``dict``; the handler never hand-rolls JSON shapes.

Living in ``src/entrypoints/ws/``, this is the outer edge — it may import the
domain models freely. The hexagonal rule runs the other way: nothing here is
imported by ``domain/`` or ``application/``.

**Parse, don't validate.** :func:`parse_action` is strict — an unknown action
name, a missing/invalid direction, or a malformed ``item_id`` raises
:class:`ActionParseError` rather than constructing a half-valid action. The
handler catches it, returns an ``error`` frame, and keeps the loop alive (one
bad message must not kill the session).

**Wire shapes** (the contract the React client in Phase 5 will hardcode):

* inbound action — ``{"action": "<name>", ...params}`` where ``name`` is one of
  ``move | attack | wait | descend | abandon | pickup | use_item | open``;
  ``move``/``attack``/``open`` carry ``"direction"`` (a :class:`Direction`
  value), ``use_item`` carries ``"item_id"`` (a UUID string), the rest are bare.
* outbound event — ``{"type": "<snake_case>", ...fields}``; the discriminator
  mirrors each :class:`TurnEvent` variant. Positions cross the wire as ``[x, y]``
  arrays, matching the HTTP schema convention (``schemas.py``).
"""

from collections.abc import Mapping
from typing import Final
from uuid import UUID

from src.domain.models import (
    Abandon,
    Action,
    ActionRejected,
    Attack,
    Descend,
    Direction,
    EnemyAttacked,
    EnemyKilled,
    FloorDescended,
    Move,
    Open,
    PickUp,
    PlayerAttacked,
    PlayerDamaged,
    PlayerDied,
    PlayerMoved,
    RunAbandoned,
    TurnEvent,
    UseItem,
    Wait,
)

# Inbound action names that carry no parameters — built as bare variants.
_NULLARY_ACTIONS: Final[dict[str, Action]] = {
    "wait": Wait(),
    "descend": Descend(),
    "abandon": Abandon(),
    "pickup": PickUp(),
}


class ActionParseError(Exception):
    """An inbound frame could not be parsed into a typed :class:`Action`.

    Carries a short, client-safe message (the frame was malformed, named an
    unknown action, or omitted/mistyped a required field). The handler maps it
    to an ``{"type": "error", "detail": ...}`` frame and continues the loop —
    it is a *bad message*, not a connection-fatal fault.
    """


def parse_action(frame: object) -> Action:
    """Parse a decoded inbound JSON frame into a typed domain :class:`Action`.

    ``frame`` is the raw result of ``websocket.receive_json()`` (typed ``object``
    because JSON is untyped at the boundary). Raises :class:`ActionParseError`
    if it is not an object, lacks a string ``"action"``, names an unknown
    action, or omits/mistypes a required ``direction`` / ``item_id``.
    """
    if not isinstance(frame, Mapping):
        raise ActionParseError("frame must be a JSON object")
    name = frame.get("action")
    if not isinstance(name, str):
        raise ActionParseError("frame is missing a string 'action' field")

    if name in _NULLARY_ACTIONS:
        return _NULLARY_ACTIONS[name]
    match name:
        case "move":
            return Move(direction=_direction(frame))
        case "attack":
            return Attack(direction=_direction(frame))
        case "open":
            return Open(direction=_direction(frame))
        case "use_item":
            return UseItem(item_id=_item_id(frame))
        case _:
            raise ActionParseError(f"unknown action '{name}'")


def _direction(frame: Mapping[str, object]) -> Direction:
    """Extract a required :class:`Direction` from ``frame['direction']``."""
    raw = frame.get("direction")
    if not isinstance(raw, str):
        raise ActionParseError("action requires a string 'direction'")
    try:
        return Direction(raw)
    except ValueError as exc:
        valid = ", ".join(d.value for d in Direction)
        raise ActionParseError(f"invalid direction '{raw}' (expected one of {valid})") from exc


def _item_id(frame: Mapping[str, object]) -> UUID:
    """Extract a required UUID from ``frame['item_id']``."""
    raw = frame.get("item_id")
    if not isinstance(raw, str):
        raise ActionParseError("use_item requires a string 'item_id'")
    try:
        return UUID(raw)
    except ValueError as exc:
        raise ActionParseError(f"invalid item_id '{raw}' (expected a UUID)") from exc


def serialize_event(event: TurnEvent) -> dict[str, object]:
    """Serialise one :class:`TurnEvent` to a JSON-safe ``{"type": ..., ...}`` dict.

    The ``match`` is exhaustive over the ``TurnEvent`` union, so adding a new
    variant without a serialisation arm is a mypy-strict error (the point of the
    union). UUIDs become strings and ``(x, y)`` positions become ``[x, y]``
    arrays, matching the HTTP wire convention.
    """
    match event:
        case PlayerMoved(from_position=src, to_position=dst):
            return {"type": "player_moved", "from": list(src), "to": list(dst)}
        case PlayerAttacked(enemy_id=enemy_id, damage=damage, killed=killed):
            return {
                "type": "player_attacked",
                "enemy_id": str(enemy_id),
                "damage": damage,
                "killed": killed,
            }
        case EnemyAttacked(enemy_id=enemy_id, damage=damage):
            return {"type": "enemy_attacked", "enemy_id": str(enemy_id), "damage": damage}
        case PlayerDamaged(amount=amount):
            return {"type": "player_damaged", "amount": amount}
        case EnemyKilled(enemy_id=enemy_id):
            return {"type": "enemy_killed", "enemy_id": str(enemy_id)}
        case PlayerDied():
            return {"type": "player_died"}
        case FloorDescended(new_floor_index=index):
            return {"type": "floor_descended", "new_floor_index": index}
        case RunAbandoned():
            return {"type": "run_abandoned"}
        case ActionRejected(reason=reason):
            return {"type": "action_rejected", "reason": reason}


__all__ = ["ActionParseError", "parse_action", "serialize_event"]
