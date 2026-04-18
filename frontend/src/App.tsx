import { Link, Navigate, Route, Routes } from "react-router-dom";
import VeriYukleme from "./pages/VeriYukleme/index";

function PlaceholderPage({ title }: { title: string }) {
  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-xl rounded-2xl border border-gray-200 bg-white p-8 text-center">
        <h2 className="text-2xl font-bold text-gray-900">{title}</h2>
        <p className="mt-2 text-sm text-gray-600">
          Bu sayfa hazirlandi. Sonraki adimda backend baglantilarini
          ekleyecegiz.
        </p>
        <Link
          to="/veri-yukleme"
          className="inline-flex mt-5 items-center gap-2 rounded-lg bg-red-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-red-700"
        >
          <i className="ri-upload-cloud-2-line" /> Veri Yukleme Sayfasina Don
        </Link>
      </div>
    </div>
  );
}

function Home() {
  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-2xl rounded-2xl border border-slate-200 bg-white/90 shadow-sm p-8">
        <h1 className="text-2xl font-semibold text-slate-900">
          Dedupli-AI React Panel
        </h1>
        <p className="text-slate-600 mt-2">
          Mevcut Streamlit uygulaman korunur. Bu panel veri yukleme akisinin
          React arayuzudur.
        </p>
        <div className="mt-6 flex gap-3">
          <Link
            to="/veri-yukleme"
            className="inline-flex items-center gap-2 rounded-lg bg-red-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-red-700"
          >
            <i className="ri-upload-cloud-2-line" /> Veri Yukleme Sayfasina Git
          </Link>
          <a
            href="http://localhost:8501"
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            <i className="ri-external-link-line" /> Streamlit Ac
          </a>
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
      <Route
        path="/veri-normalizasyon"
        element={<PlaceholderPage title="Veri Normalizasyon" />}
      />
      <Route
        path="/mukerrer-tespit"
        element={<PlaceholderPage title="Mukerrer Tespit" />}
      />
      <Route
        path="/mukerrer-kayitlar"
        element={<PlaceholderPage title="Mukerrer Kayitlar" />}
      />
      <Route
        path="/yonetici-onayi"
        element={<PlaceholderPage title="Yonetici Onayi" />}
      />
      <Route path="/ayarlar" element={<PlaceholderPage title="Ayarlar" />} />
      <Route path="/raporlar" element={<PlaceholderPage title="Raporlar" />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
