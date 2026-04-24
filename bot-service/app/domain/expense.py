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
    """Write-side model — row to be persisted into `expenses` (matches PDF DDL)."""

    user_id: int
    description: str
    amount: Decimal
    category: str
    added_at: datetime


@dataclass(frozen=True)
class ExpenseRecord:
    """Read-side model — row read back from `expenses` for queries.

    Separate from ExpenseToSave because read concerns differ from write
    concerns (CQRS-lite). Currently identical fields minus `user_id`
    (queries are already scoped per-user), but free to evolve independently.
    """

    description: str
    amount: Decimal
    category: str
    added_at: datetime
