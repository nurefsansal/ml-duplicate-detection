import { useState, useEffect } from "react";
import DashboardLayout from "../../components/feature/DashboardLayout";
import Header from "../../components/feature/Header";
import { mockDuplicateGroups } from "../../mocks/records";
import { auditLog } from "../../mocks/approval";

const reportTypes = [
  { id: "mukerrer-ozet", icon: "ri-file-chart-line", label: "Mükerrer Özet Raporu", desc: "Toplam mükerrer, karar dağılımı ve trend analizi", badge: "Popüler" },
  { id: "tespit-detay", icon: "ri-search-eye-line", label: "Tespit Detay Raporu", desc: "Tüm tespit sonuçları, skor kırılımı ve algoritma bazlı analiz", badge: null },
  { id: "onay-log", icon: "ri-checkbox-circle-line", label: "Yönetici Onay Logu", desc: "Tüm onay/red işlemleri, yönetici bazlı dağılım", badge: null },
  { id: "veri-kalite", icon: "ri-shield-check-line", label: "Veri Kalite Raporu", desc: "Normalizasyon başarısı, alan bazlı doğruluk oranları", badge: "Yeni" },
  { id: "yukleme-gecmis", icon: "ri-upload-cloud-2-line", label: "Yükleme Geçmişi", desc: "Kaynak bazlı yükleme istatistikleri ve hata oranları", badge: null },
  { id: "ozet-dashboard", icon: "ri-dashboard-3-line", label: "Dashboard Özet", desc: "KPI kartları ve grafiklerin PDF özeti", badge: null },
];

const exportFormats = [
  { id: "excel", icon: "ri-file-excel-2-line", label: "Excel (.xlsx)", color: "text-green-600 bg-green-50 border-green-200" },
  { id: "csv", icon: "ri-file-text-line", label: "CSV (.csv)", color: "text-blue-600 bg-blue-50 border-blue-200" },
  { id: "pdf", icon: "ri-file-pdf-line", label: "PDF (.pdf)", color: "text-red-600 bg-red-50 border-red-200" },
];

type ReportData = {
  totalDuplicates: number;
  onaylandi: number;
  bekleyen: number;
  reddedildi: number;
  avgScore: number;
  totalRecords: number;
};

