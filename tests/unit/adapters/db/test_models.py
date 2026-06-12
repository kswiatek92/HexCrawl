"""ORM model structure guards — metadata/mapper introspection, no DB.

These assert the *schema-shaping* decisions of task 2.3 that a Postgres round
trip alone would not pin: the relational aggregate, ``selectin`` loading, the
1:1 player, the leaderboard index, and the deliberate FK-free ``scores`` table.
Full read/write round-trips against a real database are deferred to task 2.6
(testcontainers). Everything here is pure introspection, so it stays fast and
needs neither Postgres nor Settings.

Each test is written so it would *fail* if the feature it guards were removed
(e.g. flipping ``lazy="selectin"`` back to the default ``"select"`` breaks the
loading-strategy test).
"""

from sqlalchemy import ForeignKeyConstraint, inspect
from sqlalchemy.sql import operators

from src.adapters.db.base import Base
from src.adapters.db.models import (
    DungeonRow,
    EnemyRow,
    FloorRow,
    PlayerRow,
    ScoreRow,
)

EXPECTED_TABLES = {"dungeons", "players", "floors", "enemies", "scores"}


def test_all_expected_tables_registered() -> None:
    # Every ORM model must register on the shared Base.metadata — that single
    # MetaData is what Alembic autogenerate diffs against.
    assert EXPECTED_TABLES <= set(Base.metadata.tables)


def test_table_columns() -> None:
    # Spot-check each table's column set so an accidental rename/drop is caught.
    cols = {name: set(table.columns.keys()) for name, table in Base.metadata.tables.items()}
    assert cols["dungeons"] == {
        "dungeon_id",
        "user_id",
        "seed",
        "current_floor_index",
        "turn_count",
    }
    assert cols["players"] == {
        "dungeon_id",
        "user_id",
        "name",
        "position_x",
        "position_y",
        "hp",
        "max_hp",
        "attack",
        "defense",
        "damage_taken",
    }
    assert cols["floors"] == {
        "floor_id",
        "dungeon_id",
        "floor_index",
        "tiles",
        "items",
        "stairs_x",
        "stairs_y",
    }
    assert cols["enemies"] == {
        "enemy_id",
        "floor_id",
        "name",
        "position_x",
        "position_y",
        "behaviour",
        "hp",
        "max_hp",
        "attack",
        "defense",
        "awake",
    }
    assert cols["scores"] == {
        "score_id",
        "user_id",
        "dungeon_id",
        "floors_reached",
        "kills",
        "item_multiplier",
        "damage_taken",
        "value",
        "computed_at",
    }


def test_collections_use_selectin_loading() -> None:
    # QUIZZES.md 2.3 Q3: collections load with selectin to avoid N+1 (Q2)
    # without the row multiplication a JOIN causes. If this regresses to the
    # default "select", every floor/enemy access becomes a lazy round trip.
    dungeon_rels = inspect(DungeonRow).relationships
    floor_rels = inspect(FloorRow).relationships
    assert dungeon_rels["floors"].lazy == "selectin"
    assert dungeon_rels["player"].lazy == "selectin"
    assert floor_rels["enemies"].lazy == "selectin"


def test_player_relationship_is_one_to_one() -> None:
    # The player is a single row per dungeon, not a collection.
    assert inspect(DungeonRow).relationships["player"].uselist is False


def test_floors_are_ordered_by_index() -> None:
    # Floors must come back in depth order, not insertion/PK order.
    order_by = inspect(DungeonRow).relationships["floors"].order_by
    assert [c.name for c in order_by] == ["floor_index"]


def test_aggregate_cascades_delete_orphan() -> None:
    # Deleting a dungeon must take its floors/player with it, and a floor its
    # enemies — otherwise orphan rows accumulate.
    dungeon_rels = inspect(DungeonRow).relationships
    floor_rels = inspect(FloorRow).relationships
    for rel in (dungeon_rels["floors"], dungeon_rels["player"], floor_rels["enemies"]):
        assert rel.cascade.delete_orphan is True


def test_scores_has_leaderboard_composite_index() -> None:
    # top_n / rank_of sort by value DESC, computed_at ASC; the composite index
    # must span exactly those two columns *in that order and those directions*.
    # Asserting direction matters: a plain (value, computed_at) index cannot
    # serve the mixed-direction ORDER BY, so if .desc()/.asc() regress to bare
    # columns this must fail.
    scores = Base.metadata.tables["scores"]
    composite = [idx for idx in scores.indexes if len(idx.columns) == 2]
    assert [idx.name for idx in composite] == ["ix_scores_value_computed_at"]

    def direction(expr: object) -> str:
        modifier = getattr(expr, "modifier", None)
        if modifier is operators.desc_op:
            return "DESC"
        if modifier is operators.asc_op:
            return "ASC"
        return "NONE"

    ordering = [
        (getattr(expr, "element", expr).name, direction(expr)) for expr in composite[0].expressions
    ]
    assert ordering == [("value", "DESC"), ("computed_at", "ASC")]


def test_scores_has_no_foreign_keys() -> None:
    # Deliberate: a Score outlives its run (active runs live in Redis and may be
    # GC'd), so it must not be coupled to the dungeon lifecycle via an FK.
    scores = Base.metadata.tables["scores"]
    assert scores.foreign_keys == set()


def test_player_fk_uses_naming_convention() -> None:
    # Now that real constraints exist, confirm the convention on Base.metadata
    # actually names them (complements tests/unit/adapters/db/test_base.py).
    players = Base.metadata.tables["players"]
    fk_names = {c.name for c in players.constraints if isinstance(c, ForeignKeyConstraint)}
    assert fk_names == {"fk_players_dungeon_id_dungeons"}


def test_orm_rows_are_distinct_from_domain() -> None:
    # The ORM classes are separate from the domain dataclasses (BOARD 2.3).
    # A domain Enemy has no __tablename__; the ORM EnemyRow does.
    assert EnemyRow.__tablename__ == "enemies"
    assert ScoreRow.__tablename__ == "scores"
    assert PlayerRow.__tablename__ == "players"
