from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ParsedExpense:
    description: str
    amount: Decimal
    category: str
