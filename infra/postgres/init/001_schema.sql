DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'expense_category') THEN
        CREATE TYPE expense_category AS ENUM (
            'Housing',
            'Transportation',
            'Food',
            'Utilities',
            'Insurance',
            'Medical/Healthcare',
            'Savings',
            'Debt',
            'Education',
            'Entertainment',
            'Other'
        );
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS whitelist_users (
    telegram_user_id BIGINT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS expenses (
    id BIGSERIAL PRIMARY KEY,
    telegram_user_id BIGINT NOT NULL,
    description TEXT NOT NULL,
    amount NUMERIC(12, 2) NOT NULL CHECK (amount > 0),
    category expense_category NOT NULL,
    source_chat_id BIGINT NOT NULL,
    source_message_id BIGINT NOT NULL,
    source_timestamp TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_expenses_source_message UNIQUE (source_chat_id, source_message_id)
);

CREATE INDEX IF NOT EXISTS idx_expenses_telegram_user_id ON expenses (telegram_user_id);
CREATE INDEX IF NOT EXISTS idx_expenses_created_at ON expenses (created_at DESC);
