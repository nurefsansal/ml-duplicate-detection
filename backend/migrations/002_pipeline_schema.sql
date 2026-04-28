-- Extend legacy tables without removing or renaming them.

ALTER TABLE uploads
    ADD COLUMN IF NOT EXISTS source_type VARCHAR(32),
    ADD COLUMN IF NOT EXISTS source_name VARCHAR(255),
    ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS processing_stage VARCHAR(64) DEFAULT 'uploaded';

UPDATE uploads
SET processing_stage = COALESCE(processing_stage, status, 'uploaded')
WHERE processing_stage IS NULL;

ALTER TABLE entities
    ADD COLUMN IF NOT EXISTS canonical_tc TEXT,
    ADD COLUMN IF NOT EXISTS confidence FLOAT;

UPDATE entities
SET confidence = COALESCE(confidence, confidence_score, 1.0)
WHERE confidence IS NULL;

CREATE TABLE IF NOT EXISTS raw_records (
    id SERIAL PRIMARY KEY,
    upload_id INT NOT NULL REFERENCES uploads(id) ON DELETE CASCADE,
    raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    ingestion_hash VARCHAR(128),
    row_status VARCHAR(32) DEFAULT 'pending',
    validation_errors JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS column_mappings (
    id SERIAL PRIMARY KEY,
    upload_id INT NOT NULL REFERENCES uploads(id) ON DELETE CASCADE,
    source_column_name VARCHAR(255) NOT NULL,
    target_field_name VARCHAR(128) NOT NULL,
    is_required BOOLEAN DEFAULT FALSE,
    mapping_type VARCHAR(32) DEFAULT 'direct',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_column_mapping_upload_source_target
        UNIQUE (upload_id, source_column_name, target_field_name)
);

CREATE TABLE IF NOT EXISTS normalization_runs (
    id SERIAL PRIMARY KEY,
    upload_id INT NOT NULL REFERENCES uploads(id) ON DELETE CASCADE,
    mapping_id INT REFERENCES column_mappings(id) ON DELETE SET NULL,
    normalization_profile VARCHAR(128),
    total_processed INT DEFAULT 0,
    success_count INT DEFAULT 0,
    failed_count INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS normalized_records (
    id SERIAL PRIMARY KEY,
    raw_id INT NOT NULL REFERENCES raw_records(id) ON DELETE CASCADE,
    upload_id INT NOT NULL REFERENCES uploads(id) ON DELETE CASCADE,
    normalization_run_id INT REFERENCES normalization_runs(id) ON DELETE SET NULL,
    clean_name TEXT,
    first_name TEXT,
    last_name TEXT,
    ordered_name TEXT,
    name_phonetic TEXT,
    clean_phone TEXT,
    phone_last7 VARCHAR(7),
    clean_email TEXT,
    clean_tc TEXT,
    clean_city TEXT,
    clean_address TEXT,
    blocking_key VARCHAR(255),
    is_valid BOOLEAN DEFAULT TRUE,
    normalized_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS detection_runs (
    id SERIAL PRIMARY KEY,
    upload_id INT NOT NULL REFERENCES uploads(id) ON DELETE CASCADE,
    normalization_run_id INT REFERENCES normalization_runs(id) ON DELETE SET NULL,
    model_version VARCHAR(128),
    threshold FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS match_candidates (
    id SERIAL PRIMARY KEY,
    detection_run_id INT NOT NULL REFERENCES detection_runs(id) ON DELETE CASCADE,
    left_id INT NOT NULL REFERENCES normalized_records(id) ON DELETE CASCADE,
    right_id INT NOT NULL REFERENCES normalized_records(id) ON DELETE CASCADE,
    score FLOAT,
    match_type VARCHAR(32),
    decision VARCHAR(32) DEFAULT 'pending',
    confidence FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_match_candidate_run_pair
        UNIQUE (detection_run_id, left_id, right_id)
);

CREATE TABLE IF NOT EXISTS review_actions (
    id SERIAL PRIMARY KEY,
    match_id INT NOT NULL REFERENCES match_candidates(id) ON DELETE CASCADE,
    decision VARCHAR(32) NOT NULL,
    decided_by VARCHAR(255),
    decided_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reason TEXT
);

CREATE TABLE IF NOT EXISTS entity_memberships (
    id SERIAL PRIMARY KEY,
    entity_id INT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    normalized_record_id INT NOT NULL REFERENCES normalized_records(id) ON DELETE CASCADE,
    confidence_at_merge FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_entity_membership_entity_record
        UNIQUE (entity_id, normalized_record_id)
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,
    action_type VARCHAR(64) NOT NULL,
    entity_type VARCHAR(64) NOT NULL,
    entity_id INT NOT NULL,
    payload JSONB DEFAULT '{}'::jsonb,
    created_by VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS jobs (
    id SERIAL PRIMARY KEY,
    type VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    progress FLOAT NOT NULL DEFAULT 0,
    total_rows INT DEFAULT 0,
    processed_rows INT DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_uploads_source_type ON uploads(source_type);
CREATE INDEX IF NOT EXISTS idx_uploads_processing_stage ON uploads(processing_stage);
CREATE INDEX IF NOT EXISTS idx_uploads_completed_at ON uploads(completed_at DESC);

CREATE INDEX IF NOT EXISTS idx_entities_canonical_city ON entities(canonical_city);
CREATE INDEX IF NOT EXISTS idx_entities_canonical_tc ON entities(canonical_tc);

CREATE INDEX IF NOT EXISTS idx_raw_records_upload_id ON raw_records(upload_id);
CREATE INDEX IF NOT EXISTS idx_raw_records_ingestion_hash ON raw_records(ingestion_hash);
CREATE INDEX IF NOT EXISTS idx_raw_records_row_status ON raw_records(row_status);

CREATE INDEX IF NOT EXISTS idx_column_mappings_upload_id ON column_mappings(upload_id);
CREATE INDEX IF NOT EXISTS idx_column_mappings_target_field_name ON column_mappings(target_field_name);
CREATE INDEX IF NOT EXISTS idx_column_mappings_mapping_type ON column_mappings(mapping_type);

CREATE INDEX IF NOT EXISTS idx_normalization_runs_upload_id ON normalization_runs(upload_id);
CREATE INDEX IF NOT EXISTS idx_normalization_runs_mapping_id ON normalization_runs(mapping_id);
CREATE INDEX IF NOT EXISTS idx_normalization_runs_created_at ON normalization_runs(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_normalized_records_raw_id ON normalized_records(raw_id);
CREATE INDEX IF NOT EXISTS idx_normalized_records_upload_id ON normalized_records(upload_id);
CREATE INDEX IF NOT EXISTS idx_normalized_records_normalization_run_id ON normalized_records(normalization_run_id);
CREATE INDEX IF NOT EXISTS idx_normalized_records_clean_tc ON normalized_records(clean_tc);
CREATE INDEX IF NOT EXISTS idx_normalized_records_clean_phone ON normalized_records(clean_phone);
CREATE INDEX IF NOT EXISTS idx_normalized_records_clean_email ON normalized_records(clean_email);
CREATE INDEX IF NOT EXISTS idx_normalized_records_name_phonetic ON normalized_records(name_phonetic);
CREATE INDEX IF NOT EXISTS idx_normalized_records_clean_city ON normalized_records(clean_city);
CREATE INDEX IF NOT EXISTS idx_normalized_records_blocking_key ON normalized_records(blocking_key);
CREATE INDEX IF NOT EXISTS idx_normalized_records_is_valid ON normalized_records(is_valid);

CREATE INDEX IF NOT EXISTS idx_detection_runs_upload_id ON detection_runs(upload_id);
CREATE INDEX IF NOT EXISTS idx_detection_runs_normalization_run_id ON detection_runs(normalization_run_id);
CREATE INDEX IF NOT EXISTS idx_detection_runs_created_at ON detection_runs(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_match_candidates_detection_run_id ON match_candidates(detection_run_id);
CREATE INDEX IF NOT EXISTS idx_match_candidates_left_id ON match_candidates(left_id);
CREATE INDEX IF NOT EXISTS idx_match_candidates_right_id ON match_candidates(right_id);
CREATE INDEX IF NOT EXISTS idx_match_candidates_decision ON match_candidates(decision);
CREATE INDEX IF NOT EXISTS idx_match_candidates_match_type ON match_candidates(match_type);
CREATE INDEX IF NOT EXISTS idx_match_candidates_score ON match_candidates(score DESC);

CREATE INDEX IF NOT EXISTS idx_review_actions_match_id ON review_actions(match_id);
CREATE INDEX IF NOT EXISTS idx_review_actions_decided_by ON review_actions(decided_by);
CREATE INDEX IF NOT EXISTS idx_review_actions_decided_at ON review_actions(decided_at DESC);

CREATE INDEX IF NOT EXISTS idx_entity_memberships_entity_id ON entity_memberships(entity_id);
CREATE INDEX IF NOT EXISTS idx_entity_memberships_normalized_record_id ON entity_memberships(normalized_record_id);

CREATE INDEX IF NOT EXISTS idx_audit_logs_action_type ON audit_logs(action_type);
CREATE INDEX IF NOT EXISTS idx_audit_logs_entity_lookup ON audit_logs(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_type ON jobs(type);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_updated_at ON jobs(updated_at DESC);
