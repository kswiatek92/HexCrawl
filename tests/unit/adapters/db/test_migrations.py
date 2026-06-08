"""Migration-graph integrity guards.

These read the Alembic script directory off disk — no DB connection and no
execution of env.py, so they stay fast and need neither Postgres nor Settings.

The single-head check is the automated half of QUIZZES.md task 2.2 Q5: when two
branches each create a migration without a merge, Alembic ends up with two heads
and `upgrade head` becomes ambiguous. Asserting exactly one head fails CI the
moment that happens. The single-base check guards the mirror image — the history
must have exactly one root, or `downgrade base` is ambiguous.
"""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

# tests/unit/adapters/db/test_migrations.py -> repo root is four parents up.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_ALEMBIC_INI = _REPO_ROOT / "alembic.ini"


def _script_directory() -> ScriptDirectory:
    return ScriptDirectory.from_config(Config(str(_ALEMBIC_INI)))


def test_single_migration_head() -> None:
    # Exactly one head: no unmerged branch points in the migration graph.
    assert len(_script_directory().get_heads()) == 1


def test_single_migration_base() -> None:
    # Exactly one root (a revision with down_revision is None): linear history
    # all the way back to the empty database.
    assert len(_script_directory().get_bases()) == 1
