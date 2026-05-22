from billable.config import Settings, get_settings


def test_get_settings_returns_singleton() -> None:
    assert get_settings() is get_settings()


def test_follow_up_delay_demo_mode_is_short() -> None:
    s = Settings(demo_mode=True)
    assert s.follow_up_delay_seconds == 10


def test_follow_up_delay_production_is_one_day() -> None:
    s = Settings(demo_mode=False)
    assert s.follow_up_delay_seconds == 86_400
