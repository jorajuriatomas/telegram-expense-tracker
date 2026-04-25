#!/bin/bash
# Optional seed: insert one or more users into the whitelist on first DB init.
#
# INITIAL_TELEGRAM_IDS is a comma-separated list of Telegram numeric ids:
#   INITIAL_TELEGRAM_IDS=123456789
#   INITIAL_TELEGRAM_IDS=123456789,9876543210,5555555555
#
# Postgres' init mechanism runs files in /docker-entrypoint-initdb.d/ in
# alphabetical order; .sh files (unlike .sql) inherit container env vars,
# which is why this is a shell script.
#
# This only runs the first time the volume is initialized. To re-trigger it,
# blow away the volume: `docker compose down -v && docker compose up`.
set -euo pipefail

if [[ -z "${INITIAL_TELEGRAM_IDS:-}" ]]; then
    echo "[seed] INITIAL_TELEGRAM_IDS is empty; skipping whitelist seed."
    exit 0
fi

IFS=',' read -ra ids <<< "$INITIAL_TELEGRAM_IDS"

for raw_id in "${ids[@]}"; do
    # Strip all whitespace; Telegram user ids are numeric so this is safe.
    id="$(echo -n "$raw_id" | tr -d '[:space:]')"

    if [[ -z "$id" ]]; then
        continue
    fi

    # Defensive validation: refuse anything that isn't a positive integer.
    # Protects against typos in the env var AND any SQL-injection risk.
    if ! [[ "$id" =~ ^[0-9]+$ ]]; then
        echo "[seed] WARN: skipping invalid telegram_id (not numeric): '${raw_id}'"
        continue
    fi

    echo "[seed] Inserting telegram_id=${id} into users (if missing)."
    psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --variable=ON_ERROR_STOP=1 <<-SQL
        INSERT INTO users ("telegram_id")
        VALUES ('${id}')
        ON CONFLICT ("telegram_id") DO NOTHING;
SQL
done
