# Deployment

How to deploy this stack to production-like environments. The same code runs locally with `docker compose up` and in any Docker-friendly hosting platform (Railway, Render, Fly.io, AWS ECS, etc.).

This guide covers Railway in depth (because it has the smoothest free-tier flow for a multi-service stack) and gives high-level pointers for other platforms.

---

## Architectural reminder

The stack has three components:

1. **PostgreSQL** — managed database
2. **Bot Service** — Python/FastAPI container, exposes `:8000`
3. **Connector Service** — Node/Express container, exposes `:3000` publicly

In production, each runs in its own container. Connector talks to bot over the platform's internal network; bot talks to Postgres similarly. Only the connector needs a public domain (so Telegram can reach the webhook).

---

## Railway (recommended for the free tier)

### Prerequisites

- Railway account (https://railway.com) — free tier gives ~$5/month, enough for a demo.
- Code pushed to a GitHub repo.

### Step 1 — Create the project and Postgres

1. New Project → empty.
2. `+ New` → `Database` → `Add PostgreSQL`. Railway provisions it in ~30 seconds.

### Step 2 — Deploy the Bot Service

1. `+ New` → `GitHub Repo` → select your repo.
2. Once the service is created, **Settings**:
   - **Root Directory**: `bot-service`
   - **Builder**: `Dockerfile`
3. **Variables**:
   ```
   BOT_SERVICE_HOST=0.0.0.0
   BOT_SERVICE_PORT=8000
   DATABASE_URL=postgresql+asyncpg://${{Postgres.PGUSER}}:${{Postgres.PGPASSWORD}}@${{Postgres.PGHOST}}:${{Postgres.PGPORT}}/${{Postgres.PGDATABASE}}
   LLM_PROVIDER=google_genai
   LLM_MODEL_NAME=gemini-2.5-flash
   LLM_API_KEY=<your-key>
   LOG_LEVEL=INFO
   INITIAL_TELEGRAM_IDS=<your-telegram-id>
   ```
   Note the explicit `postgresql+asyncpg://` prefix — required for the asyncpg driver. Railway's `${{Postgres.DATABASE_URL}}` variable defaults to the psycopg2 format. The bot also normalizes the URL at startup as a safety net (`app/infrastructure/postgres/connection.py`), so either form works.
4. Trigger Deploy.

On the first boot, the FastAPI lifespan runs `ensure_schema_exists` and creates the `users` and `expenses` tables, plus seeds `INITIAL_TELEGRAM_IDS`. You should see in Deploy Logs:
```
[INFO] Schema ensured (CREATE TABLE IF NOT EXISTS executed)
[INFO] Whitelist seeded with 1 telegram_id(s)
INFO:     Application startup complete.
```

### Step 3 — Deploy the Connector Service

1. `+ New` → `GitHub Repo` → same repo.
2. Settings:
   - **Root Directory**: `connector-service`
   - **Builder**: `Dockerfile`
3. Settings → **Networking** → **Generate Domain**. Copy the URL (e.g. `https://your-connector.up.railway.app`).
4. Variables:
   ```
   PORT=3000
   NODE_ENV=production
   TELEGRAM_BOT_TOKEN=<your-bot-token>
   TELEGRAM_WEBHOOK_SECRET=<random-string>
   TELEGRAM_WEBHOOK_PATH=/telegram/webhook
   TELEGRAM_API_BASE_URL=https://api.telegram.org
   BOT_SERVICE_BASE_URL=http://${{bot-service.RAILWAY_PRIVATE_DOMAIN}}:8000
   BOT_SERVICE_PROCESS_MESSAGE_PATH=/process-message
   ```
   Note `BOT_SERVICE_BASE_URL` uses the **internal** private domain (faster, no public hop) and the explicit port `8000` (where the bot service listens). Railway's auto-injected `${{service.PORT}}` may differ from the application's listening port — hardcode `:8000` to match the Dockerfile.
5. Trigger Deploy.

### Step 4 — Register the Telegram webhook

```bash
curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://<your-connector>.up.railway.app/telegram/webhook","secret_token":"<your-secret>","allowed_updates":["message"]}'
```

Verify:

```bash
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
```

You should see your URL set, `pending_update_count: 0`, and no `last_error_message`.

### Step 5 — Test

Open Telegram, send `Pizza 20 bucks` to your bot. You should receive `[Food] expense added ✅`.

### Adding more whitelist users

You have two options:

**A) Declarative (preferred):** add to `INITIAL_TELEGRAM_IDS` env var (comma-separated). Triggers a redeploy. Only seeds on first DB init unless you reset the volume.

