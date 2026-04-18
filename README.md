# ml-duplicate-detection

Bu proje Streamlit tabanli duplicate tespit uygulamasidir.

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

2. API servisini calistir:

```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

3. Endpointler:

- `GET /health`
- `POST /api/v1/normalize`
- `POST /api/v1/detect`
- `POST /api/v1/detect-file` (Excel/CSV upload)
- `POST /api/v1/detect-from-url` (harici API'den veri cekip tespit)

Frontend varsayilan olarak `http://localhost:8000` adresine istek atar.

React Veri Yukleme sayfasinda su akıslar canli backend ile calisir:

- Excel/CSV dosya yukleme -> `detect-file`
- API URL'den veri cekme -> `detect-from-url`
- Manuel kayit girisi -> `detect`
- "Sonuclari PostgreSQL'e kaydet" secenegi ile DB insert

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
