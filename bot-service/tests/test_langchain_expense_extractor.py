import asyncio
from types import SimpleNamespace

from app.infrastructure.llm.langchain_expense_extractor import LangChainExpenseExtractor


class FakeChain:
    def __init__(self, response: SimpleNamespace) -> None:
        self._response = response

    async def ainvoke(self, _input: dict[str, str]) -> SimpleNamespace:
        return self._response


def test_extract_returns_expense_for_valid_llm_output() -> None:
    async def run() -> None:
        extractor = LangChainExpenseExtractor(
            llm_provider="openai",
            llm_model_name="gpt-4o-mini",
            llm_api_key="test-key",
            chain=FakeChain(
                SimpleNamespace(
                    is_expense=True,
                    description="Lunch",
                    amount="23.50",
                    category="Food",
                )
            ),
        )

        result = await extractor.extract("Lunch 23.50")

        assert result is not None
        assert result.description == "Lunch"
        assert str(result.amount) == "23.50"
        assert result.category == "Food"

    asyncio.run(run())


def test_extract_returns_none_for_non_expense_output() -> None:
    async def run() -> None:
        extractor = LangChainExpenseExtractor(
            llm_provider="openai",
            llm_model_name="gpt-4o-mini",
            llm_api_key="test-key",
            chain=FakeChain(
                SimpleNamespace(
                    is_expense=False,
                    description=None,
                    amount=None,
                    category=None,
                )
            ),
        )

        result = await extractor.extract("Good morning")

        assert result is None

    asyncio.run(run())


def test_extract_falls_back_to_other_for_unknown_category() -> None:
    async def run() -> None:
        extractor = LangChainExpenseExtractor(
            llm_provider="openai",
            llm_model_name="gpt-4o-mini",
            llm_api_key="test-key",
            chain=FakeChain(
                SimpleNamespace(
                    is_expense=True,
                    description="Gym pass",
                    amount="40",
                    category="Fitness",
                )
            ),
        )

        result = await extractor.extract("Gym pass 40")

        assert result is not None
        assert result.category == "Other"

    asyncio.run(run())


def test_extract_returns_none_for_invalid_amount() -> None:
    async def run() -> None:
        extractor = LangChainExpenseExtractor(
            llm_provider="openai",
            llm_model_name="gpt-4o-mini",
            llm_api_key="test-key",
            chain=FakeChain(
                SimpleNamespace(
                    is_expense=True,
                    description="Dinner",
                    amount="abc",
                    category="Food",
                )
            ),
        )

        result = await extractor.extract("Dinner abc")

        assert result is None

    asyncio.run(run())


def test_extract_returns_none_for_blank_description() -> None:
    async def run() -> None:
        extractor = LangChainExpenseExtractor(
            llm_provider="openai",
            llm_model_name="gpt-4o-mini",
            llm_api_key="test-key",
            chain=FakeChain(
                SimpleNamespace(
                    is_expense=True,
                    description="   ",
                    amount="12",
                    category="Food",
                )
            ),
        )

        result = await extractor.extract("12")

        assert result is None

    asyncio.run(run())
