-- Migration 004: Add clean_muhatap_no to normalized_records
-- Replaces address-based scoring with muhatap_no (customer/donor code) in the algorithm.

ALTER TABLE normalized_records
    ADD COLUMN IF NOT EXISTS clean_muhatap_no TEXT DEFAULT '';

UPDATE normalized_records
SET clean_muhatap_no = ''
WHERE clean_muhatap_no IS NULL;

CREATE INDEX IF NOT EXISTS idx_normalized_records_clean_muhatap_no
    ON normalized_records (clean_muhatap_no)
    WHERE clean_muhatap_no IS NOT NULL AND clean_muhatap_no <> '';
