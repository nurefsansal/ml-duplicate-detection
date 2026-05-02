ALTER TABLE raw_records
    ADD COLUMN IF NOT EXISTS batch_id VARCHAR,
    ADD COLUMN IF NOT EXISTS row_index INT;

CREATE TABLE IF NOT EXISTS import_batches (
    batch_id VARCHAR(64) PRIMARY KEY,
    source_name TEXT,
    source_type VARCHAR(32) NOT NULL DEFAULT 'unknown',
    status VARCHAR(32) NOT NULL DEFAULT 'completed',
    record_count INT NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO import_batches (
    batch_id,
    source_name,
    source_type,
    status,
    record_count,
    created_at
)
SELECT
    'upload-' || uploads.id::text,
    uploads.file_name,
    COALESCE(uploads.source_type, 'unknown'),
    COALESCE(uploads.status, 'completed'),
    COALESCE(uploads.total_records, 0),
    COALESCE(uploads.created_at, CURRENT_TIMESTAMP)
FROM uploads
WHERE uploads.id IS NOT NULL
ON CONFLICT (batch_id) DO NOTHING;

UPDATE raw_records
SET batch_id = COALESCE(batch_id, 'upload-' || COALESCE(upload_id::text, 'unknown')),
    row_index = COALESCE(row_index, id)
WHERE (batch_id IS NULL OR row_index IS NULL)
  AND (upload_id IS NULL OR EXISTS (
      SELECT 1
      FROM import_batches
      WHERE import_batches.batch_id = 'upload-' || raw_records.upload_id::text
  ));

CREATE INDEX IF NOT EXISTS idx_raw_records_batch_id ON raw_records(batch_id);
