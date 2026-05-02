import { Navigate, Route, Routes } from "react-router-dom";
import Dashboard from "./pages/Dashboard/index";
import VeriYukleme from "./pages/VeriYukleme/index";
import VeriNormalizasyon from "./pages/VeriNormalizasyon/index";
import TemizVeriSeti from "./pages/TemizVeriSeti/index";
import MukerrerTespit from "./pages/MukerrerTespit/index";
import MukerrerKayitlar from "./pages/MukerrerKayitlar/index";
import YoneticiOnayi from "./pages/YoneticiOnayi/index";
import Ayarlar from "./pages/Ayarlar/index";
import Raporlar from "./pages/Raporlar/index";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Dashboard />} />
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
