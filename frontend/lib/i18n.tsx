"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useSyncExternalStore,
} from "react";
import type { Locale } from "@/lib/api";
import bnMessages from "@/messages/bn.json";
import enMessages from "@/messages/en.json";

const STORAGE_KEY = "harbor_locale";
const BANGLA_DIGITS = ["০", "১", "২", "৩", "৪", "৫", "৬", "৭", "৮", "৯"];

type Messages = typeof bnMessages;

const CATALOG: Record<Locale, Messages> = {
  bn: bnMessages,
  en: enMessages,
};

const localeListeners = new Set<() => void>();

function notifyLocaleListeners() {
  localeListeners.forEach((fn) => fn());
}

function subscribeLocale(callback: () => void): () => void {
  localeListeners.add(callback);
  const onStorage = (e: StorageEvent) => {
    if (!e.key || e.key === STORAGE_KEY) callback();
  };
  if (typeof window !== "undefined") {
    window.addEventListener("storage", onStorage);
  }
  return () => {
    localeListeners.delete(callback);
    if (typeof window !== "undefined") {
      window.removeEventListener("storage", onStorage);
    }
  };
}

function getLocaleSnapshot(): Locale {
  if (typeof window === "undefined") return "bn";
  const saved = window.localStorage.getItem(STORAGE_KEY);
  return saved === "en" || saved === "bn" ? saved : "bn";
}

function getServerLocaleSnapshot(): Locale {
  return "bn";
}

export function toBanglaDigits(input: string | number): string {
  return String(input).replace(/[0-9]/g, (d) => BANGLA_DIGITS[Number(d)] ?? d);
}

export function formatLocalizedNumber(value: number | string, locale: Locale): string {
  const formatted =
    typeof value === "number"
      ? new Intl.NumberFormat(locale === "bn" ? "en-IN" : "en-US", {
          maximumFractionDigits: 2,
        }).format(value)
      : String(value);
  return locale === "bn" ? toBanglaDigits(formatted) : formatted;
}

export function translateKey(
  locale: Locale,
  key: string,
  params?: Record<string, string | number>,
): string {
  const parts = key.split(".");
  let current: unknown = CATALOG[locale];
  for (const part of parts) {
    if (current && typeof current === "object" && part in current) {
      current = (current as Record<string, unknown>)[part];
    } else {
      current = undefined;
      break;
    }
  }
  if (typeof current !== "string") {
    let fallback: unknown = CATALOG.en;
    for (const part of parts) {
      if (fallback && typeof fallback === "object" && part in fallback) {
        fallback = (fallback as Record<string, unknown>)[part];
      } else {
        fallback = key;
        break;
      }
    }
    current = typeof fallback === "string" ? fallback : key;
  }

  let text = current as string;
  if (params) {
    for (const [pk, pv] of Object.entries(params)) {
      const strVal =
        typeof pv === "number" ? formatLocalizedNumber(pv, locale) : String(pv);
      text = text.replaceAll(`{${pk}}`, strVal);
    }
  }
  return text;
}

export interface I18nContextValue {
  locale: Locale;
  setLocale: (next: Locale) => void;
  toggleLocale: () => void;
  t: (key: string, params?: Record<string, string | number>) => string;
  formatNumber: (value: number | string) => string;
  pickLocalized: (bnText?: string | null, enText?: string | null) => string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const locale = useSyncExternalStore(
    subscribeLocale,
    getLocaleSnapshot,
    getServerLocaleSnapshot,
  );

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const setLocale = useCallback((next: Locale) => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY, next);
      document.documentElement.lang = next;
      notifyLocaleListeners();
    }
  }, []);

  const toggleLocale = useCallback(() => {
    const next: Locale = getLocaleSnapshot() === "bn" ? "en" : "bn";
    setLocale(next);
  }, [setLocale]);

  const t = useCallback(
    (key: string, params?: Record<string, string | number>) =>
      translateKey(locale, key, params),
    [locale],
  );

  const formatNumber = useCallback(
    (value: number | string) => formatLocalizedNumber(value, locale),
    [locale],
  );

  const pickLocalized = useCallback(
    (bnText?: string | null, enText?: string | null) => {
      if (locale === "bn") {
        return bnText || enText || "";
      }
      return enText || bnText || "";
    },
    [locale],
  );

  const value = useMemo<I18nContextValue>(
    () => ({ locale, setLocale, toggleLocale, t, formatNumber, pickLocalized }),
    [locale, setLocale, toggleLocale, t, formatNumber, pickLocalized],
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
