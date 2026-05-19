from dataclasses import dataclass
from uuid import UUID


@dataclass
class Player:
    """Domain model for a player inside a dungeon run.

    Mutable by design — HP and position change every turn. Persistence
    and serialisation belong in adapter layers, never here.

    ``damage_taken`` is the cumulative damage counter consumed by the
    score-penalty formula (see ``compute_score_value`` and the task 1.7
    decision in ``QUESTIONS.md``). ``GameService.process_turn``
    increments it whenever the player loses HP; ``ScoreService.compute``
    reads it once at game over. Living on ``Player`` (vs ``Dungeon``)
    matches "the damage happens to the player" and survives v2 co-op
    where each player carries their own counter.
    """

    user_id: UUID
    name: str
    position: tuple[int, int]
    hp: int = 20
    max_hp: int = 20
    attack: int = 3
    defense: int = 1
    damage_taken: int = 0
