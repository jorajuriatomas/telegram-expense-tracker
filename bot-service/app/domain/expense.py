from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class ParsedExpense:
    """Output of the LLM extraction step (no persistence concerns)."""

    description: str
    amount: Decimal
    category: str


@dataclass(frozen=True)
class ExpenseToSave:
    """Row to be persisted into the `expenses` table (matches PDF DDL)."""

    user_id: int
    description: str
    amount: Decimal
    category: str
    added_at: datetime
