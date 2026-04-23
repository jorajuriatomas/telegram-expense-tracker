from decimal import Decimal

from app.application.basic_expense_parser import BasicExpenseParser


def test_parses_simple_expense_message() -> None:
    parser = BasicExpenseParser()

    parsed = parser.parse("Pizza 20 bucks")

    assert parsed is not None
    assert parsed.description == "Pizza"
    assert parsed.amount == Decimal("20")
    assert parsed.category == "Other"


def test_returns_none_when_message_is_not_expense() -> None:
    parser = BasicExpenseParser()

    parsed = parser.parse("Hello, how are you?")

    assert parsed is None
