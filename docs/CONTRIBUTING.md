# Contributing

Recipes for the most common changes someone might want to make to this project. Each recipe lists exactly what files to touch and in what order.

If you are new to the codebase, read [`ARCHITECTURE.md`](ARCHITECTURE.md) first to understand how the pieces fit together.

---

## Before you start

Verify the test suite passes on a clean checkout:

```bash
# Bot service
cd bot-service
pip install -r requirements.txt pytest httpx
pytest -q

# Connector service
cd ../connector-service
npm install
npm test
```

If either suite is failing on `main`, fix that before touching anything else. Do not add new code on top of a broken baseline.

---

## Recipe: Add a new LLM provider

Goal: support an additional LLM provider so users can switch with three `.env` lines.

1. **Add the LangChain integration package** to `bot-service/requirements.txt`:

   ```
   langchain-mistralai==0.2.4
   ```

   And mirror it in `bot-service/pyproject.toml` under `[project].dependencies`.

2. **Map the provider's API key env var** in `bot-service/app/infrastructure/llm/langchain_expense_extractor.py`, in the `_PROVIDER_API_KEY_ENV_VARS` table:

   ```python
   _PROVIDER_API_KEY_ENV_VARS = {
       ...,
       "mistralai": "MISTRAL_API_KEY",
   }
   ```

   The key is the LangChain `model_provider` id; the value is whatever env var the provider's library reads its API key from.

3. **Set `.env`** to use the new provider:

   ```
   LLM_PROVIDER=mistralai
   LLM_MODEL_NAME=mistral-large-latest
   LLM_API_KEY=your-mistral-key
   ```

4. **Rebuild the bot service** (new dep requires a fresh image):

   ```bash
   docker compose up --build -d bot-service
   ```

No other code changes. The extractor's `init_chat_model` call is provider-agnostic.

---

## Recipe: Add a new expense category

The 11 categories from the PDF are defined in `bot-service/app/domain/categories.py`:

```python
EXPENSE_CATEGORIES: tuple[str, ...] = (
    "Housing", "Transportation", "Food", "Utilities", "Insurance",
    "Medical/Healthcare", "Savings", "Debt", "Education",
    "Entertainment", "Other",
)
```

To add one (e.g. `"Travel"`):

1. **Append to `EXPENSE_CATEGORIES`.** Both `EXPENSE_CATEGORIES_SET` and the LLM prompt automatically pick it up.

2. **No DB schema change required** — the `category` column is `text`.

3. **Add a test case** in `bot-service/tests/test_langchain_expense_extractor.py` covering the new category to confirm the extractor recognizes it.

> ⚠️ Adding categories beyond the 11 is a deviation from the PDF spec. The reviewer expects exactly those 11.

---

## Recipe: Add a new slash command

Suppose you want to add `/today` (sum of expenses for today only).

1. **Register the command** in `bot-service/app/application/command_handler.py`:

   - Add `"/today"` to the `_HANDLED_COMMANDS` tuple.
   - Add an entry to `self._handlers` in `__init__`: `"/today": self._today`.
   - Update `_HELP_TEXT` so `/help` lists the new command.

2. **Implement the handler** as a method:

   ```python
   async def _today(self, user_id: int, _args: str) -> str:
       since = datetime.combine(date.today(), time.min)
       amount = await self._query_repository.total(user_id=user_id, since=since)
       return f"{_format_amount(amount)} spent today."
   ```

3. **If the command needs a new query**, add a method to `ExpenseQueryRepository` (Protocol in `command_handler.py`, implementation in `infrastructure/postgres/expense_query_repository.py`). The existing methods cover most cases (`total`, `summary_by_category`, `last_n`); reuse them when possible.

4. **Add tests** in `tests/test_command_handler.py` using the `InMemoryQueryRepository` pattern. At minimum: happy path, empty-data case, formatting verification.

5. **No connector changes required.** The connector forwards every text to the bot; the routing happens entirely on the bot side.

---

## Recipe: Change the reply format

The reply is built in `bot-service/app/application/process_message.py`:

```python
return ProcessMessageResponse(
    should_reply=True,
    reply_text=f"[{parsed_expense.category}] expense added \u2705",
)
```

To change it, edit that f-string. Update `bot-service/tests/test_process_message_api.py` to match the new format.

> ⚠️ The PDF specifies the literal string `"[Category] expense added ✅"`. Any other format is a deviation from spec and may fail acceptance tests.

---

## Recipe: Add a new field to the `expenses` table

Suppose you want to add a `currency` column.

1. **Schema**: edit `infra/postgres/init/001_schema.sql` AND `bot-service/app/infrastructure/postgres/schema.py` (the `_SCHEMA_SQL` constant). The first runs at first-init for local Docker; the second runs at every startup for managed-Postgres providers. For an existing local volume, also write a migration script as `infra/postgres/init/003_add_currency.sql`. For an evolving schema in production, switch to Alembic.

   ```sql
   ALTER TABLE expenses ADD COLUMN "currency" text NOT NULL DEFAULT 'USD';
   ```

2. **Domain**: add the field to `bot-service/app/domain/expense.py` `ExpenseToSave`:

   ```python
   currency: str
   ```

3. **LLM extraction**: add the field to `_ExpenseExtractionOutput` in `bot-service/app/infrastructure/llm/langchain_expense_extractor.py` and update the prompt to instruct the LLM to extract it.

4. **Persistence**: update the INSERT in `bot-service/app/infrastructure/postgres/expense_repository.py` to include the new column.