**B) Manual via psql:** in the Postgres service's Data tab (or via DBeaver connected to `DATABASE_PUBLIC_URL`):
```sql
INSERT INTO users ("telegram_id") VALUES ('<numeric_id>') ON CONFLICT DO NOTHING;
```

### Common Railway gotchas

| Symptom | Cause | Fix |
|---|---|---|
| `Error creating build plan with Railpack` | Auto-detection sees a multi-service repo | Set `Root Directory` to `bot-service` or `connector-service` and `Builder` to `Dockerfile` |
| `ModuleNotFoundError: No module named 'psycopg2'` | `DATABASE_URL` lacks the `+asyncpg` driver suffix | Either set explicit prefix in env, or rely on the auto-normalization in `connection.py` |
| `Failed to process Telegram update {error: 'fetch failed'}` | Connector can't reach bot — usually `BOT_SERVICE_BASE_URL` misconfigured | Use `http://${{bot-service.RAILWAY_PRIVATE_DOMAIN}}:8000` |
| Bot starts but `INITIAL_TELEGRAM_IDS empty` despite being set | "Redeploy" button reuses the env snapshot of the original deploy | Trigger a fresh deploy: `git commit --allow-empty -m "trigger" && git push` |
| `cannot insert multiple commands into a prepared statement` | asyncpg rejects multi-statement DDL | Schema is split into individual statements in `schema.py` (already handled) |

### Rotating credentials

When you finish testing, rotate any credentials that left your machine:

- **Gemini key:** https://aistudio.google.com/apikey → delete the key → create a new one → update in Railway.
- **Telegram bot token:** in `@BotFather`, `/revoke` → select your bot → use the new token in Railway and re-register the webhook.

---

## Render

Similar shape to Railway. Each service is a Render "Web Service" pointing to its subdirectory with `Docker` runtime. Render's managed Postgres works the same way as Railway's; the same `+asyncpg` URL adjustment applies.

Differences from Railway:

- Render uses `RENDER_INTERNAL_HOSTNAME` instead of `RAILWAY_PRIVATE_DOMAIN`.
- Render's free tier has cold starts on the web services, which adds ~30s latency to the first request after idle.

---

## Fly.io

Fly is a strong choice if you want geographic deployment or finer-grained control. You'd write a `fly.toml` per service and use `fly deploy` from each subdirectory. Fly's managed Postgres works similarly.

---

## AWS / GCP / Azure (production grade)

For real production, replace the managed-platform pieces with:

- **Containers**: ECS Fargate, Cloud Run, or App Service.
- **Postgres**: RDS, Cloud SQL, or Azure Database for PostgreSQL.
- **Secrets**: AWS Secrets Manager, Google Secret Manager, or Azure Key Vault — replace `.env` with secret refs.
- **Networking**: Put the connector behind ALB/Cloud Load Balancer with a WAF (rate limit DDoS).
- **Migrations**: Switch from the bootstrap-at-startup pattern to Alembic with a dedicated migration job (see [`DECISIONS.md`](DECISIONS.md) ADR-007).
- **Observability**: CloudWatch / Cloud Logging + a metrics backend (Prometheus, Datadog).

---

## Production hardening checklist

Before treating this as a real product (not a demo), at minimum:

- [ ] Replace `INITIAL_TELEGRAM_IDS` with an admin endpoint or admin tooling.
- [ ] Add Alembic migrations and a separate `alembic upgrade head` deploy step.
- [ ] Add request rate limiting in the connector (e.g. Redis-backed).
- [ ] Add HMAC or mTLS between connector and bot (today they trust the network).
- [ ] Pin `CHECK (amount > 0)` (or migrate `money` to `numeric(12,2)` to support it cleanly).
- [ ] Add audit log table with append-only inserts for compliance.
- [ ] Secret manager integration; rotate on a schedule.
- [ ] Structured logging (JSON) shipped to a centralized aggregator.
- [ ] Liveness vs readiness probe distinction in `/health`.
- [ ] Add `pytest-postgres` or `testcontainers` integration tests.
- [ ] Set up CI (GitHub Actions) running both test suites on every PR.
