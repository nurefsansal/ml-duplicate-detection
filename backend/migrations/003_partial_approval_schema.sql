ALTER TABLE entities
    ADD COLUMN IF NOT EXISTS canonical_data JSONB DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS golden_record_id INT REFERENCES normalized_records(id) ON DELETE SET NULL;

ALTER TABLE entity_memberships
    ADD COLUMN IF NOT EXISTS status VARCHAR(32) NOT NULL DEFAULT 'pending';

CREATE INDEX IF NOT EXISTS idx_entities_golden_record_id ON entities(golden_record_id);
CREATE INDEX IF NOT EXISTS idx_entity_memberships_status ON entity_memberships(status);
