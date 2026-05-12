# ml-duplicate-detection

Bu proje Streamlit tabanli duplicate tespit uygulamasidir. **Üretim akışı** React + FastAPI üzerindedir.

### Ana pipeline (React + API)

1. **Veri yükleme:** `POST /api/v1/uploads/file` → `uploads`, `raw_records`. Kurum DB: `POST /api/v1/uploads/from-institution-db` ingest’i **arka planda** çalıştırır; yanıtta `job_id` ile ilerleme takibi.
2. **Kolon eşlemesi + standardizasyon:** `POST /api/v1/column-mappings`, `POST /api/v1/normalization-runs` → `normalized_records`. Normalizasyon için en az bir kolonun kanonik hedefe (ad, TC, telefon, …) eşlenmesi gerekir; yalnızca “Diğer” yeterli değildir.
3. **Mükerrer tespit:** `POST /api/v1/detect` — `uploadId` (isteğe bağlı `normalizationRunId`); `minRulesToMatch` **1–4** *alan kuralı* eşiğidir (yüzde benzerlik değildir).
4. **Dışa aktarma:** `GET /api/v1/normalized-records/export`, `GET /api/v1/reports/export/*.csv`

Legacy tek dosya akışları (`/api/v1/normalize-file`, `/api/v1/detect-file`) hâlâ vardır; ana arayüz yukarıdaki sırayı kullanır. Otomatik testler: `pip install -r requirements-dev.txt` ve `python -m pytest backend/tests -q`.

## React Frontend (Yeni)

Mevcut Streamlit uygulamasi korunur. React tabanli yeni veri yukleme arayuzu `frontend` klasorune eklendi.

1. Frontend bagimliliklarini yukle:

```bash
cd frontend
npm install
```

2. React uygulamasini calistir:

```bash
cd frontend
npm run dev
```

3. Sayfa adresleri:

- Home: `http://localhost:5173`
- Veri Yukleme: `http://localhost:5173/veri-yukleme`

Not: Streamlit arayuzunde "React Veri Yukleme Panelini Ac" butonu ile yeni sayfaya gecis yapabilirsin.

## Backend API (FastAPI)

React tarafinin cagiracagi backend API baslangici eklendi.

1. Bagimliliklari yukle:

```bash
pip install -r requirements.txt
```

2. PostgreSQL semasini guncelle (ilk kurulum ve yeni SQL migration dosyalari icin). Uygulanan dosyalar `schema_migrations` tablosunda tutulur; tekrar calistirmak guvenlidir:

```bash
python backend/migrations/run_migration.py
```

Baglanti dizesi icin `DATABASE_URL` ortam degiskenini kullanabilirsiniz (ornek: `postgresql+psycopg2://kullanici:sifre@localhost:5434/ml_duplicate_db`). Sadece bekleyen migration listesini gormek icin: `python backend/migrations/run_migration.py --dry-run`.

3. API servisini calistir:

```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

4. Backend testleri (geliştirme):

```bash
pip install -r requirements-dev.txt
python -m pytest backend/tests -q
```

5. Endpointler:

- `GET /health`
- `POST /api/v1/normalize`
- `POST /api/v1/detect`
- `POST /api/v1/detect-file` (Excel/CSV upload)
- `POST /api/v1/detect-from-url` (harici API'den veri cekip tespit)

Frontend varsayilan olarak `http://localhost:8000` adresine istek atar.

Ana React akisi: **Veri Yükleme** (`uploads/file`) → **Veri Normalizasyon** → **Mükerrer Tespit** (`detect` + DB) → inceleme ve rapor/export sayfalari. Legacy olarak dosyadan doğrudan tespit: `detect-file`.

## PostgreSQL + Docker Kurulumu

Ana proje klasoru altinda `devops` klasoru olusturuldu.

1. PostgreSQL konteynerini baslat:

```bash
cd devops
docker compose up -d postgres
```

2. Tum stack'i baslatmak istersen (PostgreSQL + uygulama):

```bash
cd devops
docker compose up -d --build
```

`app` konteyneri her baslangicta (postgres saglikli olduktan sonra) veritabani migration'larini otomatik calistirir; ayri komut yazmaniz gerekmez. Kapatmak icin `devops/.env` icinde `SKIP_DB_MIGRATIONS=1` kullanin.

3. Varsayilan ayarlar `devops/.env` dosyasinda:

- POSTGRES_DB=ml_duplicate_db
- POSTGRES_USER=ml_duplicate_user
- POSTGRES_PASSWORD=1234
- POSTGRES_PORT=5434

## Python Uygulama Icin Veritabani Ayari

Uygulama `DATABASE_URL` ortam degiskenini okur.
Varsayilan deger:

```text
postgresql+psycopg2://ml_duplicate_user:1234@localhost:5434/ml_duplicate_db
```

Lokal calistirmada bu degeri override etmek icin ornek:

```powershell
$env:DATABASE_URL="postgresql+psycopg2://ml_duplicate_user:1234@localhost:5434/ml_duplicate_db"
streamlit run app.py
```

## Eklenen DB Ozellikleri

- Uygulama acilisinda PostgreSQL baglanti testi yapilir.
- Duplicate listesi bulundugunda, UI uzerinden tek tikla PostgreSQL'e kaydedilebilir.
- Sonuclar `duplicate_results` tablosuna yazilir (tablo yoksa otomatik olusturulur).

## Kayit Tablosu

Temel alanlar:

- session_id
- created_at
- rules_matched
- left_index / right_index
- left*\* ve right*\* alanlari (ad, sehir, telefon, tc, email)
- payload (tum satirin JSON kopyasi)