5. **Tests**: update `tests/test_expense_repository.py` and `tests/test_process_message_api.py` to cover the new field.

6. If the field also needs to come from the connector (not from the LLM), update the request schema in `bot-service/app/interface/http/schemas.py` AND the contract type in `connector-service/src/contracts/botService.ts`.

---

## Recipe: Add a new endpoint to the bot service

Suppose you want to add `GET /expenses/{telegram_user_id}` to query past expenses.

1. **Schema**: add a response model to `bot-service/app/interface/http/schemas.py`.

   ```python
   class ListExpensesResponse(BaseModel):
       expenses: list[ExpenseSummary]
   ```

2. **Use case**: create `bot-service/app/application/list_expenses.py` with a `ListExpensesUseCase` class that depends on a new Protocol (e.g. `ExpenseQueryRepository.find_by_telegram_id`).

3. **Repository**: implement the Protocol in `bot-service/app/infrastructure/postgres/expense_repository.py` (or a new file if it gets large).

4. **Wiring**: in `bot-service/app/main.py`, build the new use case inside `create_app` and add the endpoint:

   ```python
   list_expenses_use_case = ListExpensesUseCase(...)

   @app.get("/expenses/{telegram_user_id}")
   async def list_expenses(telegram_user_id: str) -> ListExpensesResponse:
       return await list_expenses_use_case.execute(telegram_user_id)
   ```

5. **Tests**: write a test for the use case (with an in-memory fake repository) and one for the endpoint (with `TestClient`).

---

## Recipe: Add a new env var

Say you want a `MAX_EXPENSE_AMOUNT` configurable cap.

1. **Document it** in the top-level `.env.example` with a comment explaining purpose and default.

2. **Bot service consumption**: add to `bot-service/app/core/config.py`:

   ```python
   max_expense_amount: Decimal = Field(alias="MAX_EXPENSE_AMOUNT")
   ```

3. **Connector service consumption** (if applicable): add to `connector-service/src/config/env.ts` `requireEnv()` call and the `Env` type.

4. **Wire to docker-compose**: add to the relevant service's `environment` block in `docker-compose.yml`:

   ```yaml
   environment:
     ...
     MAX_EXPENSE_AMOUNT: ${MAX_EXPENSE_AMOUNT}
   ```

5. **Use it** in code, reading from `get_settings()` in the bot service or the imported `env` object in the connector.

---

## Recipe: Switch from money to numeric in the schema

If you want to drop the `money` column type (which is generally considered a Postgres anti-pattern):

1. **Schema**: change the column type in `001_schema.sql`:

   ```sql
   "amount" numeric(12, 2) NOT NULL CHECK (amount > 0),
   ```

2. **Repository**: remove the `CAST(:amount::numeric::money)` workaround in `expense_repository.py`. It becomes just `:amount`.

3. **Tests**: no change needed (they pass `Decimal` either way).

> ⚠️ This is a deviation from the PDF DDL. Document it in the README's "design decisions" section if you make this change.

---

## Common gotchas

- **Postgres init scripts only run on first volume init.** If you change `001_schema.sql` or `002_seed.sh`, they will NOT re-run on a `docker compose up` against an existing volume. To force re-init: `docker compose down -v && docker compose up`.

- **`.sh` init scripts see env vars; `.sql` files do not.** That's why the seed is `.sh`. If you write a new init script that needs container env vars, it must be `.sh`.

- **`docker compose restart` does NOT pick up code changes.** The Dockerfiles `COPY` source at build time. To take a code change, use `docker compose up --build`.

- **Tests must not import `app.asgi`.** That module instantiates the app and triggers LLM client initialization. Tests should import `app.main` and call `create_app(use_case=...)` themselves.

- **The connector ACKs the webhook BEFORE processing.** If you change this, you risk Telegram retries → duplicate persistence. Don't change it without compensating somewhere (e.g. idempotency at the DB layer).

- **`telegram_id` is `text`.** Don't coerce it to `int` anywhere. Telegram IDs are numeric in practice but the PDF models them as text and the FK target type is text.

- **`added_at` is naive UTC after the connector.** The connector sends ISO-8601 with `Z`; Pydantic parses it as tz-aware; the repository normalizes to naive UTC before binding because asyncpg refuses tz-aware values for `timestamp` columns.

---

## Testing guidelines

- **Tests must be hermetic**: no real LLM, no real Telegram, no real Postgres. If you need to test against a real DB, use `testcontainers` or similar — but isolate it in a separate suite (`integration-tests/`) so the unit tests stay fast.

- **Bot service**: use the in-memory fakes pattern from `tests/test_process_message_api.py`. For the LangChain extractor, pass a `chain=FakeChain(...)` to skip LLM init.

- **Connector service**: use plain object stubs as in `tests/processTelegramUpdate.test.ts`. The use case accepts any object that matches the shape of `botServiceClient` and `telegramClient`.

- **Aim for the use case layer.** That's where the bulk of behavioral coverage lives per line of code. Repositories and HTTP handlers can be thinner on tests if the use case is well-covered.

- **A new feature ships with tests.** No exceptions. Even a one-line change that affects behavior should be backed by a test.

---

## Code style

- Python: type hints on everything; docstrings on classes and public functions; no comments that just rephrase the code.
- TypeScript: strict mode is on; type imports use `import type`; no `any` unless there's a comment justifying it.
- Both: small modules. If a file is over ~150 lines, consider whether it has more than one responsibility.
