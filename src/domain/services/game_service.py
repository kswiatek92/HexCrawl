"""``GameService.process_turn`` — the core domain turn loop.

Resolves one player ``Action`` plus the subsequent enemy AI round into
state mutations on the input ``Dungeon`` / ``Player`` / current ``Floor``
plus an event log. Returns a ``TurnResult(events, game_over)``; the
dungeon, player, and floor are mutated in place per the v1 mutation
decision (``QUESTIONS.md`` task 1.16). Callers — the WebSocket
entrypoint in task 3.9, tests today — pass the same instances each
turn; ``process_turn`` is the only sanctioned mutator.

Design intent (all locked in ``QUESTIONS.md`` task 1.16):

* **Pure modulo input mutation.** The function is deterministic in its
  inputs (no global state, no clock, no module-level RNG) but mutates
  the inputs in place; the ``TurnResult`` is the *narrative* of the
  mutation, not a new state object. Tests assert both: state after the
  call, and the event list returned.
* **Per-turn seeded RNG.** Derived inside the function from
  ``(dungeon.seed, current_floor_index, turn_count)`` — same pattern as
  ``DungeonGenerator``. ``turn_count`` is bumped at the very end of the
  turn so the *current* turn uses the value the dungeon was loaded
  with. Replay is feasible from ``(seed, action log)`` alone — the RNG
  has no hidden state.
* **Interleaved enemy order.** After the player's action resolves,
  enemies act one at a time in ``enemy_id`` sort order. Each enemy
  reads the latest state (including state changes from enemies that
  have already acted this turn) before deciding via
  ``enemy_ai.decide_action``. Sort by id (not list order) so replay
  doesn't depend on list-mutation history.
* **Action dispatch via ``match``.** mypy-strict checks exhaustiveness;
  adding a new ``Action`` variant without adding an arm here is a
  compile-time error. The ``case _:`` catch-all is therefore omitted
  on purpose.
* **Domain events, not side effects.** ``process_turn`` knows nothing
  about WebSockets, Redis, Celery, or persistence. It mutates and
  emits; later layers translate events into wire frames, cache writes,
  task enqueues. See ``turn_event.py``.

v1 scope: ``Move``, ``Attack`` (explicit cardinal), ``Wait``,
``Descend``, ``Abandon`` are fully implemented. ``PickUp`` /
``UseItem`` / ``Open`` return ``ActionRejected(reason="not_implemented_v1")``
because the data they depend on (player inventory slots, open-door tile
state) is not yet on the dataclasses. The match arms still exist so the
exhaustiveness check holds — those branches activate naturally when the
backing model lands.
"""

import random
from dataclasses import dataclass, field
from typing import Final

from src.domain.models.action import (
    Abandon,
    Action,
    Attack,
    Descend,
    Direction,
    Move,
    Open,
    PickUp,
    UseItem,
    Wait,
)
from src.domain.models.dungeon import Dungeon
from src.domain.models.enemy import Enemy
from src.domain.models.floor import Floor
from src.domain.models.player import Player
from src.domain.models.tile_type import TileType
from src.domain.models.turn_event import (
    ActionRejected,
    EnemyAttacked,
    EnemyKilled,
    FloorDescended,
    PlayerAttacked,
    PlayerDamaged,
    PlayerDied,
    PlayerMoved,
    RunAbandoned,
    TurnEvent,
)
from src.domain.services.enemy_ai import decide_action as ai_decide
from src.domain.services.spawn import spawn_position

_DAMAGE_VARIANCE: Final[int] = 1  # symmetric ±1 swing per hit
_MIN_DAMAGE: Final[int] = 1  # floor so armor-stacking can't trivialise combat

_DIRECTION_OFFSETS: Final[dict[Direction, tuple[int, int]]] = {
    Direction.NORTH: (0, -1),
    Direction.EAST: (1, 0),
    Direction.SOUTH: (0, 1),
    Direction.WEST: (-1, 0),
}

# Tiles that block player/enemy movement. ``DOOR`` blocks until the
# ``Open`` action's data model lands; until then the generator does not
# emit DOORs, so this is a forward-compatible default.
_MOVEMENT_BLOCKERS: Final[frozenset[TileType]] = frozenset({TileType.WALL, TileType.DOOR})


