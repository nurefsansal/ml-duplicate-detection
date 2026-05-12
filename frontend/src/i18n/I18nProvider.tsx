import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  type AppLocale,
  bundles,
  interpolate,
  LOCALE_STORAGE_KEY,
} from "./messages";

type I18nContextValue = {
  locale: AppLocale;
  setLocale: (locale: AppLocale) => void;
  /** Örn. `exportPanel.step1Title` — nokta ile iç içe anahtar */
  t: (path: string, vars?: Record<string, string | number>) => string;
  /** Dizi metinler (madde işaretleri) */
  ta: (path: string) => readonly string[];
};

const I18nContext = createContext<I18nContextValue | null>(null);

function getLeaf(
  obj: unknown,
  parts: string[],
): string | readonly string[] | undefined {
  if (parts.length === 0 || obj === null || typeof obj !== "object") {
    return undefined;
  }
  const [head, ...rest] = parts;
  const next = (obj as Record<string, unknown>)[head];
  if (rest.length === 0) {
    if (typeof next === "string") return next;
    if (Array.isArray(next) && next.every((x) => typeof x === "string")) {
      return next as readonly string[];
    }
    return undefined;
  }
  return getLeaf(next, rest);
}

function readStoredLocale(): AppLocale {
  try {
    const raw = localStorage.getItem(LOCALE_STORAGE_KEY);
    return raw === "en" ? "en" : "tr";
  } catch {
    return "tr";
  }
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<AppLocale>(readStoredLocale);

  const setLocale = useCallback((next: AppLocale) => {
    setLocaleState(next);
    try {
      localStorage.setItem(LOCALE_STORAGE_KEY, next);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    document.documentElement.lang = locale === "en" ? "en" : "tr";
  }, [locale]);

  const t = useCallback(
    (path: string, vars?: Record<string, string | number>) => {
      const parts = path.split(".");
      let raw = getLeaf(bundles[locale], parts);
      if (raw === undefined || typeof raw !== "string") {
        raw = getLeaf(bundles.tr, parts);
      }
      const str = typeof raw === "string" ? raw : path;
      return vars ? interpolate(str, vars) : str;
    },
    [locale],
  );

  const ta = useCallback(
    (path: string) => {
      const parts = path.split(".");
      let raw = getLeaf(bundles[locale], parts);
      if (!Array.isArray(raw)) {
        raw = getLeaf(bundles.tr, parts);
      }
      return Array.isArray(raw) ? raw : [];
    },
    [locale],
  );

  const value = useMemo(
    () => ({ locale, setLocale, t, ta }),
    [locale, setLocale, t, ta],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) {
    throw new Error("useI18n must be used within I18nProvider");
  }
  return ctx;
}
