# 📋 Veritabanı Tasarımı - Detaylı Analiz & İyileştirmeler

## ✅ Sizin Tasarımınız - Ne İyi Yaptınız?

| Özellik | Durumu | Yorum |
|---------|--------|-------|
| 6 tablo yapısı | ✅ Mükemmel | uploads → raw → normalized → matches → entities → entity_map |
| Entity mapping tablosu | ✅ Çok önemli | N-to-1 ilişki doğru |
| Status tracking | ✅ İyi | pending → confirmed/rejected |
| Indexler | ✅ Yeterli | Email, phone, TC indexleri var |

---

## 🔧 Önerilen İyileştirmeler

### 1️⃣ **Timestamps - EKLE** (Proje yönetimi için çok önemli)
```sql
-- ÖNCE (Eksik)
CREATE TABLE uploads (
    id SERIAL PRIMARY KEY,
    file_name TEXT
);

-- SONRA (İyileştirilmiş)
CREATE TABLE uploads (
    id SERIAL PRIMARY KEY,
    file_name TEXT NOT NULL,
    status VARCHAR(32) DEFAULT 'pending', -- pending, processing, completed, failed
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) -- Kim yüklediyse kayıt et
);
```
**Neden?** → Kaç dakikada işlem bitiyorum? / Kim sorumlu? / Hata nerede?

---

### 2️⃣ **Matches Tablosu - Çok Eksik Alanlar** (Karar motoru için şart)
```sql
-- ÖNCE (Basit)
CREATE TABLE matches (
    id SERIAL PRIMARY KEY,
    donor1_id INT,
    donor2_id INT,
    similarity FLOAT,
    ml_score FLOAT,
    status TEXT DEFAULT 'pending'
);

-- SONRA (Tam)
CREATE TABLE matches (
    id SERIAL PRIMARY KEY,
    donor1_id INT NOT NULL,
    donor2_id INT NOT NULL,
    
    -- Puanlama (3 farklı skor!)
    similarity FLOAT,           -- Basit benzerlik
    ml_score FLOAT,            -- ML puanı
    confidence FLOAT,          -- Güven seviyesi (0-1)
    
    -- Karar izleri
    status VARCHAR(32),        -- pending/confirmed/rejected/merged
    decision_reason TEXT,      -- "same_person/different_person" neden?
    features JSONB,            -- 15+ feature (name_sim, phone_match, vb)
    
    -- Admin onayı (Audit trail!)
    approved_by VARCHAR(255),  -- Hangi operatör?
    approved_at TIMESTAMP,     -- Ne zaman?
    rejected_reason TEXT,      -- Neden reddedildi?
    
    UNIQUE(donor1_id, donor2_id)  -- Aynı çift iki kez girilmesin
);
```
**Neden?** → Admin "neden onayladı?" diye sorduğunda kanıt gösterebilirsin

---

### 3️⃣ **Normalized_Donors - Blocking Anahtarları EKLE**
```sql
-- Blocking'i hızlandırmak için:
CREATE TABLE normalized_donors (
    id SERIAL PRIMARY KEY,
    
    -- Temel alanlar
    full_name TEXT,
    email TEXT,
    phone TEXT,
    
    -- ⭐ BLOCKING ANAHTARLARı (çok önemli!)
    clean_tc TEXT,
    clean_phone TEXT,
    clean_email TEXT,
    clean_city TEXT,
    email_normalized_key TEXT,    -- "ahmet.yilmaz+spam" → "ahmetyilmaz@..."
    name_phonetic_key TEXT,       -- "Ahmet" → "AHM" (Soundex/Metaphone)
    
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```
**Neden?** → Milyonlarca kaydı sorgulamak yerine, sadece same key'deki kayıtları karşılaştır. 100x hızlı!

---

### 4️⃣ **Entities - Metadata Alanları EKLE**
```sql
-- ÖNCE
CREATE TABLE entities (
    id SERIAL PRIMARY KEY,
    canonical_name TEXT,
    email TEXT,
    phone TEXT
);

-- SONRA
CREATE TABLE entities (
    id SERIAL PRIMARY KEY,
    
    -- Canonical veriler
    canonical_name TEXT NOT NULL,
    canonical_email TEXT,
    canonical_phone TEXT,
    
    -- ⭐ METADATA (Raporlama için)
    donor_count INT DEFAULT 1,        -- Kaç kayıt birleşti?
    merged_count INT DEFAULT 0,       -- Kaç merge işlemi?
    confidence_score FLOAT DEFAULT 1, -- Birleştirme güven: 0-1
    
    -- ⭐ AUDIT TRAIL
    merged_by VARCHAR(255),    -- Hangi admin yaptı?
    merged_at TIMESTAMP,       -- Ne zaman?
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```
**Neden?** → "Bu entity güvenilir mi?" diye görebilirsin. confidence_score = 0.85 demek "85% güvenle doğru"

