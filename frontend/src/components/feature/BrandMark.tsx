type BrandMarkProps = {
  variant?: "sidebar" | "login" | "icon";
  className?: string;
};

export function BrandIcon({ className = "h-9 w-9" }: { className?: string }) {
  return (
    <div
      className={`flex shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-primary-500 to-indigo-600 text-sm font-bold tracking-tighter text-white shadow-lg shadow-primary-900/30 ${className}`}
      aria-hidden
    >
      UR
    </div>
  );
}

export default function BrandMark({ variant = "sidebar", className = "" }: BrandMarkProps) {
  if (variant === "icon") {
    return <BrandIcon className={className || "h-9 w-9"} />;
  }

  const isLogin = variant === "login";

  return (
    <div className={`flex items-center gap-3 ${className}`}>
      <BrandIcon className={isLogin ? "h-12 w-12 text-base" : "h-9 w-9 text-sm"} />
      <div className="min-w-0">
        <p
          className={`font-semibold tracking-tight ${
            isLogin ? "text-2xl text-slate-900" : "text-sm leading-tight text-white"
          }`}
        >
          Uni<span className={isLogin ? "text-primary-600" : "text-primary-400"}>Record</span>
        </p>
        <p
          className={`font-medium ${
            isLogin ? "mt-1 text-sm text-slate-500" : "mt-0.5 text-[11px] text-slate-500"
          }`}
        >
          Her kişi için tek kayıt
        </p>
      </div>
    </div>
  );
}
