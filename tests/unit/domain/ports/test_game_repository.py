import inspect
from typing import get_type_hints
from uuid import UUID, uuid4

from src.domain.models import Dungeon, Floor, TileType
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


class _FakeGameRepository:
    """Local in-memory fake used to lock the IGameRepository contract.

    Stays private (``_`` prefix) and local to this test file until
    ``GameService`` tests (task 1.17) become a second consumer — at
    that point this gets promoted to a shared fixture. YAGNI until
    then.

    Note the deliberate absence of ``IGameRepository`` in the bases:
    structural conformance (Protocol) means inheritance is neither
    needed nor desirable. The conformance is asserted statically by
    ``test_fake_conforms_structurally`` below.
    """

    def __init__(self) -> None:
        self._store: dict[UUID, Dungeon] = {}

    async def save(self, dungeon: Dungeon) -> Dungeon:
        self._store[dungeon.dungeon_id] = dungeon
        return dungeon

    async def get(self, game_id: UUID) -> Dungeon | None:
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
    assert list(sig.parameters) == ["self", "dungeon"]
    hints = get_type_hints(IGameRepository.save)
    assert hints["dungeon"] is Dungeon
    assert hints["return"] is Dungeon


def test_get_signature_is_async_and_typed() -> None:
    assert inspect.iscoroutinefunction(IGameRepository.get)
    sig = inspect.signature(IGameRepository.get)
    assert list(sig.parameters) == ["self", "game_id"]
    hints = get_type_hints(IGameRepository.get)
    assert hints["game_id"] is UUID
    assert hints["return"] == Dungeon | None


def test_fake_conforms_structurally() -> None:
    repo: IGameRepository = _FakeGameRepository()
    assert repo is not None


async def test_fake_save_returns_saved_dungeon() -> None:
    repo: IGameRepository = _FakeGameRepository()
    dungeon = _make_dungeon()

    saved = await repo.save(dungeon)

    assert saved is dungeon
    assert await repo.get(dungeon.dungeon_id) is dungeon


async def test_fake_get_missing_returns_none() -> None:
    repo: IGameRepository = _FakeGameRepository()
    assert await repo.get(uuid4()) is None


async def test_fake_save_is_idempotent_on_id() -> None:
    repo: IGameRepository = _FakeGameRepository()
    did = uuid4()
    first = _make_dungeon(dungeon_id=did, seed=1)
    second = _make_dungeon(dungeon_id=did, seed=2)

    await repo.save(first)
    await repo.save(second)

    retrieved = await repo.get(did)
    assert retrieved is second
