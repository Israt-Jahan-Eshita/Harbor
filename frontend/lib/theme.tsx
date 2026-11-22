"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useSyncExternalStore,
} from "react";

export type ThemeMode = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

const STORAGE_KEY = "harbor_theme";
const themeListeners = new Set<() => void>();

function notifyThemeListeners() {
  themeListeners.forEach((fn) => fn());
}

function subscribeTheme(callback: () => void): () => void {
  themeListeners.add(callback);
  const onStorage = (e: StorageEvent) => {
    if (!e.key || e.key === STORAGE_KEY) callback();
  };
  if (typeof window !== "undefined") {
    window.addEventListener("storage", onStorage);
  }
  return () => {
    themeListeners.delete(callback);
    if (typeof window !== "undefined") {
      window.removeEventListener("storage", onStorage);
    }
  };
}

function getThemeSnapshot(): ThemeMode {
  if (typeof window === "undefined") return "light";
  const saved = window.localStorage.getItem(STORAGE_KEY);
  return saved === "light" || saved === "dark" || saved === "system" ? saved : "light";
}

function getServerThemeSnapshot(): ThemeMode {
  return "light";
}

function subscribeSystemTheme(callback: () => void): () => void {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return () => {};
  }
  const mq = window.matchMedia("(prefers-color-scheme: dark)");
  mq.addEventListener("change", callback);
  return () => mq.removeEventListener("change", callback);
}

function getSystemThemeSnapshot(): ResolvedTheme {
  if (typeof window !== "undefined" && typeof window.matchMedia === "function") {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  return "light";
}

function getServerSystemThemeSnapshot(): ResolvedTheme {
  return "light";
}

export interface ThemeContextValue {
  themeMode: ThemeMode;
  resolvedTheme: ResolvedTheme;
  setThemeMode: (mode: ThemeMode) => void;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const themeMode = useSyncExternalStore(
    subscribeTheme,
    getThemeSnapshot,
    getServerThemeSnapshot,
  );
  const systemTheme = useSyncExternalStore(
    subscribeSystemTheme,
    getSystemThemeSnapshot,
    getServerSystemThemeSnapshot,
  );

  const resolvedTheme: ResolvedTheme =
    themeMode === "system" ? systemTheme : themeMode;

  useEffect(() => {
    document.documentElement.dataset.theme = resolvedTheme;
  }, [resolvedTheme]);

  const setThemeMode = useCallback((mode: ThemeMode) => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY, mode);
      const nextResolved = mode === "system" ? getSystemThemeSnapshot() : mode;
      document.documentElement.dataset.theme = nextResolved;
      notifyThemeListeners();
    }
  }, []);

  const toggleTheme = useCallback(() => {
    const current = getThemeSnapshot();
    const effective = current === "system" ? getSystemThemeSnapshot() : current;
    setThemeMode(effective === "light" ? "dark" : "light");
  }, [setThemeMode]);

  const value = useMemo<ThemeContextValue>(
    () => ({ themeMode, resolvedTheme, setThemeMode, toggleTheme }),
    [themeMode, resolvedTheme, setThemeMode, toggleTheme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    throw new Error("useTheme must be used within ThemeProvider");
  }
  return ctx;
}
