"""The declarative Base must carry the agreed naming convention.

This locks the QUESTIONS.md Phase 2 decision: a naming convention is attached to
the MetaData from the first migration so Alembic autogenerate produces
deterministic, stable constraint/index names. If the convention is dropped or
edited, every future migration's generated names drift — so we pin it here.
"""

from src.adapters.db.base import NAMING_CONVENTION, Base


def test_base_metadata_uses_naming_convention() -> None:
    # The MetaData must actually be configured with our convention — not the
    # SQLAlchemy default (an empty dict), which would let Postgres assign names.
    assert Base.metadata.naming_convention == NAMING_CONVENTION


def test_naming_convention_covers_all_constraint_types() -> None:
    # One template per constraint type SQLAlchemy names: index, unique, check,
    # foreign key, primary key. A missing key means that constraint type falls
    # back to a non-deterministic DB-assigned name.
    assert set(NAMING_CONVENTION) == {"ix", "uq", "ck", "fk", "pk"}
