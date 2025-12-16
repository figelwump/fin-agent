-- 008_documents_source_file_hash.sql
-- Add source_file_hash column to documents table for tracking original PDF hashes.
-- This enables the 'fin-query unimported' command to identify files not yet imported.

BEGIN;

-- Add column for original source file hash (before scrubbing)
-- Nullable for backwards compatibility with existing documents
ALTER TABLE documents ADD COLUMN source_file_hash TEXT;

-- Index for efficient lookups when checking if a file has been imported
CREATE INDEX IF NOT EXISTS idx_documents_source_file_hash
    ON documents(source_file_hash)
    WHERE source_file_hash IS NOT NULL;

COMMIT;
