ALTER TABLE entities ADD COLUMN IF NOT EXISTS canonical_muhatap_no TEXT;

CREATE INDEX IF NOT EXISTS idx_entities_canonical_muhatap_no ON entities (canonical_muhatap_no);
