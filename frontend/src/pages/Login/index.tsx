import { useState } from "react";
import { useNavigate } from "react-router-dom";

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
      setError("Giris basarisiz. Kullanici adi veya sifre hatali.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 p-6">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-md rounded-2xl border border-gray-100 bg-white p-6 shadow-sm"
      >
        <h1 className="text-xl font-semibold text-gray-900">Giris Yap</h1>
        <p className="mt-1 text-sm text-gray-500">
          Yonetim endpointlerine erisim icin oturum acin.
        </p>

        <div className="mt-4 space-y-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-700">
              Kullanici Adi
            </label>
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:border-red-400 focus:outline-none"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-700">
              Sifre
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:border-red-400 focus:outline-none"
            />
          </div>
        </div>

        {error && (
          <div className="mt-3 rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-xs text-red-700">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={loading}
          className="mt-4 w-full rounded-lg bg-red-600 py-2.5 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-60"
        >
          {loading ? "Giris yapiliyor..." : "Giris Yap"}
        </button>
      </form>
    </div>
  );
}
