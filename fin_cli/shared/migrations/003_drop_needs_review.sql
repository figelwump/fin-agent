-- 003_drop_needs_review.sql
-- Remove the needs_review column from transactions.

BEGIN;

CREATE TABLE IF NOT EXISTS transactions_tmp (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    merchant TEXT NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    category_id INTEGER,
    account_id INTEGER,
    original_description TEXT,
    import_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    categorization_confidence REAL,
    categorization_method TEXT,
    fingerprint TEXT NOT NULL UNIQUE,
    FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE SET NULL,
    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL
);

INSERT INTO transactions_tmp (
    id,
    date,
    merchant,
    amount,
    category_id,
    account_id,
    original_description,
    import_date,
    categorization_confidence,
    categorization_method,
    fingerprint
)
SELECT
    id,
    date,
    merchant,
    amount,
    category_id,
    account_id,
    original_description,
    import_date,
    categorization_confidence,
    categorization_method,
    fingerprint
FROM transactions;

DROP TABLE transactions;
ALTER TABLE transactions_tmp RENAME TO transactions;

CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date);
CREATE INDEX IF NOT EXISTS idx_transactions_account ON transactions(account_id);
CREATE INDEX IF NOT EXISTS idx_transactions_category ON transactions(category_id);

COMMIT;
