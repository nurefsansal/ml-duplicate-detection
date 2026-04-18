import { useState } from "react";
import { NavLink, useLocation } from "react-router-dom";

const navItems = [
  { path: "/", icon: "ri-dashboard-3-line", label: "Dashboard" },
  {
    path: "/veri-yukleme",
    icon: "ri-upload-cloud-2-line",
    label: "Veri Yükleme",
  },
  {
    path: "/veri-normalizasyon",
    icon: "ri-filter-3-line",
    label: "Veri Normalizasyon",
  },
  {
    path: "/mukerrer-tespit",
    icon: "ri-search-eye-line",
    label: "Mükerrer Tespit",
  },
  {
    path: "/mukerrer-kayitlar",
    icon: "ri-file-copy-2-line",
    label: "Mükerrer Kayıtlar",
  },
  {
    path: "/yonetici-onayi",
    icon: "ri-checkbox-circle-line",
    label: "Yönetici Onayı",
  },
  { path: "/ayarlar", icon: "ri-settings-4-line", label: "Ayarlar" },
  { path: "/raporlar", icon: "ri-bar-chart-box-line", label: "Raporlar" },
];

export default function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const location = useLocation();

  return (
    <aside
      className={`${collapsed ? "w-16" : "w-64"} flex-shrink-0 bg-white border-r border-gray-100 flex flex-col transition-all duration-300 min-h-screen`}
    >
      <div
        className={`flex items-center ${collapsed ? "justify-center px-0" : "px-5"} py-5 border-b border-gray-100`}
      >
        {!collapsed && (
          <div className="flex items-center gap-3 flex-1">
            <div className="w-8 h-8 flex items-center justify-center flex-shrink-0">
              <img
                src="https://static.readdy.ai/image/2efa4a2fc14b02768a2ef78ac82f3041/97530cc188494aabe80a972e6a98a906.png"
                alt="Logo"
                className="w-8 h-8 object-contain"
              />
            </div>
            <div>
              <p className="text-xs font-bold text-gray-900 leading-none">
                MükerrerTespit
              </p>
              <p className="text-[10px] text-gray-400 mt-0.5">
                Kayıt Yönetim Sistemi
              </p>
            </div>
          </div>
        )}
        {collapsed && (
          <div className="w-8 h-8 flex items-center justify-center">
            <img
              src="https://static.readdy.ai/image/2efa4a2fc14b02768a2ef78ac82f3041/97530cc188494aabe80a972e6a98a906.png"
              alt="Logo"
              className="w-7 h-7 object-contain"
            />
          </div>
        )}
        {!collapsed && (
          <button
            onClick={() => setCollapsed(true)}
            className="w-6 h-6 flex items-center justify-center text-gray-400 hover:text-gray-600 cursor-pointer rounded"
          >
            <i className="ri-arrow-left-s-line text-base"></i>
          </button>
        )}
      </div>

      <nav className="flex-1 py-4 px-2 space-y-0.5 overflow-y-auto">
        {navItems.map((item) => {
          const isActive = location.pathname === item.path;
          return (
            <NavLink
              key={item.path}
              to={item.path}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200 group ${
                isActive
                  ? "bg-red-600 text-white"
                  : "text-gray-500 hover:bg-gray-50 hover:text-gray-800"
              } ${collapsed ? "justify-center" : ""}`}
              title={collapsed ? item.label : undefined}
            >
              <div className="w-5 h-5 flex items-center justify-center flex-shrink-0">
                <i className={`${item.icon} text-base`}></i>
              </div>
              {!collapsed && (
                <span className="text-sm font-medium whitespace-nowrap">
                  {item.label}
                </span>
              )}
              {isActive && !collapsed && (
                <div className="ml-auto w-1.5 h-1.5 rounded-full bg-red-200"></div>
              )}
            </NavLink>
          );
        })}
      </nav>

      {collapsed && (
        <div className="p-2 border-t border-gray-100">
          <button
            onClick={() => setCollapsed(false)}
            className="w-full flex items-center justify-center p-2 text-gray-400 hover:text-gray-600 cursor-pointer rounded-lg hover:bg-gray-50"
          >
            <i className="ri-arrow-right-s-line text-base"></i>
          </button>
        </div>
      )}

      {!collapsed && (
        <div className="p-3 border-t border-gray-100">
          <div className="flex items-center gap-3 p-2 rounded-lg hover:bg-gray-50 cursor-pointer">
            <div className="w-8 h-8 rounded-full bg-red-100 flex items-center justify-center flex-shrink-0">
              <span className="text-xs font-bold text-red-600">AK</span>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-semibold text-gray-800 truncate">
                Ayşe Kara
              </p>
              <p className="text-[10px] text-gray-400 truncate">
                Sistem Yöneticisi
              </p>
            </div>
            <div className="w-4 h-4 flex items-center justify-center">
              <i className="ri-more-2-line text-gray-400 text-sm"></i>
            </div>
          </div>
        </div>
      )}
    </aside>
  );
}
