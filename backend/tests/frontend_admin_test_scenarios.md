# Frontend + Admin API Test Senaryolari

Bu dokuman, detect -> pending -> approve/reject akisinin UI ve API seviyesinde dogrulanmasi icin olusturulmustur.

## On Kosullar

- PostgreSQL container calisiyor.
- Backend API ayakta.
- Frontend dev server ayakta.
- Tarayici ile frontend acilabiliyor.

## Ortam Hazirlama

1. Postgres:
   - `cd devops`
   - `docker compose up -d postgres`
2. Backend:
   - `cd ..`
   - `$env:PYTHONPATH='.'`
   - `.venv/Scripts/python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8001`
3. Frontend:
   - `cd frontend`
   - `npm run dev`

Not: Frontend ortaminda gerekiyorsa `VITE_API_BASE_URL=http://127.0.0.1:8001` kullanin.

## Senaryo 1 - Temel Uctan Uca (Pozitif)

Amac: Detect sonucu pending listesine dusmeli, approve ile entity olusmali.

Adimlar:
1. Frontendde Mukerrer Tespit sayfasina gidin.
2. Icinde bilerek benzer 2 kayit barindiran bir csv/xlsx secin.
3. Tespiti Baslat butonuna basin.
4. Islem bitince mesajda duplicate sayisini ve varsa Upload ID bilgisini kontrol edin.
5. Yonetici Onayi sayfasina gecin.
6. Bekleyen listede kayitlarin geldigini kontrol edin.
7. Bir kayit icin Detay & Karar Ver > Onayla islemini yapin.
8. Bekleyen sayisinin azaldigini kontrol edin.
9. Onaylanan tabinda audit kaydinin olustugunu kontrol edin.

Beklenen:
- Yonetici Onayi sayfasi son upload ID ile filtreli veri getirir.
- Onay islemi 200 ile tamamlanir ve kayit pending listeden duser.

## Senaryo 2 - Reddetme Akisi

Amac: Admin reddetme endpoint ve UI senkronizasyonu.

Adimlar:
1. Yonetici Onayi > Bekleyen listeden bir kaydi acin.
2. Karar notu girin.
3. Reddet butonuna basin.
4. Bekleyen listeden kaydin kalktigini kontrol edin.
5. Reddedilen tabinda audit satirini kontrol edin.

Beklenen:
- Reject istegi basarili olur.
- Reddedilen satiri gorunur.

## Senaryo 3 - Upload ID Filter Kontrolu

Amac: Yonetici ekraninin son detect uploadini dogru okudugunu kanitlamak.

Adimlar:
1. Mukerrer Tespit ile yeni bir detect calistirin.
2. Islem sonrasi tarayici localStorage icinde `lastDetectUploadId` degerini kontrol edin.
3. Yonetici Onayi sayfasina gecin.
4. Ust bilgilendirme kartinda upload id gorunuyor mu kontrol edin.
5. Yenile butonu ile sadece ilgili uploadin pending kayitlarini getirdigini dogrulayin.

Beklenen:
- Upload ID uyumlu gorunur.
- Bekleyen liste beklenen alt kumeyi gosterir.

## Senaryo 4 - Backend Kapali Iken Dayaniklilik

Amac: UI hata durumunu dogru gostermeli.

Adimlar:
1. Backend servisini kapatin.
2. Frontendde Yonetici Onayi sayfasini yenileyin.
3. Mukerrer Tespit sayfasina gidin.

Beklenen:
- Backend Erisilemiyor uyarisi gorunur.
- Bekleyen cekme / karar verme islemlerinde anlamli hata mesaji gorunur.

## Senaryo 5 - Veri Bos Durumu

Amac: Pending yoksa UI bozulmamali.

Adimlar:
1. Tum pending kayitlari onaylayin/reddedin.
2. Yonetici Onayi sayfasinda Yenile butonuna basin.

Beklenen:
- Bekleyen kayit yok mesaji gorunur.
- Sayfa hata vermez.

## API Smoke Komutu

Asagidaki komut backend zincirini hizli dogrular:

- `$env:PYTHONPATH='.'; .venv/Scripts/python.exe backend/tests/smoke_detect_admin.py`

Beklenen ornek cikti:
- detect 200
- pending 200 count > 0
- approve 200
- entities 200 count > 0
