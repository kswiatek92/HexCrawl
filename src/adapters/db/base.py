"""SQLAlchemy declarative base shared by every ORM model.

This is an *adapter* concern — it imports SQLAlchemy and therefore must never be
imported from ``domain/`` or ``application/`` (hexagonal golden rule). All ORM
models (task 2.3 onward) inherit ``Base`` so they register on a single
``MetaData``, which is what Alembic's ``--autogenerate`` diffs against.

The ``NAMING_CONVENTION`` is attached to that ``MetaData`` here, from the very
first migration, so Postgres names every index/constraint deterministically.
Without it, autogenerate would emit DB-assigned names that differ between
environments, making diffs noisy and ``downgrade()`` unable to drop constraints
by a stable name (see QUESTIONS.md Phase 2 — naming-convention decision).
"""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Standard Alembic-recommended template. Keys are the constraint-type tokens
# SQLAlchemy understands; the %-fields are filled in per object at DDL time.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base for all HexCrawl ORM models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
