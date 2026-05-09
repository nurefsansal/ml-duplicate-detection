interface HeaderProps {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
}

export default function Header({ title, subtitle, actions }: HeaderProps) {
  return (
    <header className="sticky top-0 z-10 flex flex-shrink-0 items-center justify-between border-b border-slate-200/80 bg-white/85 px-6 py-5 backdrop-blur-md supports-[backdrop-filter]:bg-white/70 lg:px-8">
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900">{title}</h1>
        {subtitle ? (
          <p className="mt-1 text-sm font-medium text-slate-500">{subtitle}</p>
        ) : null}
      </div>
      <div className="flex flex-shrink-0 items-center gap-2">
        {actions}
        <button
          type="button"
          className="relative flex h-10 w-10 cursor-pointer items-center justify-center rounded-xl text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-800"
          aria-label="Bildirimler"
        >
          <i className="ri-notification-3-line text-xl" />
          <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-primary-500 ring-2 ring-white" />
        </button>
        <button
          type="button"
          className="flex h-10 w-10 cursor-pointer items-center justify-center rounded-xl text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-800"
          aria-label="Yardım"
        >
          <i className="ri-question-line text-xl" />
        </button>
      </div>
    </header>
  );
}
