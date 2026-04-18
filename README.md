# ml-duplicate-detection

Bu proje Streamlit tabanli duplicate tespit uygulamasidir.

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
