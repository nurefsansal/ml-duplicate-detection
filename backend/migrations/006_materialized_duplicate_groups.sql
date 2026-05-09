-- Materialize duplicate groups so we can paginate at DB level.
-- Groups are computed during detection runs and stored per decision (pending/approved/rejected).

CREATE TABLE IF NOT EXISTS materialized_duplicate_groups (
    id                  SERIAL PRIMARY KEY,
    detection_run_id     INT NOT NULL REFERENCES detection_runs(id) ON DELETE CASCADE,
    upload_id            INT NOT NULL REFERENCES uploads(id) ON DELETE CASCADE,
    normalization_run_id INT REFERENCES normalization_runs(id) ON DELETE SET NULL,
    decision             VARCHAR(32) NOT NULL DEFAULT 'pending',
    group_key            TEXT NOT NULL,
    record_count         INT NOT NULL DEFAULT 0,
    match_count          INT NOT NULL DEFAULT 0,
    avg_score            DOUBLE PRECISION DEFAULT 0,
    max_score            DOUBLE PRECISION DEFAULT 0,
    different_muhatap_code BOOLEAN NOT NULL DEFAULT FALSE,
    muhatap_codes        JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at           TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
    UNIQUE(detection_run_id, decision, group_key)
);

CREATE INDEX IF NOT EXISTS idx_mat_dup_groups_upload_decision
    ON materialized_duplicate_groups (upload_id, decision);

CREATE INDEX IF NOT EXISTS idx_mat_dup_groups_scores
    ON materialized_duplicate_groups (avg_score DESC, match_count DESC);

CREATE TABLE IF NOT EXISTS materialized_duplicate_group_members (
    group_id             INT NOT NULL REFERENCES materialized_duplicate_groups(id) ON DELETE CASCADE,
    normalized_record_id INT NOT NULL REFERENCES normalized_records(id) ON DELETE CASCADE,
    created_at           TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
    PRIMARY KEY(group_id, normalized_record_id)
);

CREATE INDEX IF NOT EXISTS idx_mat_dup_group_members_group
    ON materialized_duplicate_group_members (group_id);

CREATE INDEX IF NOT EXISTS idx_mat_dup_group_members_record
    ON materialized_duplicate_group_members (normalized_record_id);

