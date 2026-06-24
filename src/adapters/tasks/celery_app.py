"""Celery application — the worker-side adapter for HexCrawl's async jobs.

This module owns the single :class:`~celery.Celery` instance every Phase 4 task
registers against (``score_recalc``, ``map_generation``,
``weekly_leaderboard_reset`` — CLAUDE.md → "Celery tasks"). It is an *adapter*:
it imports a framework (``celery``) and therefore may never be imported by
``domain/`` or ``application/``. The application layer reaches the worker solely
through the :class:`IScoreRecalcQueue` port
(``src/domain/ports/score_recalc_queue.py``); the Celery *producer* that conforms
to that port is a separate adapter built in task 4.2. This module only stands up
the app — no tasks, no Beat schedule yet (tasks 4.2–4.5).

Design, pinned to ``QUIZZES.md`` task 4.1:

* **Instance named ``app``** — CLAUDE.md's local-dev command is
  ``celery -A src.adapters.tasks.celery_app worker`` (no ``:attr`` suffix), so
  Celery's ``find_app`` auto-discovery must locate the instance by attribute. It
  looks for ``module.app`` first, then ``module.celery``; naming it ``app`` keeps
  that command working. This is the standard ``app = Celery(...)`` convention.

* **Broker vs result backend, both Redis** (Q2) — the *broker* (``redis`` db1)
  carries pending task messages; the *result backend* (``redis`` db2) stores
  return values / task state. Both URLs come from :class:`Settings`
  (``celery_broker_url`` / ``celery_result_backend``), never hardcoded. Redis
  trades AMQP's richer routing and stronger delivery guarantees for operational
  simplicity — one datastore we already run (Q3).

* **JSON, never pickle** (Q5) — ``task_serializer`` / ``result_serializer`` are
  ``"json"`` and ``accept_content`` admits ``"json"`` only. Unpickling an
  attacker-controlled task payload is arbitrary code execution; JSON cannot carry
  code, so it is the safe default. The cost is that task args must be
  JSON-serialisable — which is exactly why :class:`IScoreRecalcQueue` passes a
  stringifiable ``UUID``, not a pickled domain object (CLAUDE.md → "Celery
  tasks": args "must be JSON-serialisable, not pickled").

* **UTC pinned** — ``enable_utc`` / ``timezone="UTC"`` set now so the weekly Beat
  reset (task 4.5, "Mon 00:00 UTC") inherits the right clock and no later silent
  default flip can move it.

* **Terminal failures log-and-drop** — the ``task_failure`` signal handler below
  realises the QUESTIONS.md task-4.1 decision: a job that fails terminally is
  structured-logged via ``structlog`` and dropped. There is no dead-letter queue
  — the Redis transport has no native dead-letter routing, and these tasks are
  derived/idempotent (the durable ``Score`` row is written *before* the recalc is
  ever enqueued), so a dropped job is recoverable on the next enqueue. Wiring
  Sentry into this same handler is a Phase 6 follow-up, not a v1 dependency.
"""

import structlog
from celery import Celery
from celery.signals import task_failure

from src.config import Settings

_settings = Settings()

logger = structlog.get_logger(__name__)

app = Celery(
    "hexcrawl",
    broker=_settings.celery_broker_url,
    backend=_settings.celery_result_backend,
)

app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)


def _log_task_failure(
    sender: object = None,
    task_id: str | None = None,
    exception: BaseException | None = None,
    args: object = None,
    kwargs: object = None,
    **extra: object,
) -> None:
    """Structured-log a terminally-failed task, then let it drop.

    Fires only on terminal failure: a task that calls ``self.retry()`` raises
    ``Retry`` and emits ``task_retry`` instead, so reaching here means the job is
    done failing. We emit one structured ``error`` event — task name, id, the
    call args/kwargs (so the log says *which* job failed, e.g. the ``score_id``),
    retry count, and the exception — and return, dropping the job. This is the
    log-and-drop policy recorded for task 4.1 (QUESTIONS.md): no re-raise, no
    dead-letter queue. Task payloads here are small JSON-serialisable identifiers
    (a ``UUID``, a seed), so logging them carries no sensitive-data risk.
    """
    request = getattr(sender, "request", None)
    logger.error(
        "celery.task_failed",
        task=getattr(sender, "name", None),
        task_id=task_id,
        args=args,
        kwargs=kwargs,
        retries=getattr(request, "retries", None),
        exc=repr(exception),
    )


# Connected explicitly (not via the ``@task_failure.connect`` decorator) so the
# handler keeps its type annotations — an untyped Celery decorator would erase
# them under mypy-strict. ``weak=False`` keeps the receiver strongly referenced.
task_failure.connect(_log_task_failure, weak=False)
