from src.domain.models import LeaderboardPeriod


def test_leaderboard_period_members() -> None:
    assert set(LeaderboardPeriod) == {
        LeaderboardPeriod.GLOBAL,
        LeaderboardPeriod.WEEKLY,
    }


def test_leaderboard_period_values_are_uppercase_strings() -> None:
    for variant in LeaderboardPeriod:
        assert variant.value == variant.name
        assert variant.value.isupper()


def test_leaderboard_period_is_str_enum() -> None:
    assert isinstance(LeaderboardPeriod.GLOBAL, str)
    assert LeaderboardPeriod.GLOBAL == "GLOBAL"
    assert LeaderboardPeriod.WEEKLY == "WEEKLY"


def test_leaderboard_period_variants_are_singletons() -> None:
    assert LeaderboardPeriod.GLOBAL is LeaderboardPeriod.GLOBAL
    assert LeaderboardPeriod("GLOBAL") is LeaderboardPeriod.GLOBAL
    assert LeaderboardPeriod.GLOBAL is not LeaderboardPeriod.WEEKLY