@dataclass
class TurnResult:
    """Narrative + termination flag returned by ``process_turn``.

    ``events`` is ordered: events earlier in the list happened earlier
    in the turn, so a consumer can replay them as an animation queue.
    ``game_over`` is ``True`` when the run terminated this turn (player
    died, player abandoned, or — future — completed the final floor);
    callers should not call ``process_turn`` again on the same dungeon
    after seeing ``game_over=True``.

    Not frozen because the use-case layer is allowed to append events
    of its own after the turn (e.g. ``ScoreComputed``) before forwarding
    to the entrypoint. ``Score`` is frozen for the opposite reason —
    it's a published snapshot.
    """

    events: list[TurnEvent] = field(default_factory=list)
    game_over: bool = False


def process_turn(dungeon: Dungeon, player: Player, action: Action) -> TurnResult:
    """Resolve one turn: player action, enemy AI loop, end-of-turn bookkeeping.

    Mutates ``dungeon`` (``turn_count``, possibly ``current_floor_index``),
    ``player`` (position, hp, damage_taken), and the current ``Floor``
    (enemy positions, enemy hp, enemy awake) in place. Returns a
    ``TurnResult`` whose ``events`` list is the per-turn narrative and
    whose ``game_over`` flag terminates the run.

    Precondition: ``dungeon.current_floor_index`` indexes a valid floor
    in ``dungeon.floors``; if it does not, ``IndexError`` propagates —
    that is a caller-side bug, not a domain outcome.
    """
    result = TurnResult()
    floor = dungeon.floors[dungeon.current_floor_index]
    rng = _per_turn_rng(dungeon)

    match action:
        case Move(direction=d):
            _player_move(player, floor, d, rng, result)
        case Attack(direction=d):
            _player_attack(player, floor, d, rng, result)
        case Wait():
            pass
        case Descend():
            _player_descend(dungeon, player, floor, result)
        case Abandon():
            result.events.append(RunAbandoned())
            result.game_over = True
        case PickUp() | UseItem() | Open():
            result.events.append(ActionRejected(reason="not_implemented_v1"))

    # End-of-run short-circuits skip the enemy AI loop; events ordering
    # would otherwise be misleading (e.g. an attack landing after the
    # player has already abandoned).
    if not result.game_over:
        _run_enemy_ai(dungeon, player, rng, result)

    dungeon.turn_count += 1
    return result


def _per_turn_rng(dungeon: Dungeon) -> random.Random:
    """Construct a deterministic per-turn RNG.

    Mirrors ``DungeonGenerator``: a string seed of
    ``"{seed}|{current_floor_index}|{turn_count}"`` is fed to
    ``random.Random``, which internally SHA-512-hashes it. The same
    triple always produces the same RNG state — that is what makes
    seeded-equality tests of combat outcomes possible.
    """
    return random.Random(f"{dungeon.seed}|{dungeon.current_floor_index}|{dungeon.turn_count}")


def _player_move(
    player: Player,
    floor: Floor,
    direction: Direction,
    rng: random.Random,
    result: TurnResult,
) -> None:
    """Resolve ``Move(direction)``: walk, attack on enemy, or reject.

    Move-into-enemy resolves to an attack via the ``Action`` contract
    (task 1.9). The attack uses the same damage roll as an explicit
    ``Attack`` action; the player does *not* also step onto the
    enemy's tile — only one event fires per Move.
    """
    dx, dy = _DIRECTION_OFFSETS[direction]
    target = (player.position[0] + dx, player.position[1] + dy)

    rejection = _rejection_for_target(floor, target, allow_enemy=True)
    if rejection is not None:
        result.events.append(rejection)
        return

    enemy = _enemy_at(floor, target)
    if enemy is not None:
        _resolve_player_attack(player, enemy, floor, rng, result)
        return

    from_pos = player.position
    player.position = target
    result.events.append(PlayerMoved(from_position=from_pos, to_position=target))


