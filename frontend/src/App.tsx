import { Link, Navigate, Route, Routes } from "react-router-dom";
import VeriYukleme from "./pages/VeriYukleme/index";
import VeriNormalizasyon from "./pages/VeriNormalizasyon/index";
import TemizVeriSeti from "./pages/TemizVeriSeti/index";
import MukerrerTespit from "./pages/MukerrerTespit/index";
import MukerrerKayitlar from "./pages/MukerrerKayitlar/index";
import YoneticiOnayi from "./pages/YoneticiOnayi/index";
import Ayarlar from "./pages/Ayarlar/index";
import Raporlar from "./pages/Raporlar/index";

function Home() {
  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-2xl rounded-2xl border border-slate-200 bg-white/90 shadow-sm p-8">
        <h1 className="text-2xl font-semibold text-slate-900">Dedupli-AI</h1>
        <p className="text-slate-600 mt-2">
          Kayıt yönetim sistemi. Veri akışı: Yükleme → Normalizasyon → Temiz Veri → Mükerrer Tespit → Onay → Raporlar.
        </p>
        <div className="mt-6 flex gap-3 flex-wrap">
          <Link
            to="/veri-yukleme"
            className="inline-flex items-center gap-2 rounded-lg bg-red-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-red-700"
          >
            <i className="ri-upload-cloud-2-line" /> Veri Yükleme
          </Link>
          <Link
            to="/temiz-veri-seti"
            className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            <i className="ri-table-line" /> Temiz Veri Seti
          </Link>
        </div>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/veri-yukleme" element={<VeriYukleme />} />
      <Route path="/veri-normalizasyon" element={<VeriNormalizasyon />} />
      <Route path="/temiz-veri-seti" element={<TemizVeriSeti />} />
      <Route path="/mukerrer-tespit" element={<MukerrerTespit />} />
      <Route path="/mukerrer-kayitlar" element={<MukerrerKayitlar />} />
      <Route path="/yonetici-onayi" element={<YoneticiOnayi />} />
      <Route path="/ayarlar" element={<Ayarlar />} />
      <Route path="/raporlar" element={<Raporlar />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
