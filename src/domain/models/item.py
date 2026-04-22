from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class ItemType(StrEnum):
    """Top-level item category.

    ``StrEnum`` (Python 3.11+) mirrors ``BehaviourType``: str inheritance
    means variants serialise cleanly as JSON over the WebSocket turn loop
    and compare equal to their wire-format literals. Each variant is
    planned to map to a Player slot — ``WEAPON`` / ``ARMOR`` / ``SHIELD``
    to dedicated equipment slots, and ``POTION`` / ``KEY`` to the shared
    consumables stack (cap 5, enforced by pickup logic, not here).
    Scrolls and gold are deferred to v2.
    """

    WEAPON = "WEAPON"
    ARMOR = "ARMOR"
    SHIELD = "SHIELD"
    POTION = "POTION"
    KEY = "KEY"


@dataclass
class Item:
    """Domain model for a single item instance.

    Mutable by design — ``count`` shrinks as potions are consumed or keys
    are spent, and pickup logic mutates an existing stack in place rather
    than allocating new instances for every merge.

    ``effect`` is a polymorphic integer whose meaning depends on
    ``item_type`` (attack bonus for ``WEAPON``, defense bonus for
    ``ARMOR`` / ``SHIELD``, HP restored for ``POTION``, ignored for
    ``KEY``). Scoring weights per type live in ``ScoreService``, not here.
    """

    item_id: UUID
    name: str
    item_type: ItemType
    effect: int = 0
    count: int = 1
