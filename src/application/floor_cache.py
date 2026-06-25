"""Pre-generated-floor cache contract + the shared ``Floor`` wire codec.

Two things live here, both in the application layer per the hexagonal rule
(CLAUDE.md → cache "Serialisation lives in the application layer, never in the
cache adapter"):

1. **The pre-generation cache contract** — the key, TTL, and ``Floor``↔string
   serialisation the ``map_generation`` worker (task 4.3) uses to stash a
   deep floor in Redis for the descent path to pick up. Deep-floor BSP is
   CPU-bound and is generated off the turn loop in a Celery worker; the result
   is a fully-rendered ``Floor`` (QUESTIONS.md ``:104``: cache the floor, not
   just the seed — caching the seed would offload no work since the consumer
   would still have to run BSP on descent).

2. **The canonical ``Floor`` wire codec** (``floor_to_dict`` / ``floor_from_dict``
   and the enemy/item/position helpers). This is the *single source of truth* for
   how a ``Floor`` is shaped on the wire. :mod:`src.application.game_state` imports
   it for the active ``(Dungeon, Player)`` blob, and this module's
   :func:`serialize_floor` uses it for the standalone pre-gen blob. They MUST agree:
   a pre-generated floor is later spliced into the live dungeon and re-serialised by
   ``game_state``, so a divergent shape would be a latent corruption bug. One codec,
   one shape.

The wire-format conventions (shared with ``game_state`` and the DB adapter): ``tiles``
as nested wire-strings (``TileType`` is a ``StrEnum``), ground ``items`` keyed ``"x,y"``
(JSON object keys must be strings), ``(x, y)`` positions as ``[x, y]`` arrays, and UUIDs
as their ``str`` form.

Bound by the hexagonal golden rule: imports domain models only — never an adapter, never
a framework.
"""

import json
from typing import Final, cast
from uuid import UUID

from src.domain.models import (
    BehaviourType,
    Enemy,
    Floor,
    Item,
    ItemType,
    TileType,
)

# 2 hours, matching the active-game-state TTL (``game_state.GAME_STATE_TTL_SECONDS``).
# A pre-generated floor the player never reaches — e.g. they die before descending —
# is cleaned up by this expiry, not an explicit delete (QUIZZES.md 4.3 Q4: TTL cleanup
# is more robust than relying on a delete that a crash or an orphaned run would skip).
PREGEN_FLOOR_TTL_SECONDS: Final[int] = 7200


def pregenerated_floor_cache_key(game_id: UUID, floor_index: int) -> str:
    """Return the cache key for a run's pre-generated floor at ``floor_index``.

    The ``floor:`` prefix namespaces pre-gen entries away from the ``game:``
    active-state blob and the ``leaderboard:`` slices that share the same Redis
    instance. Keyed per ``(game_id, floor_index)`` so each run's deep floors are
    distinct entries the worker can write and the descent path can poll.
    """
    return f"floor:{game_id}:{floor_index}"


def serialize_floor(floor: Floor) -> str:
    """Serialise a single ``Floor`` to a JSON string for the cache.

    The inverse is :func:`deserialize_floor`. Uses the shared :func:`floor_to_dict`
    codec so the shape matches the floors inside the ``game_state`` active blob.
    """
    return json.dumps(floor_to_dict(floor))


def deserialize_floor(blob: str) -> Floor:
    """Rebuild a ``Floor`` from a cached JSON string — the inverse of
    :func:`serialize_floor`.

    A malformed blob raises from the conversions (``KeyError`` / ``ValueError`` /
    ``TypeError``); the caller treats any of these as a corrupt cache entry, not a
    normal outcome (same convention as ``game_state.deserialize_game_state``).
    """
    return floor_from_dict(cast("dict[str, object]", json.loads(blob)))


# --- shared Floor wire codec (also consumed by game_state) -----------------


def floor_to_dict(floor: Floor) -> dict[str, object]:
    return {
        "floor_id": str(floor.floor_id),
        # TileType is a StrEnum, so each member already *is* its wire string;
        # json.dumps would emit it directly, but .value keeps the typed dict
        # honest (list[list[str]] rather than list[list[TileType]]).
        "tiles": [[tile.value for tile in row] for row in floor.tiles],
        "enemies": [enemy_to_dict(enemy) for enemy in floor.enemies],
        "items": items_to_dict(floor.items),
        "stairs_down": list(floor.stairs_down),
    }


def enemy_to_dict(enemy: Enemy) -> dict[str, object]:
    return {
        "enemy_id": str(enemy.enemy_id),
        "name": enemy.name,
        "position": list(enemy.position),
        "behaviour": enemy.behaviour.value,
        "hp": enemy.hp,
        "max_hp": enemy.max_hp,
        "attack": enemy.attack,
        "defense": enemy.defense,
        "awake": enemy.awake,
    }


def items_to_dict(
    items: dict[tuple[int, int], list[Item]],
) -> dict[str, object]:
    # Ground items are keyed by an (x, y) tuple; JSON object keys must be
    # strings, so the position becomes "x,y" (matching the DB adapter).
    return {f"{x},{y}": [item_to_dict(item) for item in stack] for (x, y), stack in items.items()}


def item_to_dict(item: Item) -> dict[str, object]:
    return {
        "item_id": str(item.item_id),
        "name": item.name,
        "item_type": item.item_type.value,
        "effect": item.effect,
        "count": item.count,
    }


def position_from_list(data: object) -> tuple[int, int]:
    # Positions serialise as a 2-element [x, y] array; JSON has no tuple type,
    # so rebuild the (x, y) tuple the domain models expect.
    x, y = cast("list[int]", data)
    return (x, y)


def floor_from_dict(data: dict[str, object]) -> Floor:
    tiles = cast("list[list[str]]", data["tiles"])
    enemies = cast("list[dict[str, object]]", data["enemies"])
    return Floor(
        floor_id=UUID(cast("str", data["floor_id"])),
        tiles=[[TileType(value) for value in row] for row in tiles],
        enemies=[enemy_from_dict(enemy) for enemy in enemies],
        items=items_from_dict(cast("dict[str, object]", data["items"])),
        stairs_down=position_from_list(data["stairs_down"]),
    )


def enemy_from_dict(data: dict[str, object]) -> Enemy:
    return Enemy(
        enemy_id=UUID(cast("str", data["enemy_id"])),
        name=cast("str", data["name"]),
        position=position_from_list(data["position"]),
        behaviour=BehaviourType(cast("str", data["behaviour"])),
        hp=cast("int", data["hp"]),
        max_hp=cast("int", data["max_hp"]),
        attack=cast("int", data["attack"]),
        defense=cast("int", data["defense"]),
        awake=cast("bool", data["awake"]),
    )


def items_from_dict(
    data: dict[str, object],
) -> dict[tuple[int, int], list[Item]]:
    # Ground items are keyed "x,y" on the wire (JSON object keys must be
    # strings); split each back into the (x, y) tuple the domain dict uses.
    result: dict[tuple[int, int], list[Item]] = {}
    for key, stack in data.items():
        x_str, y_str = key.split(",")
        items = cast("list[dict[str, object]]", stack)
        result[(int(x_str), int(y_str))] = [item_from_dict(item) for item in items]
    return result


def item_from_dict(data: dict[str, object]) -> Item:
    return Item(
        item_id=UUID(cast("str", data["item_id"])),
        name=cast("str", data["name"]),
        item_type=ItemType(cast("str", data["item_type"])),
        effect=cast("int", data["effect"]),
        count=cast("int", data["count"]),
    )
