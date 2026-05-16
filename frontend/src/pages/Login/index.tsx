import { useState } from "react";
import { useNavigate } from "react-router-dom";

import BrandMark from "../../components/feature/BrandMark";
import { login } from "../../services/api";

export default function Login() {
  const navigate = useNavigate();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login({ username, password });
      navigate("/", { replace: true });
    } catch {
      setError("Giriş başarısız. Kullanıcı adı veya şifre hatalı.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen bg-surface">
      <div className="hidden flex-1 flex-col justify-between bg-gradient-to-br from-slate-950 via-slate-900 to-indigo-950 p-10 lg:flex">
        <BrandMark variant="sidebar" />
        <div className="max-w-md">
          <p className="text-3xl font-semibold leading-snug tracking-tight text-white">
            Benzersiz kayıt.
            <br />
            <span className="text-primary-400">Her kişi için tek profil.</span>
          </p>
          <p className="mt-4 text-sm leading-relaxed text-slate-400">
            UniRecord (Unique Record), mükerrer kayıtları tespit eder, incelemenizi yönetir ve
            her muhatap için birleştirilmiş tek bir golden kayıt oluşturur.
          </p>
        </div>
        <p className="text-xs text-slate-600">© UniRecord</p>
      </div>

      <div className="flex flex-1 items-center justify-center p-6">
        <form onSubmit={onSubmit} className="ui-card w-full max-w-md p-8 shadow-card-lg">
          <div className="mb-6 lg:hidden">
            <BrandMark variant="login" />
          </div>

          <h1 className="text-xl font-semibold text-slate-900">Giriş Yap</h1>
          <p className="mt-1 text-sm text-slate-500">Yönetim paneline erişmek için oturum açın.</p>

          <motion>
          <div className="mt-6 space-y-4">
            <div>
              <label className="mb-1.5 block text-xs font-medium text-slate-700">
                Kullanıcı Adı
              </label>
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                className="ui-focus-ring w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium text-slate-700">Şifre</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                className="ui-focus-ring w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm"
              />
            </div>
          </div>

          {error && (
            <div className="mt-4 rounded-xl border border-danger-200 bg-danger-50 px-3 py-2.5 text-xs text-danger-700">
              {error}
            </div>
          )}

          <button type="submit" disabled={loading} className="ui-btn-primary ui-focus-ring mt-6 w-full">
            {loading ? "Giriş yapılıyor..." : "Giriş Yap"}
          </button>
        </form>
      </div>
    </div>
  );
}
