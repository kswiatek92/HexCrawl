"""Active-game-state cache contract: key, TTL, and serialisation.

HexCrawl keeps the *hot* state of a running game — the ``(Dungeon, Player)``
pair the turn loop mutates every move — in Redis, not Postgres (CLAUDE.md →
"Active game state lives in Redis (TTL 2h)"). Postgres holds the durable
checkpoint; Redis holds the working copy so ``ProcessTurn`` (task 3.2) can
read and write turn-by-turn without a relational round-trip.

This module is the single home for *how* that cache entry is shaped:

* the **key** every consumer agrees on (``game:{game_id}``),
* the **TTL** every write uses, and
* the **serialisation** of the domain pair to the ``str`` the cache port
  speaks.

Per :mod:`src.domain.ports.cache_port` (docstring "Use cases own
serialisation, not the cache adapter"), the conversion lives *here* in the
application layer, never in the Redis adapter — the adapter stays a generic
``str`` store that imports no domain type. This module is bound by the
hexagonal rule: it imports domain models only, never an adapter or a
framework.

The on-the-wire shape mirrors the relational JSONB layout the DB adapter
uses (``src/adapters/db/game_repository.py``) so the two stay mentally in
sync: ``tiles`` as nested wire-strings (``TileType`` is a ``StrEnum``),
ground ``items`` keyed ``"x,y"`` (JSON object keys must be strings),
``(x, y)`` positions as ``[x, y]`` arrays, and UUIDs as their ``str`` form.
The two codecs are deliberately *not* shared: they sit on opposite sides of
the hexagon (application vs adapter), and coupling them would drag a
framework dependency across the boundary.

Both directions live here. ``serialize_game_state`` is the write side
(``StartGame`` 3.1 seeds the initial blob; ``ProcessTurn`` 3.2 rewrites it
each turn); ``deserialize_game_state`` is the read side ``ProcessTurn`` (3.2)
uses to load the active run before mutating it. The two are exact inverses
over the wire format documented above — :func:`deserialize_game_state` of
:func:`serialize_game_state` round-trips to an equal ``(Dungeon, Player)``.
"""

import json
from typing import Final, cast
from uuid import UUID

from src.domain.models import (
    BehaviourType,
    Dungeon,
    Enemy,
    Floor,
    Item,
    ItemType,
    Player,
    TileType,
)

# 2 hours, matching CLAUDE.md's "TTL 2h" for active game state. A run that
# goes idle past this window expires from the cache and is rebuilt from the
# Postgres checkpoint on the next access.
GAME_STATE_TTL_SECONDS: Final[int] = 7200


def game_state_cache_key(game_id: UUID) -> str:
    """Return the cache key for a run's active state.

    ``game_id`` is ``Dungeon.dungeon_id`` — the same value the external
    ``/game/{id}`` and ``/ws/game/{session_id}`` vocabulary uses. The
    ``game:`` prefix namespaces run state away from the leaderboard slices
    that share the same Redis instance.
    """
    return f"game:{game_id}"


def serialize_game_state(dungeon: Dungeon, player: Player) -> str:
    """Serialise the ``(dungeon, player)`` pair to a JSON string for the cache.

    The inverse (``ProcessTurn``, task 3.2) reads this exact shape back. See
    the module docstring for the wire-format conventions.
    """
    payload: dict[str, object] = {
        "dungeon": _dungeon_to_dict(dungeon),
        "player": _player_to_dict(player),
    }
    return json.dumps(payload)


def deserialize_game_state(blob: str) -> tuple[Dungeon, Player]:
    """Rebuild the ``(dungeon, player)`` pair from a cached JSON string.

    The exact inverse of :func:`serialize_game_state`: it consumes the wire
    format documented in the module docstring and reconstructs the domain
    dataclasses (UUIDs from their ``str`` form, ``(x, y)`` tuples from
    ``[x, y]`` arrays, ``StrEnum`` members from their wire strings, the
    ground-items dict from its ``"x,y"`` keys). ``ProcessTurn`` (3.2) calls
    this to load the active run from the cache before mutating it.

    ``json.loads`` is untyped (its result is ``Any``); rather than annotate
    ``Any`` — forbidden in the application layer — the parsed values are
    narrowed to concrete types with localized :func:`cast` at each branch.
    A malformed blob (missing key, wrong shape) raises ``KeyError`` /
    ``ValueError`` from the conversions, which the caller treats as a
    corrupt cache entry — not a normal outcome.
    """
    payload = json.loads(blob)
    dungeon = _dungeon_from_dict(cast("dict[str, object]", payload["dungeon"]))
    player = _player_from_dict(cast("dict[str, object]", payload["player"]))
    return dungeon, player


def _dungeon_to_dict(dungeon: Dungeon) -> dict[str, object]:
    return {
        "dungeon_id": str(dungeon.dungeon_id),
        "seed": dungeon.seed,
        "current_floor_index": dungeon.current_floor_index,
        "turn_count": dungeon.turn_count,
        "floors": [_floor_to_dict(floor) for floor in dungeon.floors],
    }


