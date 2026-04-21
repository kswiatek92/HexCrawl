from dataclasses import dataclass
from enum import Enum
from uuid import UUID


class BehaviourType(str, Enum):
    """Top-level enemy archetype.

    Inherits from ``str`` so values serialise cleanly as JSON strings over
    the WebSocket turn loop and compare equal to their wire-format literals.
    Granular variants (e.g. cowardly melee) are deferred to v2.
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
    """

    enemy_id: UUID
    name: str
    position: tuple[int, int]
    behaviour: BehaviourType
    hp: int
    max_hp: int
    attack: int
    defense: int
