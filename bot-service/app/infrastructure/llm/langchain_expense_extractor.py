"""LangChain-based expense extractor.

Provider-agnostic: the concrete LLM is selected by `LLM_PROVIDER`
(`openai`, `google_genai`, etc.) and resolved through LangChain's
`init_chat_model`. The same code path works for any provider that
LangChain supports — that's the point of this layer.

Auth keys are passed to providers via their well-known environment
variables (e.g. `OPENAI_API_KEY`, `GOOGLE_API_KEY`) instead of as
constructor kwargs, because each LangChain integration uses a
different kwarg name. Mapping happens in `_apply_provider_api_key`.
"""

import os
from decimal import Decimal, InvalidOperation
from typing import Protocol

from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.domain.categories import EXPENSE_CATEGORIES, EXPENSE_CATEGORIES_SET
from app.domain.expense import ParsedExpense

# Maps the value of LLM_PROVIDER to the env var that the corresponding
# LangChain provider package reads to pick up its API key.
_PROVIDER_API_KEY_ENV_VARS: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "google_genai": "GOOGLE_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "groq": "GROQ_API_KEY",
    "mistralai": "MISTRAL_API_KEY",
    "together": "TOGETHER_API_KEY",
    "fireworks": "FIREWORKS_API_KEY",
    # Local-only providers (no API key required) intentionally omitted:
    # ollama, llama_cpp.
}


def _apply_provider_api_key(llm_provider: str, llm_api_key: str) -> None:
    env_var = _PROVIDER_API_KEY_ENV_VARS.get(llm_provider)
    if env_var and llm_api_key:
        os.environ[env_var] = llm_api_key


class _ExpenseExtractionOutput(BaseModel):
    is_expense: bool = Field(
        description=(
            "True only when the message clearly represents an expense that should be recorded."
        )
    )
    description: str | None = Field(
        default=None,
        description="Short expense description in plain text.",
    )
    amount: str | None = Field(
        default=None,
        description="Numeric amount without currency symbol. Example: 20 or 20.50",
    )
    category: str | None = Field(
        default=None,
        description=f"One of: {', '.join(EXPENSE_CATEGORIES)}",
    )


class _AsyncChain(Protocol):
    async def ainvoke(self, input: dict[str, str]) -> _ExpenseExtractionOutput:
        ...


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


class LangChainExpenseExtractor:
    def __init__(
        self,
        llm_provider: str,
        llm_model_name: str,
        llm_api_key: str,
        chain: _AsyncChain | None = None,
    ) -> None:
        if chain is not None:
            # Test seam: callers can inject a stub chain, skipping LLM init entirely.
            self._chain = chain
            return

        _apply_provider_api_key(llm_provider, llm_api_key)

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    (
                        "You extract expense information from user messages. "
                        "Classify only clear expense statements. "
                        f"Valid categories: {', '.join(EXPENSE_CATEGORIES)}. "
                        "Return amount as plain numeric text. "
                        "If it is not an expense, set is_expense=false and keep other fields null."
                    ),
                ),
                ("human", "{message_text}"),
            ]
        )
        chat_model = init_chat_model(
            model=llm_model_name,
            model_provider=llm_provider,
            temperature=0,
        )
        self._chain = prompt | chat_model.with_structured_output(_ExpenseExtractionOutput)

    async def extract(self, message_text: str) -> ParsedExpense | None:
        result = await self._chain.ainvoke({"message_text": message_text})

        if not result.is_expense:
            return None

        if result.description is None or result.amount is None or result.category is None:
            return None

        description = result.description.strip()
        if description == "":
            return None

        amount = _normalize_amount(result.amount)
        if amount is None:
            return None

        category = result.category.strip()
        if category not in EXPENSE_CATEGORIES_SET:
            category = "Other"

        return ParsedExpense(
            description=description,
            amount=amount,
            category=category,
        )
