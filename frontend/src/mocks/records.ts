export type UploadHistoryItem = {
  id: string;
  dosyaAdi: string;
  kaynak: "Excel" | "CSV" | "API" | "Manuel";
  kayitSayisi: number;
  mukerrer: number;
  tarih: string;
  durum: "tamamlandi" | "hata" | "isleniyor";
};

export type NormalizationRule = {
  id: number;
  name: string;
  description: string;
  category: "metin" | "karakter" | "format" | "dogrulama" | "adres";
  field: string;
  active: boolean;
};

export type NormalizationPreview = {
  field: string;
  ham: string;
  normalize: string;
};

export const normalizationRules: NormalizationRule[] = [
  {
    id: 1,
    name: "Büyük/Küçük Harf Normalizasyonu",
    description: "Tüm metin alanlarını küçük harfe çevirir",
    category: "metin",
    field: "Tüm metin alanları",
    active: true,
  },
  {
    id: 2,
    name: "Türkçe Karakter Dönüşümü",
    description: "Ç, ğ, ı, ö, ş, ü karakterlerini ASCII karşılıklarına çevirir",
    category: "karakter",
    field: "Ad Soyad, Şehir",
    active: true,
  },
  {
    id: 3,
    name: "Telefon Formatı Standartlaştırma",
    description: "Telefon numaralarını (05XX XXX XX XX) formatına dönüştürür",
    category: "format",
    field: "Telefon",
    active: true,
  },
  {
    id: 4,
    name: "TC Kimlik No Doğrulama",
    description: "11 haneli TC numarasının algoritmasını kontrol eder",
    category: "dogrulama",
    field: "TC Kimlik No",
    active: true,
  },
  {
    id: 5,
    name: "E-posta Normalizasyonu",
    description: "E-posta adreslerini küçük harfe çevirir ve standartlaştırır",
    category: "format",
    field: "E-posta",
    active: true,
  },
  {
    id: 6,
    name: "Şehir Adı Standartlaştırma",
    description: "Şehir isimlerini standart formata dönüştürür (İstanbul, ANKARA -> İstanbul)",
    category: "adres",
    field: "Şehir",
    active: true,
  },
  {
    id: 7,
    name: "Boşluk Karakteri Temizleme",
    description: "Metin başındaki ve sonundaki boşlukları kaldırır",
    category: "karakter",
    field: "Tüm metin alanları",
    active: true,
  },
  {
    id: 8,
    name: "Çoklu Boşluk Birleştirme",
    description: "Ardışık boşlukları tek boşluğa dönüştürür",
    category: "karakter",
    field: "Tüm metin alanları",
    active: true,
  },
];

export const normalizationPreview: NormalizationPreview[] = [
  { field: "Ad Soyad", ham: "AHMET YILMAZ ", normalize: "ahmet yilmaz" },
  { field: "Telefon", ham: "+90 532 123 45 67", normalize: "05321234567" },
  { field: "TC Kimlik", ham: "12345678901", normalize: "12345678901" },
  { field: "E-posta", ham: "Ahmet@Example.COM", normalize: "ahmet@example.com" },
  { field: "Şehir", ham: "ANKARA", normalize: "Ankara" },
];

export const uploadHistory: UploadHistoryItem[] = [
  {
    id: "UP-001",
    dosyaAdi: "musteri_listesi_nisan.xlsx",
    kaynak: "Excel",
    kayitSayisi: 1260,
    mukerrer: 118,
    tarih: "18.04.2026 10:30",
    durum: "tamamlandi",
  },
  {
    id: "UP-002",
    dosyaAdi: "api_musteriler_17_04.csv",
    kaynak: "CSV",
    kayitSayisi: 820,
    mukerrer: 64,
    tarih: "17.04.2026 15:42",
    durum: "tamamlandi",
  },
  {
    id: "UP-003",
    dosyaAdi: "crm_sync",
    kaynak: "API",
    kayitSayisi: 410,
    mukerrer: 0,
    tarih: "17.04.2026 16:05",
    durum: "isleniyor",
  },
];

export type DuplicateGroup = {
  id: string;
  records: [
    { adSoyad: string; tcKimlikNo: string; telefon: string; email: string; sehir: string; muhatapNo: string; dogumTarihi?: string; adres?: string },
    { adSoyad: string; tcKimlikNo: string; telefon: string; email: string; sehir: string; muhatapNo: string; dogumTarihi?: string; adres?: string }
  ];
  score: number;
  decision: "bekleyen" | "onaylandi" | "reddedildi";
  matchDetails?: Record<string, number>;
};

