from app.infrastructure.postgres.schema import parse_telegram_ids


def test_parse_returns_empty_for_empty_input() -> None:
    valid, invalid = parse_telegram_ids("")
    assert valid == []
    assert invalid == []


def test_parse_single_id() -> None:
    valid, invalid = parse_telegram_ids("1218557035")
    assert valid == ["1218557035"]
    assert invalid == []


def test_parse_comma_separated_list() -> None:
    valid, invalid = parse_telegram_ids("1,2,3")
    assert valid == ["1", "2", "3"]
    assert invalid == []


def test_parse_tolerates_whitespace_around_entries() -> None:
    valid, invalid = parse_telegram_ids(" 1, 2 ,3  ")
    assert valid == ["1", "2", "3"]
    assert invalid == []


def test_parse_skips_empty_entries_from_trailing_commas() -> None:
    valid, invalid = parse_telegram_ids("1,,2,")
    assert valid == ["1", "2"]
    assert invalid == []


def test_parse_separates_invalid_non_numeric_entries() -> None:
    valid, invalid = parse_telegram_ids("1,abc,2,xyz")
    assert valid == ["1", "2"]
    assert invalid == ["abc", "xyz"]
