from weather_core.wmo import ICON_KEYS, condition


def test_known_code() -> None:
    c = condition(63)
    assert (c.code, c.label, c.icon) == (63, "Moderate rain", "rain")


def test_unknown_code_does_not_raise() -> None:
    assert condition(42).icon == "unknown"


def test_night_variant_only_for_sky_icons() -> None:
    assert condition(0, is_day=False).icon == "clear-night"
    assert condition(2, is_day=False).icon == "partly-cloudy-night"
    assert condition(61, is_day=False).icon == "rain"


def test_icon_vocabulary_is_closed() -> None:
    for code in (*range(100),):
        for is_day in (True, False):
            assert condition(code, is_day=is_day).icon in ICON_KEYS
