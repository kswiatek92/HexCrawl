"""Pydantic v2 request/response schemas for the HTTP game endpoints.

These are the **API contract** — the wire shape clients see — and live in the
entrypoints layer, the only place ``pydantic`` is allowed (CLAUDE.md → Code
conventions: "Pydantic v2 for all API schemas. Domain models are plain
dataclasses."). They are deliberately **separate** from the cache serializer in
``src/application/game_state.py``: that codec is the cache's internal concern,
and reusing it as the API contract would couple the HTTP surface to a storage
format on the far side of the hexagon. The translation from domain dataclass to
schema lives here, in the ``from_domain`` classmethods, so the route stays a thin
adapter and the domain never learns the wire shape exists.

Started for task 3.6 (`POST /game/start`); ``GameStateResponse`` is shared by
`GET /game/{id}` (task 3.7). Remaining schemas (abandon, leaderboard) land with
task 3.13.

Coordinate convention: positions cross the wire as ``[x, y]`` arrays (a 2-tuple
serialises to a JSON array), matching the domain's ``(x, y)`` facing API. Ground
items are keyed ``"x,y"`` strings because JSON object keys must be strings.
"""

from uuid import UUID

from pydantic import BaseModel, Field

from src.domain.models import (
    Dungeon,
    Enemy,
    Floor,
    Item,
    Player,
    TileType,
)

# A persisted seed lands in a signed-64-bit BIGINT column (adapters/db/models.py);
# the use case (``StartGame``) enforces the same bound. Validating here too makes
# an out-of-range seed a clean 422 at the edge before the use case runs.
_SEED_MIN = -(2**63)
_SEED_MAX = 2**63 - 1


class StartGameRequest(BaseModel):
    """Body for ``POST /game/start``.

    Carries no ``user_id``: identity comes from the verified bearer token
    (``AuthenticatedUser``), never the client body — a client must not be able
    to start a run as someone else. ``seed`` is optional (server-random by
    default); an explicit seed drives daily / shared-seed modes.
    """

    player_name: str = Field(min_length=1, max_length=32)
    seed: int | None = Field(default=None, ge=_SEED_MIN, le=_SEED_MAX)


class PlayerState(BaseModel):
    """Player view in a game-state response.

    Exposes gameplay-facing fields only — ``Player.user_id`` (identity) and
    ``Player.damage_taken`` (internal score-penalty accumulator) are omitted.
    """

    name: str
    position: tuple[int, int]
    hp: int
    max_hp: int
    attack: int
    defense: int

    @classmethod
    def from_domain(cls, player: Player) -> "PlayerState":
        return cls(
            name=player.name,
            position=player.position,
            hp=player.hp,
            max_hp=player.max_hp,
            attack=player.attack,
            defense=player.defense,
        )


class EnemyState(BaseModel):
    """An enemy on the current floor."""

    enemy_id: UUID
    name: str
    position: tuple[int, int]
    behaviour: str
    hp: int
    max_hp: int
    attack: int
    defense: int
    awake: bool

    @classmethod
    def from_domain(cls, enemy: Enemy) -> "EnemyState":
        return cls(
            enemy_id=enemy.enemy_id,
            name=enemy.name,
            position=enemy.position,
            behaviour=enemy.behaviour.value,
            hp=enemy.hp,
            max_hp=enemy.max_hp,
            attack=enemy.attack,
            defense=enemy.defense,
            awake=enemy.awake,
        )


class ItemState(BaseModel):
    """A ground item (stack) in a game-state response."""

    item_id: UUID
    name: str
    item_type: str
    effect: int
    count: int

    @classmethod
    def from_domain(cls, item: Item) -> "ItemState":
        return cls(
            item_id=item.item_id,
            name=item.name,
            item_type=item.item_type.value,
            effect=item.effect,
            count=item.count,
        )


class FloorState(BaseModel):
    """The current floor's geometry and contents, ready for the client to render.

    ``tiles`` is row-major (``tiles[y][x]``, ``TileType`` values as strings).
    ``items`` is keyed ``"x,y"`` (JSON keys are strings); each value is the stack
    on that tile.
    """

    width: int
    height: int
    tiles: list[list[TileType]]
    enemies: list[EnemyState]
    items: dict[str, list[ItemState]]
    stairs_down: tuple[int, int]

    @classmethod
    def from_domain(cls, floor: Floor) -> "FloorState":
        height = len(floor.tiles)
        width = len(floor.tiles[0]) if floor.tiles else 0
        return cls(
            width=width,
            height=height,
            tiles=floor.tiles,
            enemies=[EnemyState.from_domain(e) for e in floor.enemies],
            items={
                f"{x},{y}": [ItemState.from_domain(i) for i in stack]
                for (x, y), stack in floor.items.items()
            },
            stairs_down=floor.stairs_down,
        )


class GameStateResponse(BaseModel):
    """Full state of a run: identifiers, seed, and the current floor + player.

    Returned by ``POST /game/start`` (201, with a ``Location`` header) and, from
    task 3.7, by ``GET /game/{id}``. Carries the *current* floor only — the run's
    other floors are regenerable from ``(seed, index)`` and not part of the
    playable view.
    """

    game_id: UUID
    seed: int
    current_floor_index: int
    turn_count: int
    player: PlayerState
    floor: FloorState

    @classmethod
    def from_domain(cls, dungeon: Dungeon, player: Player) -> "GameStateResponse":
        current_floor = dungeon.floors[dungeon.current_floor_index]
        return cls(
            game_id=dungeon.dungeon_id,
            seed=dungeon.seed,
            current_floor_index=dungeon.current_floor_index,
            turn_count=dungeon.turn_count,
            player=PlayerState.from_domain(player),
            floor=FloorState.from_domain(current_floor),
        )
