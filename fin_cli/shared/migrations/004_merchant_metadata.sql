-- 004_merchant_metadata.sql
-- Add display + metadata columns for merchant patterns and transactions.

BEGIN;

ALTER TABLE merchant_patterns
    ADD COLUMN pattern_display TEXT;

ALTER TABLE merchant_patterns
    ADD COLUMN metadata TEXT CHECK (metadata IS NULL OR json_valid(metadata));

ALTER TABLE transactions
    ADD COLUMN metadata TEXT CHECK (metadata IS NULL OR json_valid(metadata));

COMMIT;