def _floor_to_dict(floor: Floor) -> dict[str, object]:
    return {
        "floor_id": str(floor.floor_id),
        # TileType is a StrEnum, so each member already *is* its wire string;
        # json.dumps would emit it directly, but .value keeps the typed dict
        # honest (list[list[str]] rather than list[list[TileType]]).
        "tiles": [[tile.value for tile in row] for row in floor.tiles],
        "enemies": [_enemy_to_dict(enemy) for enemy in floor.enemies],
        "items": _items_to_dict(floor.items),
        "stairs_down": list(floor.stairs_down),
    }


def _enemy_to_dict(enemy: Enemy) -> dict[str, object]:
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


def _items_to_dict(
    items: dict[tuple[int, int], list[Item]],
) -> dict[str, object]:
    # Ground items are keyed by an (x, y) tuple; JSON object keys must be
    # strings, so the position becomes "x,y" (matching the DB adapter).
    return {f"{x},{y}": [_item_to_dict(item) for item in stack] for (x, y), stack in items.items()}


def _item_to_dict(item: Item) -> dict[str, object]:
    return {
        "item_id": str(item.item_id),
        "name": item.name,
        "item_type": item.item_type.value,
        "effect": item.effect,
        "count": item.count,
    }


def _player_to_dict(player: Player) -> dict[str, object]:
    return {
        "user_id": str(player.user_id),
        "name": player.name,
        "position": list(player.position),
        "hp": player.hp,
        "max_hp": player.max_hp,
        "attack": player.attack,
        "defense": player.defense,
        "damage_taken": player.damage_taken,
    }


# --- decode: the inverse of the _*_to_dict encoders above ------------------


def _position_from_list(data: object) -> tuple[int, int]:
    # Positions serialise as a 2-element [x, y] array; JSON has no tuple type,
    # so rebuild the (x, y) tuple the domain models expect.
    x, y = cast("list[int]", data)
    return (x, y)


def _dungeon_from_dict(data: dict[str, object]) -> Dungeon:
    floors = cast("list[dict[str, object]]", data["floors"])
    return Dungeon(
        dungeon_id=UUID(cast("str", data["dungeon_id"])),
        seed=cast("int", data["seed"]),
        floors=[_floor_from_dict(floor) for floor in floors],
        current_floor_index=cast("int", data["current_floor_index"]),
        turn_count=cast("int", data["turn_count"]),
    )


def _floor_from_dict(data: dict[str, object]) -> Floor:
    tiles = cast("list[list[str]]", data["tiles"])
    enemies = cast("list[dict[str, object]]", data["enemies"])
    return Floor(
        floor_id=UUID(cast("str", data["floor_id"])),
        tiles=[[TileType(value) for value in row] for row in tiles],
        enemies=[_enemy_from_dict(enemy) for enemy in enemies],
        items=_items_from_dict(cast("dict[str, object]", data["items"])),
        stairs_down=_position_from_list(data["stairs_down"]),
    )


def _enemy_from_dict(data: dict[str, object]) -> Enemy:
    return Enemy(
        enemy_id=UUID(cast("str", data["enemy_id"])),
        name=cast("str", data["name"]),
        position=_position_from_list(data["position"]),
        behaviour=BehaviourType(cast("str", data["behaviour"])),
        hp=cast("int", data["hp"]),
        max_hp=cast("int", data["max_hp"]),
        attack=cast("int", data["attack"]),
        defense=cast("int", data["defense"]),
        awake=cast("bool", data["awake"]),
    )


def _items_from_dict(
    data: dict[str, object],
) -> dict[tuple[int, int], list[Item]]:
    # Ground items are keyed "x,y" on the wire (JSON object keys must be
    # strings); split each back into the (x, y) tuple the domain dict uses.
    result: dict[tuple[int, int], list[Item]] = {}
    for key, stack in data.items():
        x_str, y_str = key.split(",")
        items = cast("list[dict[str, object]]", stack)
        result[(int(x_str), int(y_str))] = [_item_from_dict(item) for item in items]
    return result


def _item_from_dict(data: dict[str, object]) -> Item:
    return Item(
        item_id=UUID(cast("str", data["item_id"])),
        name=cast("str", data["name"]),
        item_type=ItemType(cast("str", data["item_type"])),
        effect=cast("int", data["effect"]),
        count=cast("int", data["count"]),
    )


def _player_from_dict(data: dict[str, object]) -> Player:
    return Player(
        user_id=UUID(cast("str", data["user_id"])),
        name=cast("str", data["name"]),
        position=_position_from_list(data["position"]),
        hp=cast("int", data["hp"]),
        max_hp=cast("int", data["max_hp"]),
        attack=cast("int", data["attack"]),
        defense=cast("int", data["defense"]),
        damage_taken=cast("int", data["damage_taken"]),
    )
