"""Unit tests for the Celery application setup (task 4.1).

These lock the *configuration contract* the app module owns — broker/result
wiring sourced from :class:`Settings`, JSON-only serialisation (the no-pickle
security choice, QUIZZES.md 4.1 Q5), a UTC clock, the auto-discovery instance
name, and the terminal-failure log-and-drop policy (QUESTIONS.md task 4.1).

No broker is contacted: importing the app builds the instance but opens no
connection, so this stays a fast unit test. The real worker round-trip is out of
scope for 4.1 (no tasks exist until 4.2).
"""

import structlog
from celery import Celery

from src.adapters.tasks.celery_app import _log_task_failure, app
from src.config import Settings


def test_broker_and_backend_are_sourced_from_settings() -> None:
    settings = Settings()
    assert app.conf.broker_url == settings.celery_broker_url
    assert app.conf.result_backend == settings.celery_result_backend


def test_serialization_is_json_and_never_pickle() -> None:
    # The security-relevant assertion: an attacker-controlled pickle payload is
    # arbitrary code execution; JSON cannot carry code (QUIZZES.md 4.1 Q5).
    assert app.conf.task_serializer == "json"
    assert app.conf.result_serializer == "json"
    assert app.conf.accept_content == ["json"]
    assert "pickle" not in app.conf.accept_content


def test_clock_is_utc() -> None:
    # Weekly Beat reset (task 4.5) is "Mon 00:00 UTC" — pin the clock now.
    assert app.conf.enable_utc is True
    assert app.conf.timezone == "UTC"


def test_app_identity_supports_cli_autodiscovery() -> None:
    # `celery -A src.adapters.tasks.celery_app worker` finds the instance by the
    # attribute name `app`; guard both the type and the main name.
    assert isinstance(app, Celery)
    assert app.main == "hexcrawl"


def test_task_failure_handler_logs_and_drops() -> None:
    class _FakeRequest:
        retries = 2

    class _FakeTask:
        name = "score_recalc"
        request = _FakeRequest()

    exc = ValueError("boom")

    with structlog.testing.capture_logs() as logs:
        result = _log_task_failure(
            sender=_FakeTask(),
            task_id="abc-123",
            exception=exc,
            args=["score-uuid"],
            kwargs={},
        )

    # Log-and-drop: returns None (no re-raise) and emits exactly one error event
    # carrying the task name, id, call args/kwargs (which job failed), retry
    # count, and the exception.
    assert result is None
    assert len(logs) == 1
    entry = logs[0]
    assert entry["event"] == "celery.task_failed"
    assert entry["log_level"] == "error"
    assert entry["task"] == "score_recalc"
    assert entry["task_id"] == "abc-123"
    assert entry["args"] == ["score-uuid"]
    assert entry["kwargs"] == {}
    assert entry["retries"] == 2
    assert "boom" in entry["exc"]
