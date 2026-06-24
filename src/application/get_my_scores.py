"""``GetMyScores`` — the read use case behind ``GET /leaderboard/me``.

The authenticated, per-user counterpart to ``GetLeaderboard`` (the public
``global`` / ``weekly`` boards, tasks 3.10–3.11). Where those serve one shared,
bounded top-100 slice — cheap to cache for everyone — this query is *scoped to
the caller*: their strongest personal runs plus where their single best run sits
on each public board. That per-user shape is exactly why it does **not** reuse
the leaderboard Redis cache: a top-100 slice is one key shared by all readers,
but "my scores" is a distinct slice per user, so caching it would mean a key per
user with no shared-read benefit. It reads straight through to Postgres via the
score repository (CLAUDE.md → API surface: "Current user's best scores").

Like every use case it is *orchestration*, not domain rule: it wires the score
repository's reads together and holds no scoring logic. Bound by the hexagonal
golden rule — it imports domain models and the domain port only; never an
adapter, never a framework. Constructor-injected port (mirroring
``GetLeaderboard``), so it is unit-testable against a hand-written fake with no
database.
"""

from dataclasses import dataclass
from uuid import UUID

from src.application.leaderboard_cache import LEADERBOARD_SIZE
from src.domain.models import LeaderboardPeriod, Score
from src.domain.ports import IScoreRepository


@dataclass(frozen=True)
class MyScores:
    """A caller's personal-best history plus their standing on the public boards.

    ``scores`` is the user's top runs (``value`` DESC, ``computed_at`` ASC —
    :meth:`IScoreRepository.top_n_for_user`), period-agnostic. ``global_rank`` /
    ``weekly_rank`` are the 1-indexed position of the user's *single best* run on
    each public board, or ``None`` when they have no qualifying score in that
    window (a fresh account globally; anyone who hasn't played this week for
    weekly). The entrypoint maps ``None`` to "unranked".
    """

    scores: list[Score]
    global_rank: int | None
    weekly_rank: int | None


class GetMyScores:
    """Use case: fetch the caller's best runs and their board standings.

    Takes only :class:`IScoreRepository` — no cache port. Unlike the public
    boards, this slice is per-user and read straight from the durable store.
    """

    def __init__(self, scores: IScoreRepository) -> None:
        self._scores = scores

    async def execute(self, user_id: UUID) -> MyScores:
        """Return ``user_id``'s top runs and their global + weekly ranks.

        Three reads against the score repository: the user's top-100 personal
        bests, then their rank on each public board. ``rank_of`` returns ``None``
        for a user with no qualifying score in a window — surfaced verbatim so
        the entrypoint can render "unranked" without a sentinel. The entrypoint
        paginates the returned ``scores`` list (offset/limit), exactly as the
        global/weekly boards do.
        """
        scores = await self._scores.top_n_for_user(user_id, LEADERBOARD_SIZE)
        global_rank = await self._scores.rank_of(user_id, LeaderboardPeriod.GLOBAL)
        weekly_rank = await self._scores.rank_of(user_id, LeaderboardPeriod.WEEKLY)
        return MyScores(scores=scores, global_rank=global_rank, weekly_rank=weekly_rank)
