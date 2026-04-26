-- Add group-level duplicate metrics to detection_runs.
-- Existing rows will default to 0 (NULL is coerced at query time).

ALTER TABLE detection_runs
    ADD COLUMN IF NOT EXISTS duplicate_group_count  INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS affected_record_count  INTEGER DEFAULT 0;

-- Back-fill legacy rows so they never surface as NULL.
UPDATE detection_runs
SET
    duplicate_group_count = COALESCE(duplicate_group_count, 0),
    affected_record_count = COALESCE(affected_record_count, 0)
WHERE duplicate_group_count IS NULL
   OR affected_record_count IS NULL;

CREATE INDEX IF NOT EXISTS idx_detection_runs_duplicate_group_count
    ON detection_runs (duplicate_group_count);
