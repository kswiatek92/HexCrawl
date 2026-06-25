"""SQLAlchemy ORM models — the persistence shape of a HexCrawl run.

These are an *adapter* concern: they import SQLAlchemy and therefore must never
be imported from ``domain/`` or ``application/`` (hexagonal golden rule). They
are deliberately **separate** from the domain dataclasses in
``src/domain/models/`` (BOARD task 2.3, QUIZZES.md 2.3 Q1): the domain stays a
pure, framework-free, fast-to-test core, while these classes own the row layout,
foreign keys, indexes, and loading strategy. The Phase 2.4 / 2.5 repositories
translate between the two — nothing else does.

Design (see DECISIONS.md ADR-0005):

* **Relational aggregate.** A run is modelled as ``dungeons → floors → enemies``
  related tables (not seed-only persistence), so the Postgres checkpoint holds
  the *mutated* state — HP, pickups, awake flags — that a seed alone cannot
  reconstruct. Collections load with ``lazy="selectin"`` (QUIZZES.md 2.3 Q3):
  one extra ``IN (...)`` query per level of the aggregate, avoiding both the
  N+1 problem (Q2) and the row multiplication a JOIN would cause.
* **Player as a 1:1 table** keyed by ``dungeon_id`` (Q5) — normalised and
  queryable, and it honours the domain's deliberate Dungeon/Player separation.
* **Floor grid as JSONB.** ``tiles`` and ground ``items`` are read/written as a
  whole, never queried cell-by-cell, so a JSONB blob beats a row-per-cell table.
* **``scores.dungeon_id`` is a plain column, not a foreign key.** A ``Score`` is
  an immutable leaderboard record that outlives the run (active runs live in
  Redis and may be GC'd); coupling score retention to dungeon lifecycle via a
  cascade would let a cleaned-up run delete leaderboard history.

The ``*Row`` suffix keeps these visually distinct from the identically-named
domain dataclasses (``Player``/``Dungeon``/...) in repository code that imports
both.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    UniqueConstraint,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.adapters.db.base import Base
from src.domain.models import BehaviourType


class DungeonRow(Base):
    """A persisted dungeon run — the aggregate root."""

    __tablename__ = "dungeons"

    dungeon_id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(index=True)
    # BigInteger: the procedural seed can exceed a 32-bit INTEGER.
    seed: Mapped[int] = mapped_column(BigInteger)
    current_floor_index: Mapped[int]
    turn_count: Mapped[int] = mapped_column(default=0)

    player: Mapped["PlayerRow"] = relationship(
        back_populates="dungeon",
        uselist=False,
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    floors: Mapped[list["FloorRow"]] = relationship(
        back_populates="dungeon",
        order_by="FloorRow.floor_index",
        lazy="selectin",
        cascade="all, delete-orphan",
    )


class PlayerRow(Base):
    """Per-run player state, 1:1 with its dungeon (PK is the FK)."""

    __tablename__ = "players"

    dungeon_id: Mapped[UUID] = mapped_column(
        ForeignKey("dungeons.dungeon_id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[UUID]
    name: Mapped[str]
    # Domain Player.position is an (x, y) tuple; stored as two queryable columns.
    position_x: Mapped[int]
    position_y: Mapped[int]
    hp: Mapped[int]
    max_hp: Mapped[int]
    attack: Mapped[int]
    defense: Mapped[int]
    damage_taken: Mapped[int]

    dungeon: Mapped[DungeonRow] = relationship(back_populates="player")


class FloorRow(Base):
    """One level of a run. The grid (``tiles``) and ground ``items`` are JSONB."""

    __tablename__ = "floors"
    __table_args__ = (
        # A dungeon cannot have two floors at the same depth.
        UniqueConstraint("dungeon_id", "floor_index"),
    )

    floor_id: Mapped[UUID] = mapped_column(primary_key=True)
    dungeon_id: Mapped[UUID] = mapped_column(
        ForeignKey("dungeons.dungeon_id", ondelete="CASCADE"),
        index=True,
    )
    floor_index: Mapped[int]
    # tiles[y][x] grid of TileType values, serialised as nested string arrays.
    tiles: Mapped[list[list[str]]] = mapped_column(JSONB)
    # Ground items keyed by "x,y" position -> list of item blobs.
    items: Mapped[dict[str, list[dict[str, Any]]]] = mapped_column(JSONB)
    stairs_x: Mapped[int]
    stairs_y: Mapped[int]

    dungeon: Mapped[DungeonRow] = relationship(back_populates="floors")
    enemies: Mapped[list["EnemyRow"]] = relationship(
        back_populates="floor",
        lazy="selectin",
        cascade="all, delete-orphan",
    )


class EnemyRow(Base):
    """A single enemy instance on a floor."""

    __tablename__ = "enemies"

    enemy_id: Mapped[UUID] = mapped_column(primary_key=True)
    floor_id: Mapped[UUID] = mapped_column(
        ForeignKey("floors.floor_id", ondelete="CASCADE"),
        index=True,
    )
    name: Mapped[str]
    position_x: Mapped[int]
    position_y: Mapped[int]
    # native_enum=False -> portable VARCHAR + CHECK constraint (named by the
    # convention on Base.metadata) rather than a hard-to-migrate Postgres ENUM.
    behaviour: Mapped[BehaviourType] = mapped_column(SAEnum(BehaviourType, native_enum=False))
    hp: Mapped[int]
    max_hp: Mapped[int]
    attack: Mapped[int]
    defense: Mapped[int]
    awake: Mapped[bool] = mapped_column(default=False)

    floor: Mapped[FloorRow] = relationship(back_populates="enemies")


class ScoreRow(Base):
    """An immutable, leaderboard-eligible run score.

    Holds the four scoring inputs alongside the derived ``value`` so the
    leaderboard can show *how* a score was reached. ``dungeon_id`` is a plain
    column (no FK): scores outlive their runs.
    """

    __tablename__ = "scores"

    score_id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(index=True)
    dungeon_id: Mapped[UUID]
    floors_reached: Mapped[int]
    kills: Mapped[int]
    item_multiplier: Mapped[float]
    damage_taken: Mapped[int]
    value: Mapped[int]
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


# Composite index backing IScoreRepository.top_n / rank_of ordering:
# value DESC (highest first), computed_at ASC (earlier run wins ties). Defined
# after the class so the mapped attributes' .desc()/.asc() are available.
Index(
    "ix_scores_value_computed_at",
    ScoreRow.value.desc(),
    ScoreRow.computed_at.asc(),
)


class WeeklyLeaderboardArchiveRow(Base):
    """A snapshotted entry of a *completed* week's leaderboard (task 4.4).

    The weekly board is a ``computed_at`` window over the shared ``scores`` table,
    so it resets itself when the week advances — and the finished week's standings
    would be unrecoverable afterwards. The ``weekly_leaderboard_reset`` task
    archives them here, one row per ranked entry, before the window moves on.

    Like ``ScoreRow``, these are **plain columns, no foreign key** to ``scores``:
    an archive is an immutable historical record that must outlive score churn and
    run cleanup, so coupling its lifecycle to the live tables via a cascade would
    let routine deletion erase leaderboard history.

    ``UniqueConstraint(week_start, score_id)`` makes the archive idempotent per
    week: the adapter snapshots a week by deleting that week's rows and
    re-inserting, so a retried task replaces rather than duplicates.
    """

    __tablename__ = "weekly_leaderboard_archive"
    __table_args__ = (UniqueConstraint("week_start", "score_id"),)

    archive_id: Mapped[UUID] = mapped_column(primary_key=True)
    # Monday 00:00 UTC of the completed week this entry belongs to. Indexed: the
    # adapter reads / replaces a whole week by this key.
    week_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    rank: Mapped[int]
    score_id: Mapped[UUID]
    user_id: Mapped[UUID] = mapped_column(index=True)
    value: Mapped[int]
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
