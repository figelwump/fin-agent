-- 005_accounts_last4.sql
-- Add last_4_digits to accounts, drop UNIQUE(name), and enforce
-- uniqueness on (institution, account_type, last_4_digits) when present.

BEGIN;

-- Rebuild accounts table to add last_4_digits and remove UNIQUE(name)
CREATE TABLE IF NOT EXISTS accounts_tmp (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    institution TEXT NOT NULL,
    account_type TEXT NOT NULL,
    last_4_digits TEXT,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_import DATE,
    auto_detected BOOLEAN DEFAULT TRUE
);

-- Copy existing data; last_4_digits remains NULL for legacy rows
INSERT INTO accounts_tmp (
    id, name, institution, account_type, created_date, last_import, auto_detected
) SELECT id, name, institution, account_type, created_date, last_import, auto_detected
  FROM accounts;

DROP TABLE accounts;
ALTER TABLE accounts_tmp RENAME TO accounts;

-- Partial unique index on (institution, account_type, last_4_digits) when last4 present
CREATE UNIQUE INDEX IF NOT EXISTS idx_accounts_inst_type_last4
    ON accounts(institution, account_type, last_4_digits)
    WHERE last_4_digits IS NOT NULL;

-- Helper index for common lookup path
CREATE INDEX IF NOT EXISTS idx_accounts_inst_last4
    ON accounts(institution, last_4_digits);

COMMIT;