def _player_attack(
    player: Player,
    floor: Floor,
    direction: Direction,
    rng: random.Random,
    result: TurnResult,
) -> None:
    """Resolve explicit ``Attack(direction)``: must target an enemy.

    Validates the target tile against the same OOB / wall / door rules
    as ``Move`` first, so the rejection reason matches the actual
    failure mode — attacking into a wall surfaces ``blocked_by_wall``,
    not the misleading ``nothing_to_attack``. Only an in-bounds,
    non-blocking tile that holds no enemy yields ``nothing_to_attack``.
    """
    dx, dy = _DIRECTION_OFFSETS[direction]
    target = (player.position[0] + dx, player.position[1] + dy)
    rejection = _rejection_for_target(floor, target, allow_enemy=True)
    if rejection is not None:
        result.events.append(rejection)
        return
    enemy = _enemy_at(floor, target)
    if enemy is None:
        result.events.append(ActionRejected(reason="nothing_to_attack"))
        return
    _resolve_player_attack(player, enemy, floor, rng, result)


def _player_descend(
    dungeon: Dungeon,
    player: Player,
    floor: Floor,
    result: TurnResult,
) -> None:
    """Resolve ``Descend``: must stand on STAIRS and have a next floor."""
    if floor.tiles[player.position[1]][player.position[0]] is not TileType.STAIRS:
        result.events.append(ActionRejected(reason="not_on_stairs"))
        return
    next_index = dungeon.current_floor_index + 1
    if next_index >= len(dungeon.floors):
        # Pre-generation of the next floor is StartGame/Celery's job
        # (task 4.3 map_generation). The turn loop refuses rather than
        # generating in-line — keeping process_turn cheap and synchronous.
        result.events.append(ActionRejected(reason="no_next_floor"))
        return
    dungeon.current_floor_index = next_index
    new_floor = dungeon.floors[next_index]
    player.position = spawn_position(new_floor)
    result.events.append(FloorDescended(new_floor_index=next_index))


def _run_enemy_ai(
    dungeon: Dungeon,
    player: Player,
    rng: random.Random,
    result: TurnResult,
) -> None:
    """Each living enemy on the current floor acts, in ``enemy_id`` order.

    Sort by id (not list position) so replay reproduction does not
    depend on enemy spawn / removal history. Iterates a snapshot so the
    floor's enemy list can be mutated mid-loop without invalidating the
    iteration (currently only via ``EnemyKilled`` removing the entry).
    The player-death check after each enemy's action short-circuits the
    rest of the loop — letting dead-player turns continue would just
    pile cosmetic events onto a terminated run.
    """
    floor = dungeon.floors[dungeon.current_floor_index]
    snapshot = sorted(floor.enemies, key=lambda e: e.enemy_id)
    for enemy in snapshot:
        if enemy.hp <= 0:
            # Killed earlier this turn (player's action). Skip cleanly.
            continue
        ai_action, new_awake = ai_decide(enemy, player, floor, awake=enemy.awake)
        enemy.awake = new_awake
        _apply_enemy_action(enemy, player, floor, ai_action, rng, result)
        if player.hp <= 0:
            result.events.append(PlayerDied())
            result.game_over = True
            return


def _apply_enemy_action(
    enemy: Enemy,
    player: Player,
    floor: Floor,
    action: Action,
    rng: random.Random,
    result: TurnResult,
) -> None:
    """Apply one enemy's chosen action to the world.

    Enemy AI emits ``Move`` and ``Wait`` only (today). The catch-all arm
    for the other ``Action`` variants is deliberately a silent no-op:
    an enemy-side AI bug should not surface as a client-visible
    ``ActionRejected`` event (the player's action wasn't rejected, the
    AI just misbehaved), and raising would kill the WebSocket session
    over a recoverable issue. The exhaustive match keeps mypy-strict
    happy without any visible domain artefact.
    """
    match action:
        case Move(direction=d):
            _enemy_step_or_attack(enemy, player, floor, d, rng, result)
        case Wait():
            return
        case Attack() | Descend() | Abandon() | PickUp() | UseItem() | Open():
            # The AI shouldn't pick these; treat as a no-op rather than
            # raising — an exception here would kill the WebSocket
            # session for a recoverable AI bug.
            return


