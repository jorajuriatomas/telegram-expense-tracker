import asyncio
from types import SimpleNamespace

from app.infrastructure.llm.gemini_image_extractor import GeminiImageExpenseExtractor


class FakeChain:
    def __init__(self, response):
        self._response = response
        self.last_messages = None

    async def ainvoke(self, messages):
        self.last_messages = messages
        return self._response


class FailingChain:
    async def ainvoke(self, messages):
        raise RuntimeError("forced LLM failure")


def _build(response, **kwargs):
    return GeminiImageExpenseExtractor(
        llm_model_name="gemini-2.5-flash",
        llm_api_key="test-key",
        chain=FakeChain(response),
        **kwargs,
    )


def test_extracts_valid_receipt() -> None:
    async def run():
        extractor = _build(
            SimpleNamespace(
                is_expense=True,
                description="Pizza Hut",
                amount="42.50",
                category="Food",
            )
        )
        result = await extractor.extract(image_bytes=b"fake-jpeg-bytes")

        assert result is not None
        assert result.description == "Pizza Hut"
        assert str(result.amount) == "42.50"
        assert result.category == "Food"

    asyncio.run(run())


def test_returns_none_when_image_is_not_expense() -> None:
    async def run():
        extractor = _build(
            SimpleNamespace(
                is_expense=False,
                description=None,
                amount=None,
                category=None,
            )
        )
        result = await extractor.extract(image_bytes=b"selfie-bytes")
        assert result is None

    asyncio.run(run())


def test_falls_back_to_other_for_unknown_category() -> None:
    async def run():
        extractor = _build(
            SimpleNamespace(
                is_expense=True,
                description="Gym pass",
                amount="40",
                category="Fitness",
            )
        )
        result = await extractor.extract(image_bytes=b"any")
        assert result is not None
        assert result.category == "Other"

    asyncio.run(run())


def test_returns_none_for_invalid_amount() -> None:
    async def run():
        extractor = _build(
            SimpleNamespace(
                is_expense=True,
                description="Dinner",
                amount="not-a-number",
                category="Food",
            )
        )
        result = await extractor.extract(image_bytes=b"any")
        assert result is None

    asyncio.run(run())


def test_returns_none_when_chain_raises() -> None:
    """LLM failures shouldn't propagate up; the use case should silent-ignore."""

    async def run():
        extractor = GeminiImageExpenseExtractor(
            llm_model_name="gemini-2.5-flash",
            llm_api_key="test-key",
            chain=FailingChain(),
        )
        result = await extractor.extract(image_bytes=b"any")
        assert result is None

    asyncio.run(run())


def test_message_payload_includes_image_data_url() -> None:
    """The chain must receive a HumanMessage with text + base64 data URL."""

    async def run():
        chain = FakeChain(
            SimpleNamespace(is_expense=False, description=None, amount=None, category=None)
        )
        extractor = GeminiImageExpenseExtractor(
            llm_model_name="gemini-2.5-flash",
            llm_api_key="test-key",
            chain=chain,
        )
        await extractor.extract(image_bytes=b"\x89PNG\r\n", mime_type="image/png")

        assert chain.last_messages is not None
        # Single HumanMessage with two content blocks: text + image_url
        message = chain.last_messages[0]
        assert len(message.content) == 2
        assert message.content[0]["type"] == "text"
        assert message.content[1]["type"] == "image_url"
        assert message.content[1]["image_url"].startswith("data:image/png;base64,")

    asyncio.run(run())
