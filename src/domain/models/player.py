from dataclasses import dataclass
from uuid import UUID


@dataclass
class Player:
    """Domain model for a player inside a dungeon run.

    Mutable by design — HP and position change every turn. Persistence
    and serialisation belong in adapter layers, never here.
    """

    user_id: UUID
    name: str
    position: tuple[int, int]
    hp: int = 20
    max_hp: int = 20
    attack: int = 3
    defense: int = 1