---

### 5️⃣ **Entity_Map - Match Tracing EKLE**
```sql
-- ÖNCE
CREATE TABLE entity_map (
    id SERIAL PRIMARY KEY,
    entity_id INT,
    donor_id INT
);

-- SONRA
CREATE TABLE entity_map (
    id SERIAL PRIMARY KEY,
    entity_id INT NOT NULL,
    donor_id INT NOT NULL,
    
    -- ⭐ Hangi match'den geliyor?
    match_id INT REFERENCES matches(id),
    
    -- ⭐ Admin onayı
    created_by VARCHAR(255),    -- Otomatik mi manuel mi?
    created_at TIMESTAMP,
    
    -- ⭐ Soft delete (Geri almak isteyebiliriz)
    is_active BOOLEAN DEFAULT TRUE,
    
    UNIQUE(entity_id, donor_id)
);
```
**Neden?** → "Operatör X bu mapping'i yaptı" ve "Geri al!" diyebilirsin

---

## 📊 Yeni Öneriler

### **Status Enum Kullan (String yerine)**
```sql
-- String yerine ENUM daha güvenli:
CREATE TYPE upload_status AS ENUM ('pending', 'processing', 'completed', 'failed');
CREATE TYPE match_status AS ENUM ('pending', 'confirmed', 'rejected', 'merged', 'manual_review');

CREATE TABLE uploads (
    id SERIAL PRIMARY KEY,
    status upload_status DEFAULT 'pending'
);
```

### **Soft Delete Desteği**
```sql
-- Veri silmeyi sakla, sadece işaretle:
CREATE TABLE entities (
    id SERIAL PRIMARY KEY,
    ...
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMP
);

-- Sorgu: is_deleted = FALSE olan veriler al
```

---

## 🔄 Workflow - Tablo Akışı

```
1️⃣ UPLOAD (Excel yükle)
   ↓ uploads tablosuna kayıt
   ↓ status = 'processing'

2️⃣ RAW DATA (Ham veri tampon)
   ↓ raw_donors tablosuna kayıt
   ↓ row_number = kaçıncı satır?

3️⃣ NORMALIZE (Temizle)
   ↓ normalized_donors tablosuna kayıt
   ↓ Blocking anahtarlarını hesapla

4️⃣ MATCHING (Eşleşmeleri tespit et)
   ↓ matches tablosuna kayıt
   ↓ status = 'pending'
   ↓ ml_score, features, decision_reason SET

5️⃣ ADMIN REVIEW (Operatör onaylasın)
   ↓ matches.status = 'confirmed' / 'rejected'
   ↓ approved_by, approved_at SET

6️⃣ MERGE (Onaylanmış eşleşmeleri birleştir)
   ↓ entities tablosuna yeni kişi kayıt
   ↓ entity_map'e donor1, donor2 mapla
   ↓ matches.status = 'merged' SET

7️⃣ ENTITY FINALIZATION (Son hal)
   ↓ entities.donor_count = 2
   ↓ entities.merged_by = 'operator@...'
```

---

## 💾 İndeксler - Neden Gerekli?

```sql
-- QUERY (1 milyonlarda veri)
SELECT * FROM matches WHERE donor1_id = 12345;

-- INDEX YOK: 1.5 saniye (tüm tabloyu scan)
-- INDEX VAR: 0.002 saniye (direkt satıra zıpla)
```

**750x hızlı!** İndexler maliyetlidir (disk kullanır) ama Query'ler için kritik.

---

## 🎯 Özet: Size Tavsiyem

| Unsur | Önerisi | Gerekli mi? |
|-------|---------|-----------|
| Timestamps (created_at, updated_at) | ✅ EKLE | **ŞART** |
| Status ENUM | ✅ EKLE | İyilik |
| Features JSONB (matches) | ✅ EKLE | **ŞART** |
| Blocking anahtarları | ✅ EKLE | **ŞART** (Performans için) |
| Audit trail (approved_by) | ✅ EKLE | **ŞART** |
| match_id in entity_map | ✅ EKLE | İyilik |
| Soft delete (is_deleted) | ⭐ Opsiyonel | İyilik |
| Views (v_pending_matches) | ⭐ Opsiyonel | Raporlama için |

**Sonuç:** Veritabanı tasarımınız **temel olarak doğru**, ama **audit trail + blocking anahtarları şart!**

---

## 🔗 Sonraki Adım

Tasarım onaylandı mı? Devam edebiliriz:

1. ✅ SQL migration script oluşturmak (migration/001_initial_schema.sql)
2. ✅ SQLAlchemy ORM modellerini yazmak
3. ✅ Database service fonksiyonlarını yazmak
4. ✅ Detect pipeline'ına entegrasyon yapmak

**Hazır mısız?**
