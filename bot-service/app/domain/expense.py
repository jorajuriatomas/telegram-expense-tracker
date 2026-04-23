from datetime import datetime
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ParsedExpense:
    description: str
    amount: Decimal
    category: str


@dataclass(frozen=True)
class ExpenseToSave:
    telegram_user_id: int
    description: str
    amount: Decimal
    category: str
    source_chat_id: int
    source_message_id: int
    source_timestamp: datetime
