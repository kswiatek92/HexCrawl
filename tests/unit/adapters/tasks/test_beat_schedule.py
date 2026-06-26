"""Unit tests for the Celery Beat schedule (task 4.5).

The schedule is static config on the app, so these assertions read straight off
``app.conf.beat_schedule`` — no Beat process is started and no broker is
contacted, keeping this a fast unit test. They lock the one contract that matters:
Beat must dispatch the registered ``weekly_leaderboard_reset`` task (4.4) at
Monday 00:00 UTC, and nowhere else.
"""

from celery.schedules import crontab

from src.adapters.tasks.celery_app import app

# The task 4.4 / CLAUDE.md "weekly_leaderboard" job is the only periodic task; it
# is dispatched by this Beat entry key.
_ENTRY = "weekly-leaderboard-reset"
_TASK_NAME = "weekly_leaderboard_reset"


def test_beat_schedule_dispatches_the_weekly_reset_task() -> None:
    # Beat resolves the task by its registered wire name; assert the entry exists
    # and targets that exact string (a typo here means Beat fires nothing).
    entry = app.conf.beat_schedule[_ENTRY]
    assert entry["task"] == _TASK_NAME


def test_scheduled_task_is_actually_registered() -> None:
    # Guard against the schedule pointing at a task name no worker knows: Beat
    # would dispatch a message the worker rejects as unregistered. The `include`
    # modules are imported lazily at worker/Beat boot, so replay that boot step
    # (`import_default_modules`) and assert the Beat-referenced name resolves
    # through the same `include` wiring the real process uses.
    app.loader.import_default_modules()
    assert _TASK_NAME in app.tasks


def test_schedule_fires_monday_at_midnight() -> None:
    # The schedule must be a crontab at Monday 00:00. celery normalises the fields
    # to int sets: minute {0}, hour {0}, day_of_week {1} (Monday). Asserting the
    # normalised sets makes the test robust to "mon" vs 1 spelling while still
    # failing on any wrong minute/hour/day.
    schedule = app.conf.beat_schedule[_ENTRY]["schedule"]
    assert isinstance(schedule, crontab)
    assert schedule.minute == {0}
    assert schedule.hour == {0}
    assert schedule.day_of_week == {1}


def test_clock_is_utc_so_midnight_is_unambiguous() -> None:
    # The "00:00" above is only "Mon 00:00 UTC" if the app clock is UTC. This ties
    # the schedule to the clock contract pinned in task 4.1.
    assert app.conf.enable_utc is True
    assert app.conf.timezone == "UTC"
