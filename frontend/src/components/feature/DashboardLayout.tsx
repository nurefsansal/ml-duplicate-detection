import Sidebar from "./Sidebar";

interface DashboardLayoutProps {
  children: React.ReactNode;
}

export default function DashboardLayout({ children }: DashboardLayoutProps) {
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex min-h-screen min-w-0 flex-1 flex-col overflow-hidden bg-transparent">
        {children}
      </main>
    </div>
  );
}
