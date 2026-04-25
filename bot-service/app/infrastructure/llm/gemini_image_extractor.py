"""Receipt-image expense extractor via Gemini Vision.

Unlike the text extractor (provider-agnostic via init_chat_model),
this one is intentionally pinned to `google_genai`. Multimodal support
across LangChain providers is uneven: each vendor has its own image
encoding conventions, and Gemini was the first to ship a stable
production-ready vision model on the free tier.

If the day comes that another provider supports vision and we want to
swap, the change is local: rename the class, keep the same Protocol
interface, and update wiring in `main.py`.
"""

import base64
import logging
import os
from decimal import Decimal, InvalidOperation
from typing import Protocol

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from app.domain.categories import EXPENSE_CATEGORIES, EXPENSE_CATEGORIES_SET
from app.domain.expense import ParsedExpense

logger = logging.getLogger(__name__)


class _ImageExpenseExtractionOutput(BaseModel):
    is_expense: bool = Field(
        description=(
            "True only when the image clearly shows a receipt, invoice, "
            "or transaction record that should be persisted as an expense."
        )
    )
    description: str | None = Field(
        default=None,
        description=(
            "Short description: the merchant name if visible, or the most "
            "prominent item on the receipt."
        ),
    )
    amount: str | None = Field(
        default=None,
        description=(
            "TOTAL amount paid (final figure), as plain numeric text "
            "without currency symbol. Example: 20 or 1234.56"
        ),
    )
    category: str | None = Field(
        default=None,
        description=f"One of: {', '.join(EXPENSE_CATEGORIES)}",
    )


class _AsyncChain(Protocol):
    async def ainvoke(self, messages: list[HumanMessage]) -> _ImageExpenseExtractionOutput:
        ...


def _normalize_amount(raw_amount: str) -> Decimal | None:
    """Same numeric normalization as the text extractor."""
    normalized = raw_amount.strip().replace(" ", "")
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


_PROMPT = (
    "You analyze receipt or invoice images. Extract the TOTAL amount paid "
    "(the final figure on the receipt, not subtotals or individual items), "
    "a short description (the merchant name if visible, otherwise the most "
    "prominent item), and the most appropriate category from this fixed list: "
    f"{', '.join(EXPENSE_CATEGORIES)}. "
    "If the image is NOT a receipt, invoice, or expense-related document "
    "(e.g. it's a meme, a selfie, a screenshot of something unrelated), "
    "set is_expense=false and leave the other fields null."
)


class GeminiImageExpenseExtractor:
    def __init__(
        self,
        llm_model_name: str,
        llm_api_key: str,
        chain: _AsyncChain | None = None,
    ) -> None:
        if chain is not None:
            # Test seam: callers can inject a stub chain, skipping LLM init entirely.
            self._chain = chain
            return

        # Gemini's library reads GOOGLE_API_KEY from the environment.
        # We translate the generic LLM_API_KEY for consistency with the text path.
        if llm_api_key:
            os.environ["GOOGLE_API_KEY"] = llm_api_key

        chat_model = init_chat_model(
            model=llm_model_name,
            model_provider="google_genai",
            temperature=0,
        )
        self._chain = chat_model.with_structured_output(_ImageExpenseExtractionOutput)

    async def extract(
        self,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
    ) -> ParsedExpense | None:
        """Run Gemini Vision against the receipt image.

        Returns a ParsedExpense if the image is a recognizable expense,
        or None otherwise (consistent with the text extractor's contract).
        """
        encoded = base64.b64encode(image_bytes).decode("ascii")
        data_url = f"data:{mime_type};base64,{encoded}"

        message = HumanMessage(
            content=[
                {"type": "text", "text": _PROMPT},
                {"type": "image_url", "image_url": data_url},
            ]
        )

        try:
            result = await self._chain.ainvoke([message])
        except Exception:
            logger.exception("Gemini Vision invocation failed")
            return None

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
