import inspect
from typing import get_type_hints

from src.domain.ports import ICachePort


class _FakeCachePort:
    """Local in-memory fake used to lock the ICachePort contract.

    Stays private (``_`` prefix) and local to this test file until a
    second consumer (e.g. ``ProcessTurn`` tests in Phase 3) appears —
    at which point this gets promoted to a shared fixture. YAGNI until
    then, matching the IGameRepository / IScoreRepository pattern.

    Note the deliberate absence of ``ICachePort`` in the bases:
    structural conformance (Protocol) means inheritance is neither
    needed nor desirable.

    TTL is intentionally ignored. The contract role of the fake is
    structural conformance + round-trip behaviour, not clock-aware
    expiry — that lives in Phase 2.7 adapter integration tests
    against real Redis. Wiring an artificial clock here would couple
    every test to ``datetime.now()`` for zero domain-test payoff.

    Fits the 5–10-line budget from QUIZZES.md Task 1.12 Q5: 7 lines
    of behaviour below.
    """

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def set(self, key: str, value: str, ttl: int) -> None:
        self._store[key] = value


def test_protocol_is_a_protocol() -> None:
    # CPython sets ``_is_protocol = True`` on every class derived from
    # ``typing.Protocol``. Mirrors the regression guard on the sibling
    # ports — without ``(Protocol)`` as a base the type silently becomes
    # nominal and structural conformance breaks at every adapter.
    assert getattr(ICachePort, "_is_protocol", False) is True


def test_get_signature_is_async_and_typed() -> None:
    assert inspect.iscoroutinefunction(ICachePort.get)
    sig = inspect.signature(ICachePort.get)
    assert list(sig.parameters) == ["self", "key"]
    hints = get_type_hints(ICachePort.get)
    assert hints["key"] is str
    assert hints["return"] == str | None


def test_set_signature_is_async_and_typed() -> None:
    assert inspect.iscoroutinefunction(ICachePort.set)
    sig = inspect.signature(ICachePort.set)
    assert list(sig.parameters) == ["self", "key", "value", "ttl"]
    hints = get_type_hints(ICachePort.set)
    assert hints["key"] is str
    assert hints["value"] is str
    assert hints["ttl"] is int
    assert hints["return"] is type(None)


def test_fake_conforms_structurally() -> None:
    cache: ICachePort = _FakeCachePort()
    assert cache is not None


async def test_get_missing_key_returns_none() -> None:
    cache: ICachePort = _FakeCachePort()
    # Empty store, asking for any key must yield None (not raise, not
    # return the empty string). The ``is None`` check fences against an
    # adapter that maps "missing" to "" — which would silently break
    # callers that distinguish "no session" from "empty session blob".
    assert await cache.get("never-set") is None


async def test_set_then_get_round_trips_value() -> None:
    cache: ICachePort = _FakeCachePort()
    await cache.set("session:abc", '{"floor": 1}', 7200)
    # Exact-equality assertion (not just truthiness) so an adapter that
    # whitespace-trims or normalises encoding fails this test rather
    # than silently corrupting the JSON blob a use case stored.
    assert await cache.get("session:abc") == '{"floor": 1}'


async def test_set_overwrites_existing_key() -> None:
    cache: ICachePort = _FakeCachePort()
    await cache.set("k", "first", 60)
    await cache.set("k", "second", 60)
    # Locks the "no already-exists sentinel" clause — the second write
    # is a replace, not an error. An adapter that returned False or
    # raised on the second set would violate the docstring contract.
    assert await cache.get("k") == "second"


async def test_set_distinct_keys_do_not_collide() -> None:
    cache: ICachePort = _FakeCachePort()
    await cache.set("a", "1", 60)
    await cache.set("b", "2", 60)
    # Anti-false-positive guard: a buggy adapter that stored every
    # value under a single internal slot would pass the round-trip and
    # overwrite tests but fail this one. Confirms the key is actually
    # part of the storage path.
    assert await cache.get("a") == "1"
    assert await cache.get("b") == "2"


def test_port_surface_is_exactly_get_and_set() -> None:
    # Probes the v1 surface explicitly so adding `delete` or any other
    # method becomes a deliberate, discoverable change rather than
    # silent drift. The two-method shape is the design — see QUIZZES.md
    # Task 1.12 Q5 and the port module docstring.
    public_methods = {
        name
        for name in vars(ICachePort)
        if not name.startswith("_") and callable(getattr(ICachePort, name))
    }
    assert public_methods == {"get", "set"}