export const mockDuplicateGroups: DuplicateGroup[] = [
  {
    id: "MG-001",
    records: [
      { adSoyad: "Ahmet Yılmaz", tcKimlikNo: "12345678901", telefon: "05321234567", email: "ahmet@example.com", sehir: "İstanbul", muhatapNo: "M001", dogumTarihi: "15.03.1985", adres: "İstanbul, Türkiye" },
      { adSoyad: "Ahmet Yılmaz", tcKimlikNo: "12345678901", telefon: "05329876543", email: "ahmet.yilmaz@test.com", sehir: "İstanbul", muhatapNo: "M002", dogumTarihi: "15.03.1985", adres: "İstanbul, Türkiye" },
    ],
    score: 98.5,
    decision: "bekleyen",
    matchDetails: { adSoyad: 100, tcKimlikNo: 100, telefon: 95, email: 98, sehir: 100 },
  },
  {
    id: "MG-002",
    records: [
      { adSoyad: "Ayşe Demir", tcKimlikNo: "98765432100", telefon: "05451234567", email: "ayse.demir@ornek.com", sehir: "Ankara", muhatapNo: "M003", dogumTarihi: "22.07.1990", adres: "Ankara, Türkiye" },
      { adSoyad: "Ayşe Demir", tcKimlikNo: "98765432100", telefon: "05451234567", email: "ayse.demir@ornek.com", sehir: "Ankara", muhatapNo: "M004", dogumTarihi: "22.07.1990", adres: "Ankara, Türkiye" },
    ],
    score: 100,
    decision: "onaylandi",
    matchDetails: { adSoyad: 100, tcKimlikNo: 100, telefon: 100, email: 100, sehir: 100 },
  },
  {
    id: "MG-003",
    records: [
      { adSoyad: "Mehmet Kaya", tcKimlikNo: "11122233344", telefon: "05331112233", email: "mehmet@kaya.com", sehir: "İzmir", muhatapNo: "M005", dogumTarihi: "10.11.1978", adres: "İzmir, Türkiye" },
      { adSoyad: "Mehmet Kaya", tcKimlikNo: "11122233344", telefon: "05334445566", email: "mehmetkaya@test.com", sehir: "İzmir", muhatapNo: "M006", dogumTarihi: "10.11.1978", adres: "İzmir, Türkiye" },
    ],
    score: 87.3,
    decision: "bekleyen",
    matchDetails: { adSoyad: 100, tcKimlikNo: 100, telefon: 75, email: 82, sehir: 100 },
  },
  {
    id: "MG-004",
    records: [
      { adSoyad: "Fatma Şahin", tcKimlikNo: "55566677788", telefon: "05325551234", email: "fatma.sahin@mail.com", sehir: "Bursa", muhatapNo: "M007", dogumTarihi: "05.02.1995", adres: "Bursa, Türkiye" },
      { adSoyad: "Fatma Şahin", tcKimlikNo: "55566677788", telefon: "05325559876", email: "fatma.sahin@posta.com", sehir: "Bursa", muhatapNo: "M008", dogumTarihi: "05.02.1995", adres: "Bursa, Türkiye" },
    ],
    score: 92.1,
    decision: "reddedildi",
    matchDetails: { adSoyad: 100, tcKimlikNo: 100, telefon: 88, email: 90, sehir: 100 },
  },
  {
    id: "MG-005",
    records: [
      { adSoyad: "Ali Öztürk", tcKimlikNo: "44455566677", telefon: "05324441111", email: "ali.ozturk@domain.com", sehir: "Adana", muhatapNo: "M009", dogumTarihi: "30.06.1982", adres: "Adana, Türkiye" },
      { adSoyad: "Ali Öztürk", tcKimlikNo: "44455566677", telefon: "05329992222", email: "ali.ozturk@web.com", sehir: "Adana", muhatapNo: "M010", dogumTarihi: "30.06.1982", adres: "Adana, Türkiye" },
    ],
    score: 78.9,
    decision: "bekleyen",
    matchDetails: { adSoyad: 100, tcKimlikNo: 100, telefon: 55, email: 68, sehir: 100 },
  },
];
