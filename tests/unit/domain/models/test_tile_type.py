from src.domain.models import TileType


def test_tile_type_members() -> None:
    assert set(TileType) == {
        TileType.WALL,
        TileType.FLOOR,
        TileType.STAIRS,
        TileType.DOOR,
    }


def test_tile_type_values_are_uppercase_strings() -> None:
    for variant in TileType:
        assert variant.value == variant.name
        assert variant.value.isupper()


def test_tile_type_is_str_enum() -> None:
    assert isinstance(TileType.WALL, str)
    assert TileType.WALL == "WALL"
    assert TileType.FLOOR == "FLOOR"
    assert TileType.STAIRS == "STAIRS"
    assert TileType.DOOR == "DOOR"


def test_tile_type_variants_are_singletons() -> None:
    assert TileType.WALL is TileType.WALL
    assert TileType("WALL") is TileType.WALL
    assert TileType.WALL is not TileType.FLOOR
