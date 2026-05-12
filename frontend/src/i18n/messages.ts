/**
 * UI metinleri — Türkçe (varsayılan) ve İngilizce.
 * Yeni anahtar eklerken `enMessages` için `satisfies typeof trMessages` ile aynı şekli koruyun.
 */
export type AppLocale = "tr" | "en";

export const LOCALE_STORAGE_KEY = "ml-dedupe-ui-locale";

export const trMessages = {
  exportPanel: {
    langAria: "Arayüz dili",
    toggleTr: "Türkçe",
    toggleEn: "English",
    emptyTitle: "Önce bir yükleme seçin",
    emptyBody:
      "Dışa aktarmak için üst menüden veya Veri Yükleme ekranından bu sayfaya ait bir yükleme (upload) seçilmiş olmalıdır.",
    downloadFailed:
      "İndirme başarısız. Oturumunuzun açık olduğundan ve sunucuya erişilebildiğinden emin olun.",
    eyebrowDefault: "Veri çıktısı",
    eyebrowPostReview: "Onay adımı sonrası",
    titleDefault: "Yükleme #{{uploadId}} — tekil müşteri dosyası ve raporlar",
    titlePostReview:
      "Yükleme #{{uploadId}} — onaylanan mükerrerlerin birleşik görünümü",
    blurbDefault:
      "Aşağıdaki dosyalar bu yükleme için normalize edilmiş ve onaylı birleşim kurallarına göre tekilleştirilmiş veriyi içerir. Kişisel veri politikalarınıza uygun paylaşın.",
    blurbPostReview:
      "Burada otomatik veya manuel onayladığınız eşleşmeler tek satırda toplanır. Önce ana dosyayı (CSV/XLSX/JSON), gerekirse denetim CSV’lerini indirin.",
    previewLink: "Temiz veri tablosu",
    previewHint: "Satır satır önizleme",
    step1Badge: "Adım 1",
    step1Title: "Ana veri dosyası (tekil satırlar)",
    step1Bullets: [
      "Her satır bir kişi / muhatap temsil eder.",
      "Onaylı mükerrer kayıtlar tek satırda birleştirilir (golden kuralları).",
      "Ham kayıtlar veritabanında durur; bu dosya operasyonel tekil görünümdür.",
    ],
    formatCsv: "CSV",
    formatCsvHint: "Excel, Python, R",
    formatXlsx: "Excel",
    formatXlsxHint: "Doğrudan açılır",
    formatJson: "JSON",
    formatJsonHint: "API / entegrasyon",
    step1TechNote:
      "İndirme bağlantıları oturum çerezinizi kullanır; yeni sekmede açınca giriş yapmış olmalısınız.",
    step2Badge: "Adım 2",
    step2TitleDefault: "Raporlar (CSV ve sözel özet TXT; oturum gerekir)",
    step2TitlePostReview: "Onay denetimi, mükerrer CSV’leri ve sözel özet",
    step2Intro:
      "Kısa açıklamayı okuyun; indir düğmesi dosyayı kaydeder. Sözel rapor, arayüz dilinize göre Türkçe veya İngilizce üretilir.",
    step2TechNote:
      "Uçlar: /api/v1/reports/export/… — yükleme numarasına göre filtrelenir. Sözel rapor: narrative_report.txt",
    actions: {
      clean: {
        label: "Temiz set raporu",
        desc: "Export ile aynı kolonlar: kaynak tipi, birleşen üye ID’leri, muhatap öncesi değerler.",
      },
      lineage: {
        label: "Birleşim özeti (önce → sonra)",
        desc: "Hangi normalize ID’lerin birleştiği, muhatap kodları öncesi ve golden sonrası tek değer.",
      },
      narrative: {
        label: "Sözel özet rapor (TXT)",
        desc: "Paragraf düzeninde okunabilir özet: ham/normalize sayıları, tekil görünüm, karar sayıları ve ilk birleşimlerden kısa örnekler. Arayüz dilinize göre TR veya EN üretilir.",
      },
      groups: {
        label: "Onaylı mükerrer grupları",
        desc: "Bağlı bileşen grupları: grup kimliği, kayıt sayısı, skor.",
      },
      matches: {
        label: "Onaylı eşleşme çiftleri",
        desc: "Çift çift tüm onaylı adaylar (sol/sağ kayıt ID, skor, karar).",
      },
      golden: {
        label: "Golden özet",
        desc: "Grup başına seçilen golden alanlar (ad, TC, iletişim, muhatap).",
      },
    },
  },
  dashboard: {
    postApprovalLead: "Onay sonrası dosyalar:",
    postApprovalLink: "Mükerrer Kayıtlar",
    postApprovalTrail:
      "sayfasının altındaki «Veri çıktısı» bölümünden indirebilirsiniz.",
  },
  sidebar: {
    language: "Dil / Language",
  },
} as const;

