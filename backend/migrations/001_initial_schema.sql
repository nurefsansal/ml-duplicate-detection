-- ============================================================================
-- AŞAMA 1: TEMEL TABLOLAR - İYİLEŞTİRİLMİŞ SCHEMA
-- ============================================================================

-- ⚡ 1. UPLOADS - Dosya yükleme kaydı
CREATE TABLE IF NOT EXISTS uploads (
    id SERIAL PRIMARY KEY,
    file_name TEXT NOT NULL,
    file_size_bytes BIGINT,
    total_records INT NOT NULL DEFAULT 0,
    status VARCHAR(32) DEFAULT 'pending', -- pending, processing, completed, failed
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) -- Operator adı (login)
);

-- ⚡ 2. RAW_DONORS - Ham veri (olduğu gibi)
CREATE TABLE IF NOT EXISTS raw_donors (
    id SERIAL PRIMARY KEY,
    upload_id INT NOT NULL REFERENCES uploads(id) ON DELETE CASCADE,
    row_number INT, -- Excel'de hangi satırdan geliyor
    full_name TEXT,
    email TEXT,
    phone TEXT,
    city TEXT,
    extra_fields JSONB, -- Başka sütunlar varsa burada tutalım
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ⚡ 3. NORMALIZED_DONORS - Temizlenmiş veri
CREATE TABLE IF NOT EXISTS normalized_donors (
    id SERIAL PRIMARY KEY,
    upload_id INT NOT NULL REFERENCES uploads(id) ON DELETE CASCADE,
    raw_id INT REFERENCES raw_donors(id) ON DELETE CASCADE,
    
    -- Temizlenmiş alanlar
    full_name TEXT,
    first_name TEXT,
    last_name TEXT,
    email TEXT,
    phone TEXT,
    city TEXT,
    
    -- Normalizasyon anahtarları (blocking için)
    clean_tc TEXT,
    clean_phone TEXT,
    clean_email TEXT,
    clean_city TEXT,
    email_normalized_key TEXT,
    name_phonetic_key TEXT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ⚡ 4. MATCHES - Eşleşme adayları (EN ÖNEMLİ)
CREATE TABLE IF NOT EXISTS matches (
    id SERIAL PRIMARY KEY,
    upload_id INT NOT NULL REFERENCES uploads(id) ON DELETE CASCADE,
    donor1_id INT NOT NULL REFERENCES normalized_donors(id) ON DELETE CASCADE,
    donor2_id INT NOT NULL REFERENCES normalized_donors(id) ON DELETE CASCADE,
    
    -- Puanlama
    similarity FLOAT, -- Basit benzerlik
    ml_score FLOAT, -- ML modeli puanı (0-1)
    confidence FLOAT, -- Güven seviyesi
    
    -- Karar
    status VARCHAR(32) DEFAULT 'pending', -- pending, confirmed, rejected, merged
    decision_reason TEXT, -- Neden "same_person"/"different_person"?
    
    -- Detaylı özellikler (JSON olarak store)
    features JSONB,
    
    -- Admin onayı
    approved_by VARCHAR(255), -- Hangi operatör onayladı
    approved_at TIMESTAMP,
    rejected_reason TEXT,
    rejected_at TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Duplicate pair'i önle (aynı çiftin iki kez girmesini)
    UNIQUE(donor1_id, donor2_id)
);

-- ⚡ 5. ENTITIES - Gerçek/Birleştirilmiş Kişiler
CREATE TABLE IF NOT EXISTS entities (
    id SERIAL PRIMARY KEY,
    
    -- Canonical (En iyi) veriler
    canonical_name TEXT NOT NULL,
    canonical_email TEXT,
    canonical_phone TEXT,
    canonical_city TEXT,
    
    -- Bu entity'ye referans olan kayıt sayısı
    donor_count INT DEFAULT 1,
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    merged_count INT DEFAULT 0, -- Kaç kişi birleştirildi
    confidence_score FLOAT DEFAULT 1.0, -- 0-1: Birleştirme güven puanı
    
    -- Eğer manuel birleştirme ise
    merged_by VARCHAR(255),
    merged_at TIMESTAMP
);

-- ⚡ 6. ENTITY_MAP - Mapping (EN ÖNEMLİ)
-- Bu tablo her donor'ın hangi entity'ye ait olduğunu söyler
CREATE TABLE IF NOT EXISTS entity_map (
    id SERIAL PRIMARY KEY,
    entity_id INT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    donor_id INT NOT NULL REFERENCES normalized_donors(id) ON DELETE CASCADE,
    
    -- Hangi match'den geliyor
    match_id INT REFERENCES matches(id) ON DELETE SET NULL,
    
    -- Eğer manuel mapping ise
    created_by VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Mapping'i geri almak isteyebiliriz
    is_active BOOLEAN DEFAULT TRUE,
    
    UNIQUE(entity_id, donor_id)
);

-- ============================================================================
-- ⚡ PERFORMANS İÇİN INDEXLER (ÇOK ÖNEMLİ!)
-- ============================================================================

-- Uploads
CREATE INDEX idx_uploads_status ON uploads(status);
CREATE INDEX idx_uploads_created_at ON uploads(created_at DESC);

-- Raw Donors
CREATE INDEX idx_raw_donors_upload_id ON raw_donors(upload_id);
CREATE INDEX idx_raw_donors_full_name ON raw_donors(full_name);

-- Normalized Donors
CREATE INDEX idx_norm_donors_upload_id ON normalized_donors(upload_id);
CREATE INDEX idx_norm_donors_raw_id ON normalized_donors(raw_id);
CREATE INDEX idx_norm_donors_email ON normalized_donors(clean_email);
CREATE INDEX idx_norm_donors_phone ON normalized_donors(clean_phone);
CREATE INDEX idx_norm_donors_tc ON normalized_donors(clean_tc);
CREATE INDEX idx_norm_donors_city ON normalized_donors(clean_city);
CREATE INDEX idx_norm_donors_phonetic ON normalized_donors(name_phonetic_key);
CREATE INDEX idx_norm_donors_email_key ON normalized_donors(email_normalized_key);

-- Matches
CREATE INDEX idx_matches_upload_id ON matches(upload_id);
CREATE INDEX idx_matches_donor1_id ON matches(donor1_id);
CREATE INDEX idx_matches_donor2_id ON matches(donor2_id);
CREATE INDEX idx_matches_status ON matches(status);
CREATE INDEX idx_matches_ml_score ON matches(ml_score DESC);
CREATE INDEX idx_matches_created_at ON matches(created_at DESC);

-- Entities
CREATE INDEX idx_entities_canonical_name ON entities(canonical_name);
CREATE INDEX idx_entities_canonical_email ON entities(canonical_email);
CREATE INDEX idx_entities_canonical_phone ON entities(canonical_phone);
CREATE INDEX idx_entities_created_at ON entities(created_at DESC);

-- Entity Map
CREATE INDEX idx_entity_map_entity_id ON entity_map(entity_id);
CREATE INDEX idx_entity_map_donor_id ON entity_map(donor_id);
CREATE INDEX idx_entity_map_is_active ON entity_map(is_active);

-- ============================================================================
-- 📊 VIEWS - Raporlama için
-- ============================================================================

-- Henüz onaylanmamış eşleşmeler
CREATE VIEW v_pending_matches AS
SELECT 
    m.id,
    m.donor1_id,
    m.donor2_id,
    nd1.full_name as donor1_name,
    nd2.full_name as donor2_name,
    nd1.email as donor1_email,
    nd2.email as donor2_email,
    m.ml_score,
    m.confidence,
    m.decision_reason,
    m.created_at
FROM matches m
JOIN normalized_donors nd1 ON m.donor1_id = nd1.id
JOIN normalized_donors nd2 ON m.donor2_id = nd2.id
WHERE m.status = 'pending'
ORDER BY m.ml_score DESC;

-- Her entity'ye kaç donor mapped
CREATE VIEW v_entity_summary AS
SELECT 
    e.id,
    e.canonical_name,
    e.canonical_email,
    e.canonical_phone,
    COUNT(em.donor_id) as donor_count,
    COUNT(CASE WHEN em.is_active = TRUE THEN 1 END) as active_donors,
    e.created_at
FROM entities e
LEFT JOIN entity_map em ON e.id = em.entity_id
GROUP BY e.id, e.canonical_name, e.canonical_email, e.canonical_phone, e.created_at;

-- Workflow: Hangi match'ler onaylandı/reddedildi
CREATE VIEW v_match_statistics AS
SELECT 
    upload_id,
    COUNT(*) as total_matches,
    COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending,
    COUNT(CASE WHEN status = 'confirmed' THEN 1 END) as confirmed,
    COUNT(CASE WHEN status = 'rejected' THEN 1 END) as rejected,
    COUNT(CASE WHEN status = 'merged' THEN 1 END) as merged,
    AVG(ml_score) as avg_score
FROM matches
GROUP BY upload_id;
