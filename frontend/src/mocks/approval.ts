export type AuditLogItem = {
  id: string;
  grup: string;
  yonetici: string;
  islem: "Onaylandı" | "Reddedildi";
  tarih: string;
  not: string;
};

export const yoneticiler = [
  "Ahmet Yılmaz",
  "Ayşe Demir",
  "Mehmet Kaya",
  "Fatma Şahin",
];

export const auditLog: AuditLogItem[] = [
  {
    id: "LOG-001",
    grup: "MG-002",
    yonetici: "Ahmet Yılmaz",
    islem: "Onaylandı",
    tarih: "18.04.2026 14:30",
    not: "TC ve telefon bilgileri birebir eşleşiyor. Aynı kişi.",
  },
  {
    id: "LOG-002",
    grup: "MG-004",
    yonetici: "Ayşe Demir",
    islem: "Reddedildi",
    tarih: "18.04.2026 11:15",
    not: "Farklı kişiler, sadece isim benzerliği var.",
  },
  {
    id: "LOG-003",
    grup: "MG-001",
    yonetici: "Mehmet Kaya",
    islem: "Onaylandı",
    tarih: "17.04.2026 16:45",
    not: "Tüm alanlar eşleşiyor.",
  },
  {
    id: "LOG-004",
    grup: "MG-003",
    yonetici: "Fatma Şahin",
    islem: "Onaylandı",
    tarih: "17.04.2026 10:20",
    not: "TC kimlik no aynı, aynı kişi.",
  },
  {
    id: "LOG-005",
    grup: "MG-005",
    yonetici: "Ahmet Yılmaz",
    islem: "Reddedildi",
    tarih: "16.04.2026 09:30",
    not: "Farklı kişiler, aynı TC numarası kullanılmış.",
  },
];