export default function Raporlar() {
  const [selectedReport, setSelectedReport] = useState("mukerrer-ozet");
  const [selectedFormat, setSelectedFormat] = useState("excel");
  const [dateFrom, setDateFrom] = useState("2024-12-01");
  const [dateTo, setDateTo] = useState("2024-12-14");
  const [exporting, setExporting] = useState(false);
  const [exported, setExported] = useState(false);
  const [reportData, setReportData] = useState<ReportData | null>(null);

  // Calculate report data based on selected report type
  useEffect(() => {
    const onaylandi = mockDuplicateGroups.filter(g => g.decision === "onaylandi").length;
    const bekleyen = mockDuplicateGroups.filter(g => g.decision === "bekleyen").length;
    const reddedildi = mockDuplicateGroups.filter(g => g.decision === "reddedildi").length;
    const totalDuplicates = mockDuplicateGroups.length;
    const avgScore = mockDuplicateGroups.reduce((sum, g) => sum + g.score, 0) / totalDuplicates;

    setReportData({
      totalDuplicates,
      onaylandi,
      bekleyen,
      reddedildi,
      avgScore,
      totalRecords: 12450,
    });
  }, [selectedReport]);

  const handleExport = async () => {
    setExporting(true);
    setExported(false);

    // Simulate report generation
    await new Promise(resolve => setTimeout(resolve, 1800));

    // In a real app, this would call the backend to generate the report
    // For now, we'll just simulate the export
    const reportName = reportTypes.find(r => r.id === selectedReport)?.label || "Rapor";
    const fileName = `${reportName.replace(/\s+/g, "_")}_${dateFrom}_${dateTo}.${selectedFormat}`;
    
    // Create a simple download simulation
    console.log(`Exporting report: ${fileName}`);
    
    setExporting(false);
    setExported(true);
    setTimeout(() => setExported(false), 3000);
  };

  const handleQuickDate = (range: string) => {
    const today = new Date();
    let from = new Date();
    
    switch (range) {
      case "Bu Hafta":
        from = new Date(today.setDate(today.getDate() - 7));
        break;
      case "Bu Ay":
        from = new Date(today.setMonth(today.getMonth() - 1));
        break;
      case "Son 3 Ay":
        from = new Date(today.setMonth(today.getMonth() - 3));
        break;
      case "Bu Yıl":
        from = new Date(today.setFullYear(today.getFullYear() - 1));
        break;
    }
    
    setDateFrom(from.toISOString().split("T")[0]);
    setDateTo(new Date().toISOString().split("T")[0]);
  };

  // Calculate estimated file size based on format
  const estimatedSize = selectedFormat === "pdf" ? "2.4" : "1.1";

  return (
    <DashboardLayout>
      <Header
        title="Raporlar"
        subtitle="Sistem verilerini analiz edin ve dışa aktarın"
      />

      <div className="flex-1 overflow-y-auto p-6 space-y-5">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
          {/* Left: Report Type + Config */}
          <div className="lg:col-span-2 space-y-5">
            {/* Report Types */}
            <div className="bg-white rounded-xl p-5 border border-gray-100">
              <h3 className="text-sm font-semibold text-gray-900 mb-4">Rapor Türü Seçin</h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {reportTypes.map((r) => {
                  const active = selectedReport === r.id;
                  return (
                    <button
                      key={r.id}
                      onClick={() => setSelectedReport(r.id)}
                      className={`relative text-left p-4 rounded-xl border-2 cursor-pointer transition-all ${active ? "border-red-500 bg-red-50/40" : "border-gray-100 hover:border-gray-200"}`}
                    >
                      {r.badge && (
                        <span className="absolute top-3 right-3 text-[10px] font-bold px-2 py-0.5 rounded-full bg-red-100 text-red-600">
                          {r.badge}
                        </span>
                      )}
                      <div className={`w-8 h-8 rounded-lg flex items-center justify-center mb-2 ${active ? "bg-red-100" : "bg-gray-100"}`}>
                        <i className={`${r.icon} text-base ${active ? "text-red-600" : "text-gray-400"}`}></i>
                      </div>
                      <p className={`text-sm font-semibold ${active ? "text-red-700" : "text-gray-700"}`}>{r.label}</p>
                      <p className="text-xs text-gray-400 mt-0.5">{r.desc}</p>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Date Range */}
            <div className="bg-white rounded-xl p-5 border border-gray-100">
              <h3 className="text-sm font-semibold text-gray-900 mb-4">Tarih Aralığı</h3>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1.5">Başlangıç</label>
                  <input 
                    type="date" 
                    value={dateFrom} 
                    onChange={(e) => setDateFrom(e.target.value)} 
                    className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-red-400 cursor-pointer" 
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1.5">Bitiş</label>
                  <input 
                    type="date" 
                    value={dateTo} 
                    onChange={(e) => setDateTo(e.target.value)} 
                    className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-red-400 cursor-pointer" 
                  />
                </div>
              </div>
              <div className="flex gap-2 mt-3">
                {["Bu Hafta", "Bu Ay", "Son 3 Ay", "Bu Yıl"].map((p) => (
                  <button 
                    key={p} 
                    onClick={() => handleQuickDate(p)}
                    className="text-xs px-3 py-1.5 border border-gray-200 rounded-lg hover:bg-gray-50 cursor-pointer text-gray-600 whitespace-nowrap transition-colors"
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>

            {/* Report Preview Stats */}
            {reportData && (
              <div className="bg-white rounded-xl p-5 border border-gray-100">
                <h3 className="text-sm font-semibold text-gray-900 mb-4">Rapor Önizleme</h3>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                  <div className="p-3 bg-gray-50 rounded-lg text-center">
                    <p className="text-lg font-bold text-gray-900">{reportData.totalDuplicates}</p>
                    <p className="text-[10px] text-gray-400">Toplam Mükerrer</p>
                  </div>
                  <div className="p-3 bg-green-50 rounded-lg text-center">
                    <p className="text-lg font-bold text-green-600">{reportData.onaylandi}</p>
                    <p className="text-[10px] text-gray-400">Onaylanan</p>
                  </div>
                  <div className="p-3 bg-yellow-50 rounded-lg text-center">
                    <p className="text-lg font-bold text-yellow-600">{reportData.bekleyen}</p>
                    <p className="text-[10px] text-gray-400">Bekleyen</p>
                  </div>
                  <div className="p-3 bg-red-50 rounded-lg text-center">
                    <p className="text-lg font-bold text-red-600">{reportData.reddedildi}</p>
                    <p className="text-[10px] text-gray-400">Reddedilen</p>
                  </div>
                </div>
                <div className="mt-4 pt-4 border-t border-gray-100 flex justify-between text-xs">
                  <span className="text-gray-500">Ortalama Skor: <span className="font-semibold text-gray-700">%{reportData.avgScore.toFixed(1)}</span></span>
                  <span className="text-gray-500">Toplam Kayıt: <span className="font-semibold text-gray-700">{reportData.totalRecords.toLocaleString()}</span></span>
                </div>
              </div>
            )}
          </div>

          {/* Right: Export Panel */}
          <div className="space-y-4">
            <div className="bg-white rounded-xl p-5 border border-gray-100">
              <h3 className="text-sm font-semibold text-gray-900 mb-4">Dışa Aktarma Formatı</h3>
              <div className="space-y-2">
                {exportFormats.map((f) => {
                  const active = selectedFormat === f.id;
                  return (
                    <button
                      key={f.id}
                      onClick={() => setSelectedFormat(f.id)}
                      className={`w-full flex items-center gap-3 p-3 rounded-lg border-2 cursor-pointer transition-all ${active ? `${f.color} border-opacity-100` : "border-gray-100 hover:border-gray-200"}`}
                    >
                      <i className={`${f.icon} text-lg ${active ? f.color.split(" ")[0] : "text-gray-400"}`}></i>
                      <span className={`text-sm font-medium ${active ? f.color.split(" ")[0] : "text-gray-600"}`}>{f.label}</span>
                      {active && <i className="ri-checkbox-circle-fill ml-auto text-base"></i>}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Preview Info */}
            <div className="bg-gray-50 rounded-xl p-4 border border-gray-100">
              <p className="text-xs font-semibold text-gray-700 mb-3">Rapor Özeti</p>
              <div className="space-y-2 text-xs text-gray-500">
                <div className="flex justify-between">
                  <span>Tür</span>
                  <span className="font-medium text-gray-700 text-right max-w-[130px] truncate">
                    {reportTypes.find((r) => r.id === selectedReport)?.label}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span>Format</span>
                  <span className="font-medium text-gray-700 uppercase">{selectedFormat}</span>
                </div>
                <div className="flex justify-between">
                  <span>Tarih</span>
                  <span className="font-medium text-gray-700">{dateFrom} → {dateTo}</span>
                </div>
                <div className="flex justify-between">
                  <span>Tahmini Boyut</span>
                  <span className="font-medium text-gray-700">~{estimatedSize} MB</span>
                </div>
              </div>
            </div>

            {exported && (
              <div className="p-3 bg-green-50 border border-green-100 rounded-xl flex items-center gap-2">
                <i className="ri-checkbox-circle-fill text-green-600 text-base"></i>
                <p className="text-xs text-green-700 font-medium">Rapor oluşturuldu ve indirildi!</p>
              </div>
            )}

            <button
              onClick={handleExport}
              disabled={exporting}
              className="w-full flex items-center justify-center gap-2 bg-red-600 text-white text-sm font-semibold py-3 rounded-xl hover:bg-red-700 disabled:opacity-60 cursor-pointer transition-colors whitespace-nowrap"
            >
              <i className={exporting ? "ri-loader-4-line animate-spin" : "ri-download-2-line"}></i>
              {exporting ? "Oluşturuluyor..." : "Raporu Dışa Aktar"}
            </button>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}