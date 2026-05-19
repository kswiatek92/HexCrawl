from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class BehaviourType(StrEnum):
    """Top-level enemy archetype.

    ``StrEnum`` (Python 3.11+) gives us str inheritance — values serialise
    cleanly as JSON over the WebSocket turn loop and compare equal to their
    wire-format literals. Granular variants (e.g. cowardly melee) are
    deferred to v2.
    """

    MELEE = "MELEE"
    RANGED = "RANGED"
    BOSS = "BOSS"


@dataclass
class Enemy:
    """Domain model for a single enemy instance on a floor.

    Mutable by design — HP and position change every turn. Stat values are
    set by spawn logic (per floor × behaviour); no v1 defaults here, since
    they would be misleading for the `BOSS` variant.

    ``awake`` is the sticky-aggro flag consumed by ``enemy_ai.decide_action``:
    once set it stays set until the enemy is destroyed or the floor is
    abandoned. Storing it on the enemy itself (rather than a side
    ``set[UUID]``) keeps the per-floor reset automatic — descending spawns
    fresh enemies with ``awake=False`` — and removes a serialisation seam.
    """

    enemy_id: UUID
    name: str
    position: tuple[int, int]
    behaviour: BehaviourType
    hp: int
    max_hp: int
    attack: int
    defense: int
    awake: bool = False
