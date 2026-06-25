"""Result of a weekly leaderboard archive (task 4.4).

The small value object :meth:`IScoreAdminRepository.archive_completed_week
<src.domain.ports.score_admin_repository.IScoreAdminRepository>` returns and the
``weekly_leaderboard_reset`` task / :class:`ResetWeeklyLeaderboard
<src.application.reset_weekly_leaderboard.ResetWeeklyLeaderboard>` use case log.

It carries *what was archived*, not the archived rows themselves: the identity of
the week that was snapshotted (``week_start``) and how many ranked entries landed
in the archive (``archived_count``). That is exactly enough for observability — a
structured log line "archived N entries for the week of X" — without dragging a
full ``list[Score]`` back across the port for a value the caller never inspects
(the cache refresh reads the *new* week independently).

``frozen=True`` mirrors :class:`~src.domain.models.score.Score`: like a finalised
score, an archive result is a computed snapshot, never mutated after the fact.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class WeeklyArchiveResult:
    """Immutable summary of one weekly-archive run.

    ``week_start`` is the Monday-00:00-UTC start of the *completed* week that was
    archived (the week that just ended, not the current one). ``archived_count``
    is the number of ranked entries snapshotted — ``0`` when the completed week
    had no qualifying scores, which is a normal outcome, not an error.
    """

    week_start: datetime
    archived_count: int
