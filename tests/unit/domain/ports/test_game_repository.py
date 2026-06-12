import inspect
from typing import get_type_hints
from uuid import UUID, uuid4

from src.domain.models import Dungeon, Floor, Player, TileType
from src.domain.ports import IGameRepository


def _make_floor(*, stairs_down: tuple[int, int] = (1, 1)) -> Floor:
    return Floor(
        floor_id=uuid4(),
        tiles=[[TileType.FLOOR]],
        enemies=[],
        items={},
        stairs_down=stairs_down,
    )


def _make_dungeon(*, dungeon_id: UUID | None = None, seed: int = 42) -> Dungeon:
    return Dungeon(
        dungeon_id=dungeon_id or uuid4(),
        seed=seed,
        floors=[_make_floor()],
        current_floor_index=0,
    )


def _make_player(*, user_id: UUID | None = None) -> Player:
    return Player(user_id=user_id or uuid4(), name="Hero", position=(1, 1))


class _FakeGameRepository:
    """Local in-memory fake used to lock the IGameRepository contract.

    Stays private (``_`` prefix) and local to this test file until a
    second consumer needs it — at that point this gets promoted to a
    shared fixture. YAGNI until then.

    Note the deliberate absence of ``IGameRepository`` in the bases:
    structural conformance (Protocol) means inheritance is neither
    needed nor desirable. The conformance is asserted statically by
    ``test_fake_conforms_structurally`` below.

    The store is keyed by ``dungeon_id`` and holds the whole saved run —
    the ``(Dungeon, Player)`` pair — mirroring the widened port (ADR-0006).
    """

    def __init__(self) -> None:
        self._store: dict[UUID, tuple[Dungeon, Player]] = {}

    async def save(self, dungeon: Dungeon, player: Player) -> tuple[Dungeon, Player]:
        self._store[dungeon.dungeon_id] = (dungeon, player)
        return dungeon, player

    async def get(self, game_id: UUID) -> tuple[Dungeon, Player] | None:
        return self._store.get(game_id)


def test_protocol_is_a_protocol() -> None:
    # CPython sets ``_is_protocol = True`` on every class derived from
    # ``typing.Protocol``. mypy treats ``Protocol`` as a typing special
    # form and flags ``Protocol in __mro__`` as a non-overlapping
    # comparison (correct from its perspective, since Protocol is not
    # a runtime ``type`` in its model), so we use the runtime attribute
    # instead. This catches a regression where the ``(Protocol)`` base
    # is silently dropped — without it, ``IGameRepository`` becomes a
    # nominal class and structural conformance breaks at every adapter.
    assert getattr(IGameRepository, "_is_protocol", False) is True


def test_save_signature_is_async_and_typed() -> None:
    assert inspect.iscoroutinefunction(IGameRepository.save)
    sig = inspect.signature(IGameRepository.save)
    assert list(sig.parameters) == ["self", "dungeon", "player"]
    hints = get_type_hints(IGameRepository.save)
    assert hints["dungeon"] is Dungeon
    assert hints["player"] is Player
    # A saved run is the pair, returned back as the canonical post-write state.
    assert hints["return"] == tuple[Dungeon, Player]


def test_get_signature_is_async_and_typed() -> None:
    assert inspect.iscoroutinefunction(IGameRepository.get)
    sig = inspect.signature(IGameRepository.get)
    assert list(sig.parameters) == ["self", "game_id"]
    hints = get_type_hints(IGameRepository.get)
    assert hints["game_id"] is UUID
    # ``None`` for a missing run; the pair otherwise.
    assert hints["return"] == tuple[Dungeon, Player] | None


def test_fake_conforms_structurally() -> None:
    repo: IGameRepository = _FakeGameRepository()
    assert repo is not None


async def test_fake_save_returns_saved_pair() -> None:
    repo: IGameRepository = _FakeGameRepository()
    dungeon = _make_dungeon()
    player = _make_player()

    saved_dungeon, saved_player = await repo.save(dungeon, player)

    # Field-equality, not ``is``: the port contract permits adapters to
    # return new instances carrying refreshed server-owned fields.
    assert saved_dungeon == dungeon
    assert saved_player == player
    retrieved = await repo.get(dungeon.dungeon_id)
    assert retrieved is not None
    retrieved_dungeon, retrieved_player = retrieved
    assert retrieved_dungeon.dungeon_id == dungeon.dungeon_id
    assert retrieved_player.user_id == player.user_id


async def test_fake_get_missing_returns_none() -> None:
    repo: IGameRepository = _FakeGameRepository()
    assert await repo.get(uuid4()) is None


async def test_fake_save_is_idempotent_on_id() -> None:
    repo: IGameRepository = _FakeGameRepository()
    did = uuid4()
    first = _make_dungeon(dungeon_id=did, seed=1)
    second = _make_dungeon(dungeon_id=did, seed=2)
    player = _make_player()

    await repo.save(first, player)
    await repo.save(second, player)

    retrieved = await repo.get(did)
    # Behaviour-level assertion: the second save overwrote the first.
    # Compare the discriminating field (seed) rather than identity — the
    # port permits adapters to return a fresh instance.
    assert retrieved is not None
    retrieved_dungeon, _ = retrieved
    assert retrieved_dungeon.dungeon_id == did
    assert retrieved_dungeon.seed == second.seed
