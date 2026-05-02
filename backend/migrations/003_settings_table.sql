CREATE TABLE IF NOT EXISTS app_settings (
    id SERIAL PRIMARY KEY,
    key VARCHAR(128) UNIQUE NOT NULL,
    value JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMP DEFAULT NOW(),
    updated_by VARCHAR(255)
);

CREATE INDEX IF NOT EXISTS idx_app_settings_key ON app_settings (key);
CREATE INDEX IF NOT EXISTS idx_app_settings_updated_at ON app_settings (updated_at);

INSERT INTO app_settings (key, value) VALUES
  ('weights',    '{"adSoyad":30,"tcKimlikNo":35,"telefon":15,"email":10,"muhatapNo":10}'),
  ('thresholds', '{"otoOnayla":97,"bayrakla":75,"yoksay":50}'),
  ('algorithms', '["levenshtein","jaro"]'),
  ('autoDetectPeriod', '"Her hafta"'),
  ('maxFileSize', '50'),
  ('approvalLimitDays', '7'),
  ('emailNotification', '"Sadece kritik"')
ON CONFLICT (key) DO NOTHING;
