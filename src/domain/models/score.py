"""Score domain model and pure scoring formula.

`Score` is the leaderboard-facing snapshot of a finished run. Unlike the
other domain models — which mutate every turn — a `Score` is computed once
at game over and never updated, so the dataclass is ``frozen=True``. This
locks the snapshot semantic and pairs with the "pure function" design
intent: ``ScoreService.compute()`` (task 1.18) produces a ``Score`` and the
result is then immutable end-to-end (cache, persist, render).

The module also exposes ``compute_score_value`` — a pure function over
primitives that is the canonical scoring formula. Keeping it as a free
function (not a method on ``Score``) means it can be tested in isolation
and called directly by 1.18's ``ScoreService.compute()`` after that service
has extracted ``floors_reached`` / ``kills`` / ``item_multiplier`` /
``damage_taken`` from a ``Dungeon`` + ``Player``.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

DAMAGE_PENALTY_WEIGHT: int = 1


@dataclass(frozen=True)
class Score:
    """Domain model for a finalised, leaderboard-eligible run score.

    Frozen by design — first ``frozen=True`` dataclass in the codebase.
    A score is computed once at game over from a finished ``Dungeon`` +
    ``Player`` and is never mutated afterwards; freezing turns that
    invariant into a runtime guarantee. Other domain models
    (``Player``, ``Dungeon``, ``Floor``, ``Enemy``, ``Item``) are mutable
    because their state evolves during the run.

    The four "input" fields (``floors_reached``, ``kills``,
    ``item_multiplier``, ``damage_taken``) are kept on the dataclass
    alongside the derived ``value`` so the leaderboard / submission
    pipeline can show *how* a score was reached, not just the total. They
    map 1:1 to the parameters of ``compute_score_value``.

    ``computed_at`` is supplied by the caller — never sourced from
    ``datetime.now()`` inside ``ScoreService`` — so tests can assert
    timestamp equality without freezing the system clock. See QUIZZES.md
    Task 1.7 Q4.
    """

    score_id: UUID
    user_id: UUID
    dungeon_id: UUID
    floors_reached: int
    kills: int
    item_multiplier: float
    damage_taken: int
    value: int
    computed_at: datetime


def compute_score_value(
    floors_reached: int,
    kills: int,
    item_multiplier: float,
    damage_taken: int,
) -> int:
    """Pure function: maps run primitives to the final integer score.

    Formula::

        value = max(0, floors_reached**2 * kills * item_multiplier
                       - damage_taken * DAMAGE_PENALTY_WEIGHT)

    ``floors_reached ** 2`` weights depth so descending always beats
    grinding shallow floors (a player on floor 10 with 5 kills strictly
    beats floor 2 with 25 kills at equal item multiplier). The
    subtractive damage-taken penalty rewards careful play. The
    ``max(0, ...)`` clamp doubles as the multiplicative-zero guard
    (QUIZZES.md Task 1.7 Q1) — a very damaging run cannot post a
    negative number on the leaderboard.

    The float intermediate (``item_multiplier`` is float) is truncated
    to ``int`` at return so the leaderboard sorts on a stable integer
    type end-to-end.
    """
    base = (floors_reached**2) * kills * item_multiplier
    penalty = damage_taken * DAMAGE_PENALTY_WEIGHT
    return max(0, int(base - penalty))
