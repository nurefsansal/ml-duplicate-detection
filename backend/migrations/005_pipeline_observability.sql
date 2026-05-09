-- Pipeline observability tables (runs + events).
-- Purpose: store small, structured, queryable process logs without bloating the jobs table.

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id SERIAL PRIMARY KEY,

    pipeline_type VARCHAR(64) NOT NULL, -- upload | normalization | detection | export | etc.
    status VARCHAR(32) NOT NULL DEFAULT 'running', -- running | completed | failed | cancelled

    -- Correlation fields (nullable by design, not all pipelines have all ids)
    request_id VARCHAR(64),
    upload_id INT REFERENCES uploads(id) ON DELETE SET NULL,
    job_id INT REFERENCES jobs(id) ON DELETE SET NULL,
    normalization_run_id INT REFERENCES normalization_runs(id) ON DELETE SET NULL,
    detection_run_id INT REFERENCES detection_runs(id) ON DELETE SET NULL,

    -- Counters (rollups)
    total_rows INT DEFAULT 0,
    processed_rows INT DEFAULT 0,
    warning_count INT DEFAULT 0,
    error_count INT DEFAULT 0,
    error_message TEXT,

    -- Timing
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    duration_ms INT,

    -- Extensible metadata
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS pipeline_events (
    id SERIAL PRIMARY KEY,
    run_id INT NOT NULL REFERENCES pipeline_runs(id) ON DELETE CASCADE,

    stage VARCHAR(64) NOT NULL, -- ingest | mapping | standardize | preview | candidate_generation | etc.
    event_type VARCHAR(32) NOT NULL, -- started | progress | completed | failed | warning | info

    message TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,

    total_rows INT DEFAULT 0,
    processed_rows INT DEFAULT 0,
    warning_count INT DEFAULT 0,
    error_count INT DEFAULT 0,
    duration_ms INT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_type_created_at
    ON pipeline_runs (pipeline_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_status
    ON pipeline_runs (status);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_request_id
    ON pipeline_runs (request_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_upload_id
    ON pipeline_runs (upload_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_job_id
    ON pipeline_runs (job_id);

CREATE INDEX IF NOT EXISTS idx_pipeline_events_run_id_created_at
    ON pipeline_events (run_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_pipeline_events_stage
    ON pipeline_events (stage);
CREATE INDEX IF NOT EXISTS idx_pipeline_events_event_type
    ON pipeline_events (event_type);

