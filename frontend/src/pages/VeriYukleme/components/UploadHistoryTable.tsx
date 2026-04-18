import { uploadHistory, type UploadHistoryItem } from "../../../mocks/records";

const statusConfig = {
  tamamlandi: {
    label: "Tamamlandı",
    class: "bg-green-50 text-green-700",
    icon: "ri-checkbox-circle-fill",
  },
  hata: {
    label: "Hata",
    class: "bg-red-50 text-red-600",
    icon: "ri-error-warning-fill",
  },
  isleniyor: {
    label: "İşleniyor",
    class: "bg-yellow-50 text-yellow-700",
    icon: "ri-loader-4-line",
  },
};

const sourceIcon: Record<string, string> = {
  Excel: "ri-file-excel-2-line",
  CSV: "ri-file-text-line",
  API: "ri-code-s-slash-line",
  Manuel: "ri-keyboard-line",
};

export default function UploadHistoryTable() {
  return (
    <div className="bg-white rounded-xl border border-gray-100">
      <div className="flex items-center justify-between px-5 py-4 border-b border-gray-50">
        <div>
          <h3 className="text-sm font-semibold text-gray-900">
            Yükleme Geçmişi
          </h3>
          <p className="text-xs text-gray-500 mt-0.5">
            Son 30 günlük yükleme işlemleri
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-700 bg-gray-50 hover:bg-gray-100 px-3 py-1.5 rounded-lg cursor-pointer transition-colors whitespace-nowrap">
            <i className="ri-filter-3-line text-sm"></i>
            Filtrele
          </button>
          <button className="flex items-center gap-1.5 text-xs text-red-600 font-medium hover:bg-red-50 px-3 py-1.5 rounded-lg cursor-pointer transition-colors whitespace-nowrap">
            <i className="ri-download-line text-sm"></i>
            Dışa Aktar
          </button>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-gray-50/70">
              <th className="text-left text-gray-400 font-medium px-5 py-3">
                Dosya Adı
              </th>
              <th className="text-left text-gray-400 font-medium px-4 py-3">
                Kaynak
              </th>
              <th className="text-right text-gray-400 font-medium px-4 py-3">
                Kayıt
              </th>
              <th className="text-right text-gray-400 font-medium px-4 py-3">
                Mükerrer
              </th>
              <th className="text-left text-gray-400 font-medium px-4 py-3">
                Tarih
              </th>
              <th className="text-left text-gray-400 font-medium px-4 py-3">
                Durum
              </th>
              <th className="text-center text-gray-400 font-medium px-4 py-3">
                İşlem
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {uploadHistory.map((item: UploadHistoryItem) => {
              const status =
                statusConfig[item.durum as keyof typeof statusConfig];
              return (
                <tr
                  key={item.id}
                  className="hover:bg-gray-50/50 transition-colors"
                >
                  <td className="px-5 py-3.5">
                    <div className="flex items-center gap-2">
                      <i
                        className={`${sourceIcon[item.kaynak] || "ri-file-line"} text-gray-400 text-base`}
                      ></i>
                      <span className="text-gray-800 font-medium">
                        {item.dosyaAdi}
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-3.5 text-gray-500">{item.kaynak}</td>
                  <td className="px-4 py-3.5 text-right font-medium text-gray-700">
                    {item.kayitSayisi.toLocaleString("tr-TR")}
                  </td>
                  <td className="px-4 py-3.5 text-right">
                    <span className="font-medium text-red-600">
                      {item.mukerrer}
                    </span>
                  </td>
                  <td className="px-4 py-3.5 text-gray-500">{item.tarih}</td>
                  <td className="px-4 py-3.5">
                    <span
                      className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-medium ${status.class}`}
                    >
                      <i className={`${status.icon} text-xs`}></i>
                      {status.label}
                    </span>
                  </td>
                  <td className="px-4 py-3.5 text-center">
                    <button className="text-gray-400 hover:text-gray-600 cursor-pointer w-6 h-6 flex items-center justify-center mx-auto">
                      <i className="ri-more-2-line text-base"></i>
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
