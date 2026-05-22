"""``ScoreService.compute`` — primitive extraction + formula composition.

Task 1.18. The scoring **formula** and the ``Score`` frozen dataclass live
in ``src/domain/models/score.py`` (task 1.7, locked by ADR-0002). This
service is the thin layer above them: it pulls the four primitive inputs
(``floors_reached``, ``kills``, ``item_multiplier``, ``damage_taken``) out
of live run state and feeds them into ``compute_score_value``. The Service
itself is just a module of pure functions — matching the ``process_turn`` /
``generate`` pattern in this package.

Design intent (``QUESTIONS.md`` tasks 1.7 / 1.16 / 1.18, ADR-0002):

* **Pure function.** No I/O, no module-level mutable state (the per-type
  weight map is a ``MappingProxyType``), no hidden clock or RNG.
  ``score_id`` and ``computed_at`` are supplied by the caller — same hygiene
  as the ``Score`` dataclass itself (QUIZZES Task 1.7 Q4) so tests can
  assert equality without freezing the system clock.
* **Composition over re-derivation.** ``compute_score`` calls
  ``compute_score_value`` rather than re-implementing the formula; if the
  formula is retuned, only ADR-0002's module changes.
* **Per-type item weights live here, not on the model.** ``QUESTIONS.md``
  task 1.4 parked the multiplier shape as "static ``ItemType → float`` map
  owned by ``ScoreService``." The exact values are tunable and provisional
  — they ship in one constant so one commit retunes them.
* **No abandoned-run zeroing here.** QUIZZES Task 1.18 Q3 pre-decided that
  the ``status == ABANDONED`` short-circuit belongs in ``SubmitScore``
  (task 3.3), not in this pure service. ``compute_score`` is unconditional:
  give it primitives, it returns a ``Score``.

Why ``kills`` and ``items`` are explicit parameters rather than fields on
``Player`` / ``Dungeon``: neither exists on the models today. ``EnemyKilled``
is an event (``turn_event.py``) with no aggregator; inventory slots are
specced in ``QUESTIONS.md`` task 1.2 but ``PickUp`` / ``UseItem`` are still
``not_implemented_v1`` in ``process_turn``. The caller — eventually the
``SubmitScore`` use case (task 3.3) — owns aggregation. When those land on
``Player``, the use case stitches them in; the service signature is unchanged.
"""

from collections.abc import Iterable, Mapping
from datetime import datetime
from types import MappingProxyType
from typing import Final
from uuid import UUID

from src.domain.models.dungeon import Dungeon
from src.domain.models.item import Item, ItemType
from src.domain.models.player import Player
from src.domain.models.score import Score, compute_score_value

ITEM_TYPE_WEIGHTS: Final[Mapping[ItemType, float]] = MappingProxyType(
    {
        ItemType.WEAPON: 0.5,
        ItemType.ARMOR: 0.3,
        ItemType.SHIELD: 0.2,
        ItemType.POTION: 0.05,
        ItemType.KEY: 0.1,
    }
)
"""Per-``ItemType`` contribution to the score multiplier.

Read-only at runtime (``MappingProxyType``) so tests cannot accidentally
mutate the calibration table for the rest of a session. Provisional values:
weapon biggest contribution to combat, armor / shield mid, key niche,
potion small — proportions chosen for sense, not playtesting. Tunable in
one place; retuning is a single-commit change.
"""


def compute_item_multiplier(items: Iterable[Item]) -> float:
    """Sum per-type item weights into a single multiplier.

    Formula::

        multiplier = 1.0 + sum(ITEM_TYPE_WEIGHTS[item.item_type] * item.count
                               for item in items)

    Empty iterable returns ``1.0`` — the multiplicative identity. A run with
    no items still scores; using ``0.0`` would zero out every pre-pickup
    run via the multiplicative chain in ``compute_score_value`` and make
    early-game scoring meaningless.

    The combination is **additive across items** rather than multiplicative.
    ``compute_score_value`` already multiplies three axes
    (``floors² × kills × multiplier``); a fourth multiplicative layer
    compounds dangerously (five weapons → ``1.5⁵ ≈ 7.6×`` vs additive
    ``1 + 5·0.5 = 3.5×``). Additive is linear-tunable and predictable.

    ``items`` is typed ``Iterable[Item]`` not ``Sequence[Item]`` so callers
    can pass a generator (e.g. ``chain(player.weapon, player.armor, ...)``
    once inventory slots land on ``Player``); the function consumes it once
    and never subscripts.
    """
    return 1.0 + sum(ITEM_TYPE_WEIGHTS[item.item_type] * item.count for item in items)


def compute_score(
    dungeon: Dungeon,
    player: Player,
    *,
    kills: int,
    items: Iterable[Item] = (),
    score_id: UUID,
    computed_at: datetime,
) -> Score:
    """Build a ``Score`` from finished-run state.

    Extracts the four scoring primitives from the live ``Dungeon`` and
    ``Player`` instances, computes the multiplier from ``items``, and
    delegates the arithmetic to ``compute_score_value`` — the formula
    lives in one place (ADR-0002) and this service is glue.

    ``floors_reached = dungeon.current_floor_index + 1`` translates the
    0-based engine index into the 1-based "Reached floor N" value the
    leaderboard renders. A player on the spawn floor
    (``current_floor_index == 0``) has reached floor 1.

    ``kills`` is caller-supplied because no kill counter currently lives on
    any domain model — ``EnemyKilled`` events are the source of truth and
    aggregation belongs in the use-case layer. Same for ``items``: until
    inventory slots ship on ``Player``, the caller passes whatever stand-in
    collection is appropriate (an empty tuple in tests, the future
    ``chain(player.weapon, ...)`` in production).

    ``score_id`` and ``computed_at`` are passed in by the caller, never
    generated inside this function. This mirrors ``Score``'s own contract
    (QUIZZES Task 1.7 Q4): purity end-to-end, tests assert equality without
    freezing the clock or stubbing ``uuid.uuid4``.

    Inputs are never mutated. The returned ``Score`` is frozen.
    """
    floors_reached = dungeon.current_floor_index + 1
    multiplier = compute_item_multiplier(items)
    value = compute_score_value(
        floors_reached=floors_reached,
        kills=kills,
        item_multiplier=multiplier,
        damage_taken=player.damage_taken,
    )
    return Score(
        score_id=score_id,
        user_id=player.user_id,
        dungeon_id=dungeon.dungeon_id,
        floors_reached=floors_reached,
        kills=kills,
        item_multiplier=multiplier,
        damage_taken=player.damage_taken,
        value=value,
        computed_at=computed_at,
    )
