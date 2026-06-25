"""Tests for ``src.application.generate_floor.GenerateFloor`` (task 4.3).

The application half of the ``map_generation`` task. Tested against a hand-written
``ICachePort`` fake (no Redis), per CLAUDE.md → "Testing strategy". Coverage targets
the 4.3 design intent: the rendered floor (not the seed) is written under the
per-``(game_id, floor_index)`` key with the pre-gen TTL, generation is deterministic,
and a repeat run overwrites idempotently.
"""

from uuid import uuid4

from src.application.floor_cache import (
    PREGEN_FLOOR_TTL_SECONDS,
    deserialize_floor,
    pregenerated_floor_cache_key,
)
from src.application.generate_floor import GenerateFloor
from src.domain.services import generate


class FakeCache:
    """In-memory :class:`ICachePort` recording every ``set`` as ``key -> (value, ttl)``."""

    def __init__(self) -> None:
        self.sets: dict[str, tuple[str, int]] = {}

    async def set(self, key: str, value: str, ttl: int) -> None:
        self.sets[key] = (value, ttl)

    async def get(self, key: str) -> str | None:
        entry = self.sets.get(key)
        return entry[0] if entry is not None else None


async def test_caches_the_rendered_floor_under_the_pregen_key_and_ttl() -> None:
    cache = FakeCache()
    game_id, floor_id = uuid4(), uuid4()
    seed, floor_index = 4242, 11

    await GenerateFloor(cache).execute(game_id, seed, floor_index, floor_id)

    key = pregenerated_floor_cache_key(game_id, floor_index)
    assert key in cache.sets
    value, ttl = cache.sets[key]
    assert ttl == PREGEN_FLOOR_TTL_SECONDS
    # The blob is the *rendered* floor — it deserialises to exactly the geometry
    # the pure generator produces for this recipe (caching the seed alone would
    # not satisfy this), with the supplied floor_id stamped on.
    cached = deserialize_floor(value)
    assert cached == generate(seed, floor_index, floor_id)
    assert cached.floor_id == floor_id


async def test_generation_is_deterministic_for_a_recipe() -> None:
    # Same (seed, floor_index, floor_id) → identical bytes. This is what makes the
    # task safe to run more than once (idempotency rests on it).
    game_id, floor_id = uuid4(), uuid4()
    a, b = FakeCache(), FakeCache()

    await GenerateFloor(a).execute(game_id, 7, 10, floor_id)
    await GenerateFloor(b).execute(game_id, 7, 10, floor_id)

    key = pregenerated_floor_cache_key(game_id, 10)
    assert a.sets[key][0] == b.sets[key][0]


async def test_repeat_run_overwrites_idempotently() -> None:
    # At-least-once delivery can deliver twice; a second run must leave one entry
    # holding the same value, not append or diverge.
    cache = FakeCache()
    game_id, floor_id = uuid4(), uuid4()

    await GenerateFloor(cache).execute(game_id, 99, 10, floor_id)
    first = dict(cache.sets)
    await GenerateFloor(cache).execute(game_id, 99, 10, floor_id)

    assert cache.sets == first


async def test_distinct_floor_indices_get_distinct_keys() -> None:
    cache = FakeCache()
    game_id = uuid4()

    await GenerateFloor(cache).execute(game_id, 1, 10, uuid4())
    await GenerateFloor(cache).execute(game_id, 1, 11, uuid4())

    assert pregenerated_floor_cache_key(game_id, 10) in cache.sets
    assert pregenerated_floor_cache_key(game_id, 11) in cache.sets
    assert len(cache.sets) == 2