export const enMessages = {
  exportPanel: {
    langAria: "Interface language",
    toggleTr: "Türkçe",
    toggleEn: "English",
    emptyTitle: "Select an upload first",
    emptyBody:
      "Choose an upload from the menu or Data Upload screen before exporting. This panel needs an active upload id.",
    downloadFailed:
      "Download failed. Check that you are signed in and the server is reachable.",
    eyebrowDefault: "Data export",
    eyebrowPostReview: "After duplicate review",
    titleDefault: "Upload #{{uploadId}} — single-customer file and reports",
    titlePostReview:
      "Upload #{{uploadId}} — merged view of approved duplicates",
    blurbDefault:
      "Files below contain normalized data deduplicated using your approval rules. Share according to your privacy policy.",
    blurbPostReview:
      "Automatically or manually approved pairs collapse to one row. Download the main file (CSV/XLSX/JSON), then audit CSVs if needed.",
    previewLink: "Clean data table",
    previewHint: "Row-level preview",
    step1Badge: "Step 1",
    step1Title: "Main dataset (one row per person)",
    step1Bullets: [
      "Each row represents one person / counterparty.",
      "Approved duplicates are merged into one row (golden rules).",
      "Raw rows stay in the database; this file is the operational single view.",
    ],
    formatCsv: "CSV",
    formatCsvHint: "Excel, Python, R",
    formatXlsx: "Excel",
    formatXlsxHint: "Opens directly",
    formatJson: "JSON",
    formatJsonHint: "API / integration",
    step1TechNote:
      "Links use your session cookie; you must be logged in when the new tab opens.",
    step2Badge: "Step 2",
    step2TitleDefault: "Reports (CSV and narrative TXT; session required)",
    step2TitlePostReview: "Approval audit, duplicate CSVs, and narrative summary",
    step2Intro:
      "Read each description, then download. The narrative report follows your UI language (TR/EN).",
    step2TechNote:
      "Endpoints: /api/v1/reports/export/… — filtered by upload id. Narrative: narrative_report.txt",
    actions: {
      clean: {
        label: "Clean dataset report",
        desc: "Same columns as export: source type, merged member ids, muhatap values before merge.",
      },
      lineage: {
        label: "Merge lineage (before → after)",
        desc: "Which normalized ids merged, muhatap codes before vs single golden after.",
      },
      narrative: {
        label: "Narrative summary (TXT)",
        desc: "Plain-language report: raw/normalized counts, clean-view breakdown, decision counts, and short examples from the first merge groups. Language follows your UI (TR/EN).",
      },
      groups: {
        label: "Approved duplicate groups",
        desc: "Connected components: group id, record count, score.",
      },
      matches: {
        label: "Approved match pairs",
        desc: "Every approved pair (left/right id, score, decision).",
      },
      golden: {
        label: "Golden summary",
        desc: "Per group chosen golden fields (name, ID, contact, muhatap).",
      },
    },
  },
  dashboard: {
    postApprovalLead: "After approval, download files from",
    postApprovalLink: "Duplicate records",
    postApprovalTrail:
      "— open the «Data export» section at the bottom of that page.",
  },
  sidebar: {
    language: "Language / Dil",
  },
} as unknown as typeof trMessages;

export const bundles: Record<AppLocale, typeof trMessages> = {
  tr: trMessages,
  en: enMessages,
};

export function interpolate(template: string, vars: Record<string, string | number>): string {
  return Object.entries(vars).reduce((acc, [key, value]) => {
    const token = `{{${key}}}`;
    return acc.split(token).join(String(value));
  }, template);
}
