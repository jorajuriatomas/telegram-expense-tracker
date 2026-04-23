-- Schema mirrors the DDL from the challenge PDF (Darwin AI Engineering Seniority Test).
-- Quoted identifiers and column types are preserved as specified.

CREATE TABLE IF NOT EXISTS users (
    "id" SERIAL PRIMARY KEY,
    "telegram_id" text UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS expenses (
    "id" SERIAL PRIMARY KEY,
    "user_id" integer NOT NULL REFERENCES users("id"),
    "description" text NOT NULL,
    "amount" money NOT NULL,
    "category" text NOT NULL,
    "added_at" timestamp NOT NULL
);

-- Supporting index for the most common access pattern (per-user history).
CREATE INDEX IF NOT EXISTS idx_expenses_user_id ON expenses ("user_id");