def _enemy_step_or_attack(
    enemy: Enemy,
    player: Player,
    floor: Floor,
    direction: Direction,
    rng: random.Random,
    result: TurnResult,
) -> None:
    """Enemy ``Move`` resolves to attack-on-player or step-into-floor.

    Mirrors player Move semantics but from the enemy's side. An enemy
    cannot move onto another enemy's tile — the AI may have planned a
    path that conflicts after a peer enemy already moved this turn, so
    we double-check at apply-time and degrade to a no-op rather than
    forcing overlap.
    """
    dx, dy = _DIRECTION_OFFSETS[direction]
    target = (enemy.position[0] + dx, enemy.position[1] + dy)

    if target == player.position:
        _resolve_enemy_attack(enemy, player, rng, result)
        return

    if not _in_bounds(floor, target):
        return
    if floor.tiles[target[1]][target[0]] in _MOVEMENT_BLOCKERS:
        return
    if _enemy_at(floor, target) is not None:
        return

    enemy.position = target


def _resolve_player_attack(
    player: Player,
    enemy: Enemy,
    floor: Floor,
    rng: random.Random,
    result: TurnResult,
) -> None:
    """Roll damage, apply to enemy, emit events, prune corpse if killed."""
    damage = _roll_damage(player.attack, enemy.defense, rng)
    enemy.hp -= damage
    killed = enemy.hp <= 0
    result.events.append(PlayerAttacked(enemy_id=enemy.enemy_id, damage=damage, killed=killed))
    if killed:
        result.events.append(EnemyKilled(enemy_id=enemy.enemy_id))
        floor.enemies.remove(enemy)


def _resolve_enemy_attack(
    enemy: Enemy,
    player: Player,
    rng: random.Random,
    result: TurnResult,
) -> None:
    """Roll damage, apply to player, emit attack + damage events."""
    damage = _roll_damage(enemy.attack, player.defense, rng)
    player.hp -= damage
    player.damage_taken += damage
    result.events.append(EnemyAttacked(enemy_id=enemy.enemy_id, damage=damage))
    result.events.append(PlayerDamaged(amount=damage))


def _roll_damage(attack: int, defense: int, rng: random.Random) -> int:
    """``max(_MIN_DAMAGE, attack + uniform(-1, 1) - defense)``.

    The floor at ``_MIN_DAMAGE`` (=1) is what prevents armor-stacking
    "0 damage forever" lockouts that would otherwise let a high-defense
    player walk through floor 100 untouched. Variance ±1 keeps combat
    predictable enough to plan while still feeling alive.
    """
    variance = rng.randint(-_DAMAGE_VARIANCE, _DAMAGE_VARIANCE)
    return max(_MIN_DAMAGE, attack + variance - defense)


def _rejection_for_target(
    floor: Floor,
    target: tuple[int, int],
    *,
    allow_enemy: bool,
) -> ActionRejected | None:
    """Return an ``ActionRejected`` if ``target`` is not a valid Move dest.

    ``allow_enemy=True`` (Move semantics) treats enemy-occupied tiles
    as valid — they resolve to an attack in the caller. ``False`` is
    reserved for actions that strictly need an empty tile (none in v1).
    """
    if not _in_bounds(floor, target):
        return ActionRejected(reason="out_of_bounds")
    tile = floor.tiles[target[1]][target[0]]
    if tile is TileType.WALL:
        return ActionRejected(reason="blocked_by_wall")
    if tile is TileType.DOOR:
        return ActionRejected(reason="blocked_by_door")
    if not allow_enemy and _enemy_at(floor, target) is not None:
        return ActionRejected(reason="blocked_by_enemy")
    return None


def _in_bounds(floor: Floor, target: tuple[int, int]) -> bool:
    height = len(floor.tiles)
    if height == 0:
        return False
    width = len(floor.tiles[0])
    x, y = target
    return 0 <= x < width and 0 <= y < height


def _enemy_at(floor: Floor, position: tuple[int, int]) -> Enemy | None:
    for enemy in floor.enemies:
        if enemy.position == position:
            return enemy
    return None
