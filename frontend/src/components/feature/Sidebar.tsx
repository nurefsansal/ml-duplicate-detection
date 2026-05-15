import { useState } from "react";
import { NavLink, useLocation } from "react-router-dom";

import { withUploadContext } from "../../utils/uploadContextNav";

const navItems = [
  { path: "/", icon: "ri-dashboard-3-line", label: "Dashboard" },
  { path: "/veri-yukleme", icon: "ri-upload-cloud-2-line", label: "Veri Yükleme" },
  { path: "/ham-veri", icon: "ri-table-2", label: "Ham Veri" },
  { path: "/veri-normalizasyon", icon: "ri-filter-3-line", label: "Veri Standardizasyon" },
  { path: "/temiz-veri-seti", icon: "ri-table-line", label: "Temiz Veri Seti" },
  { path: "/mukerrer-tespit", icon: "ri-search-eye-line", label: "Mükerrer Tespit" },
  { path: "/mukerrer-kayitlar", icon: "ri-file-copy-2-line", label: "Mükerrer Kayıtlar" },
  { path: "/ayarlar", icon: "ri-settings-4-line", label: "Ayarlar" },
  { path: "/raporlar", icon: "ri-bar-chart-box-line", label: "Raporlar" },
];

export default function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const location = useLocation();

  return (
    <aside
      className={`${collapsed ? "w-[4.25rem]" : "w-64"} relative flex min-h-screen flex-shrink-0 flex-col border-r border-slate-800/80 bg-slate-950 text-slate-300 shadow-nav transition-all duration-300 ease-out`}
    >
      <div
        className="pointer-events-none absolute inset-0 bg-gradient-to-b from-primary-900/25 via-transparent to-indigo-950/30"
        aria-hidden
      />

      <div
        className={`relative flex items-center border-b border-slate-800/80 py-5 ${collapsed ? "justify-center px-2" : "px-5"}`}
      >
        {!collapsed && (
          <div className="flex flex-1 items-center gap-3">
            <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-primary-500 to-indigo-600 shadow-lg shadow-primary-900/40">
              <i className="ri-stack-line text-lg text-white" aria-hidden />
            </div>
            <div className="min-w-0">
              <p className="text-sm font-semibold leading-tight tracking-tight text-white">
                Kayıt Tespit Sistemi
              </p>
              <p className="mt-0.5 text-[11px] font-medium text-slate-500">
                Veri kalite platformu
              </p>
            </div>
          </div>
        )}

        {collapsed && (
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-primary-500 to-indigo-600 shadow-lg">
            <i className="ri-stack-line text-lg text-white" />
          </div>
        )}

        {!collapsed && (
          <button
            type="button"
            onClick={() => setCollapsed(true)}
            className="ml-1 flex h-8 w-8 cursor-pointer items-center justify-center rounded-lg text-slate-500 transition-colors hover:bg-slate-800 hover:text-slate-200"
            aria-label="Kenar çubuğunu daralt"
          >
            <i className="ri-arrow-left-s-line text-lg" />
          </button>
        )}
      </div>

      <nav className="relative flex-1 space-y-1 overflow-y-auto px-2 py-4">
        {navItems.map((item) => {
          const isActive = location.pathname === item.path;

          return (
            <NavLink
              key={item.path}
              to={withUploadContext(item.path)}
              className={`group flex items-center gap-3 rounded-xl px-3 py-2.5 transition-all duration-200 ${
                isActive
                  ? "bg-gradient-to-r from-primary-600/25 to-indigo-600/20 text-white shadow-sm ring-1 ring-primary-500/30"
                  : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-100"
              } ${collapsed ? "justify-center" : ""}`}
              title={collapsed ? item.label : undefined}
            >
              <div className="flex h-5 w-5 flex-shrink-0 items-center justify-center">
                <i
                  className={`${item.icon} text-[17px] transition-transform duration-200 group-hover:scale-105`}
                />
              </div>

              {!collapsed && (
                <span className="text-sm font-medium tracking-tight">{item.label}</span>
              )}

              {isActive && !collapsed && (
                <div className="ml-auto h-1.5 w-1.5 rounded-full bg-cyan-400 shadow-[0_0_8px_rgba(34,211,238,0.8)]" />
              )}
            </NavLink>
          );
        })}
      </nav>

      {collapsed && (
        <div className="relative border-t border-slate-800/80 p-2">
          <button
            type="button"
            onClick={() => setCollapsed(false)}
            className="flex w-full cursor-pointer items-center justify-center rounded-xl p-2 text-slate-500 transition-colors hover:bg-slate-800 hover:text-slate-200"
            aria-label="Kenar çubuğunu genişlet"
          >
            <i className="ri-arrow-right-s-line text-lg" />
          </button>
        </div>
      )}
    </aside>
  );
}
