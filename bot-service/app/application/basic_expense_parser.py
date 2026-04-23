import re
from decimal import Decimal, InvalidOperation

from app.domain.expense import ParsedExpense

_AMOUNT_PATTERN = re.compile(
    r"(?<!\w)(?:\$\s*)?(\d+(?:[.,]\d{1,2})?)(?:\s*(?:usd|dollars?|bucks?))?(?!\w)",
    re.IGNORECASE,
)
_MULTISPACE_PATTERN = re.compile(r"\s+")


def _normalize_amount(raw_amount: str) -> Decimal | None:
    normalized = raw_amount.strip()
    if "," in normalized and "." in normalized:
        normalized = normalized.replace(",", "")
    elif "," in normalized:
        normalized = normalized.replace(",", ".")

    try:
        amount = Decimal(normalized)
    except InvalidOperation:
        return None

    if amount <= 0:
        return None
    return amount


def _normalize_description(message_text: str, amount_match: re.Match[str]) -> str:
    text_without_amount = (
        f"{message_text[:amount_match.start()]} {message_text[amount_match.end():]}".strip()
    )
    text_without_amount = _MULTISPACE_PATTERN.sub(" ", text_without_amount)
    return text_without_amount.strip(" -:,.")


class BasicExpenseParser:
    def parse(self, message_text: str) -> ParsedExpense | None:
        amount_match = _AMOUNT_PATTERN.search(message_text)
        if amount_match is None:
            return None

        amount = _normalize_amount(amount_match.group(1))
        if amount is None:
            return None

        description = _normalize_description(message_text, amount_match)
        if not description:
            return None

        return ParsedExpense(
            description=description,
            amount=amount,
            category="Other",
        )
