"""Domain events emitted by ``GameService.process_turn``.

A ``TurnEvent`` is a record of "something happened during this turn".
``process_turn`` mutates the dungeon/player/floor in place *and* returns
a list of events in the order they occurred — mutation carries state,
events carry narrative. The two-track output buys three properties at
once:

* **Decoupled WebSocket layer.** Task 3.9's entrypoint serialises the
  event list to the client without reaching into ``GameService``
  internals — adding a new event variant updates the entrypoint
  serialiser, not the turn loop.
* **Replay feasibility.** The event log is the run log: replaying a run
  is re-emitting the same events from the same seed + action sequence.
* **Use-case dispatch.** Phases 2–3 wire side effects (Celery score
  recalc, leaderboard cache invalidation) onto specific events without
  the turn loop importing those layers.

Every variant is ``@dataclass(frozen=True)`` for the same reasons as
``Action`` (see ``action.py``): events are recorded once and never
mutated after emission. Frozen dataclasses are hashable, so a turn log
keyed on ``(session_id, turn_n)`` can use them as values without custom
hashing.

The ``TurnEvent`` union is exhaustively matched by the entrypoint
serialiser; adding a new variant without updating every match arm fails
mypy-strict — which is the point. Variants here are the v1 surface;
``PickUpFailed``, ``EnemySpawned``, ``BossPhaseChanged``, etc. slot in
additively in later phases.
"""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class PlayerMoved:
    """Player walked from ``from_position`` to ``to_position``.

    Emitted when a ``Move`` action resolves to a walk (i.e. the target
    tile was not enemy-occupied). Move-into-enemy resolves to a
    ``PlayerAttacked`` instead — never both for the same action.
    """

    from_position: tuple[int, int]
    to_position: tuple[int, int]


@dataclass(frozen=True)
class PlayerAttacked:
    """Player attacked an enemy this turn.

    ``damage`` is the post-defense, post-variance number actually
    subtracted from the target's HP (already floored at 1 by the damage
    rule). ``killed`` is True when the strike brought ``enemy.hp`` to
    zero or below — when that happens an ``EnemyKilled`` event is
    emitted as the *next* event so consumers can choose to surface them
    separately (the attack animation vs. the death animation).
    """

    enemy_id: UUID
    damage: int
    killed: bool


@dataclass(frozen=True)
class EnemyAttacked:
    """An enemy attacked the player this turn.

    Mirror of ``PlayerAttacked`` for the enemy AI side of the turn. A
    ``PlayerDamaged`` event always follows so the HP delta and the
    cumulative damage counter are observable independently of the
    attacker identity.
    """

    enemy_id: UUID
    damage: int


@dataclass(frozen=True)
class PlayerDamaged:
    """Player HP changed by ``-amount`` this turn.

    Emitted once per damage instance after the player's HP is updated
    and ``damage_taken`` has been incremented. Pairs with
    ``EnemyAttacked`` to give the HUD both the source and the magnitude
    without consumers having to correlate.
    """

    amount: int


@dataclass(frozen=True)
class EnemyKilled:
    """Enemy ``enemy_id`` was killed this turn.

    Emitted immediately after the ``PlayerAttacked`` that lethal blow.
    The kill counter for scoring is read from the event log at
    submission time (task 1.18 / 3.3) — keeping the count off the
    domain models means a replay can re-derive it deterministically.
    """

    enemy_id: UUID


@dataclass(frozen=True)
class PlayerDied:
    """The player reached zero or negative HP this turn.

    Emitted at most once per turn — once the player is dead the enemy
    AI loop short-circuits. Paired with ``game_over=True`` on the
    enclosing ``TurnResult``.
    """


@dataclass(frozen=True)
class FloorDescended:
    """Player descended the staircase to ``new_floor_index``.

    The descent contract is "next floor must already exist in
    ``dungeon.floors``" — generating the next floor on demand is a use
    case / Celery concern (task 4.3), not part of the domain turn loop.
    ``ActionRejected(reason="no_next_floor")`` fires when the next
    floor is missing.
    """

    new_floor_index: int


@dataclass(frozen=True)
class RunAbandoned:
    """Player ended the run via the ``Abandon`` action.

    Distinct from ``PlayerDied``: an abandoned run short-circuits
    ``ScoreService`` so the leaderboard never sees it (per the score
    decision in ``QUESTIONS.md`` task 1.7). The use-case layer
    (``SubmitScore``) checks the last event of the run to decide.
    """


@dataclass(frozen=True)
class ActionRejected:
    """The player's action was invalid this turn — no state changed.

    ``reason`` is a short stable string (snake_case) describing *why*
    the action was rejected. The renderer / HUD surfaces it to the
    player as a flavour message. Reasons used by v1:

    * ``"out_of_bounds"`` — Move target is outside the grid.
    * ``"blocked_by_wall"`` — Move/Attack target is a wall.
    * ``"blocked_by_door"`` — target is a closed door (open it first).
    * ``"not_on_stairs"`` — Descend without standing on a STAIRS tile.
    * ``"no_next_floor"`` — Descend with no next floor pre-generated.
    * ``"nothing_to_attack"`` — explicit Attack on an empty tile.
    * ``"not_implemented_v1"`` — PickUp / UseItem / Open are reserved
      Action variants but require model extensions (inventory slots,
      door open state) that v1 has not yet shipped.

    Keeping reasons as strings (not an enum) trades type-safety for
    additive extensibility — new reasons land in one place without a
    cross-cutting enum bump. The set is small enough today that a
    runtime typo in a reason string is caught by the closest test.
    """

    reason: str


type TurnEvent = (
    PlayerMoved
    | PlayerAttacked
    | EnemyAttacked
    | PlayerDamaged
    | EnemyKilled
    | PlayerDied
    | FloorDescended
    | RunAbandoned
    | ActionRejected
)
"""Discriminated union of every domain event ``process_turn`` may emit.

Use ``match`` to dispatch (PEP 634); mypy-strict exhaustiveness checks
each call site. The entrypoint serialiser (task 3.9) is the primary
consumer; the use-case layer (task 3.3 SubmitScore) is the secondary
consumer for kills / damage / abandon detection.
"""
