import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useAuth } from "@/hooks/useAuth";
import type { AppLocale } from "@/i18n/types";
import { normalizeLocale, translate } from "@/i18n/index";
import { fetchUserLocale, localeStorageKey, saveUserLocale } from "@/services/localeApi";

type LocaleContextValue = {
  locale: AppLocale;
  setLocale: (next: AppLocale) => Promise<void>;
  toggleLocale: () => Promise<void>;
  t: (key: string, params?: Record<string, string | number>, fallback?: string) => string;
  ready: boolean;
};

const LocaleContext = createContext<LocaleContextValue | null>(null);

function readCachedLocale(userId?: string | null): AppLocale | null {
  try {
    const raw = localStorage.getItem(localeStorageKey(userId));
    if (!raw) return null;
    return normalizeLocale(raw);
  } catch {
    return null;
  }
}

function writeCachedLocale(userId: string | null | undefined, locale: AppLocale) {
  try {
    localStorage.setItem(localeStorageKey(userId), locale);
  } catch {
    //
  }
}

export function LocaleProvider({ children }: { children: ReactNode }) {
  const { user, refreshUser } = useAuth();
  const [locale, setLocaleState] = useState<AppLocale>(() => readCachedLocale(null) || "zh");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    document.documentElement.lang = locale === "en" ? "en" : "zh-CN";
  }, [locale]);

  useEffect(() => {
    let cancelled = false;
    setReady(false);

    (async () => {
      if (!user?.id) {
        const guest = readCachedLocale(null) || "zh";
        if (!cancelled) {
          setLocaleState(guest);
          setReady(true);
        }
        return;
      }

      const cached = readCachedLocale(user.id);
      if (cached && !cancelled) setLocaleState(cached);

      if (user.ui_locale) {
        const fromUser = normalizeLocale(user.ui_locale);
        if (!cancelled) {
          setLocaleState(fromUser);
          writeCachedLocale(user.id, fromUser);
          setReady(true);
        }
        return;
      }

      try {
        const remote = await fetchUserLocale();
        if (!cancelled && remote) {
          setLocaleState(remote);
          writeCachedLocale(user.id, remote);
        }
      } finally {
        if (!cancelled) setReady(true);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [user?.id, user?.ui_locale]);

  const setLocale = useCallback(
    async (next: AppLocale) => {
      const normalized = normalizeLocale(next);
      setLocaleState(normalized);
      writeCachedLocale(user?.id, normalized);

      if (user?.id) {
        try {
          await saveUserLocale(normalized);
          await refreshUser();
        } catch {
          // 本地已切换，服务端失败时下次登录可重试
        }
      } else {
        writeCachedLocale(null, normalized);
      }
    },
    [refreshUser, user?.id]
  );

  const toggleLocale = useCallback(async () => {
    await setLocale(locale === "en" ? "zh" : "en");
  }, [locale, setLocale]);

  const t = useCallback(
    (key: string, params?: Record<string, string | number>, fallback?: string) =>
      translate(locale, key, params, fallback),
    [locale]
  );

  const value = useMemo(
    () => ({ locale, setLocale, toggleLocale, t, ready }),
    [locale, setLocale, toggleLocale, t, ready]
  );

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useLocale() {
  const ctx = useContext(LocaleContext);
  if (!ctx) throw new Error("useLocale must be used within LocaleProvider");
  return ctx;
}

/** 导航标签 */
export function useNavLabel(navId: string, fallback?: string) {
  const { t } = useLocale();
  return t(`nav.${navId}`, undefined, fallback || navId);
}
