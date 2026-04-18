export type UploadHistoryItem = {
  id: string;
  dosyaAdi: string;
  kaynak: "Excel" | "CSV" | "API" | "Manuel";
  kayitSayisi: number;
  mukerrer: number;
  tarih: string;
  durum: "tamamlandi" | "hata" | "isleniyor";
};

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
