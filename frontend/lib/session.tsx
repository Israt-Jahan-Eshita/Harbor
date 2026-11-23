"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useSyncExternalStore,
} from "react";

/**
 * Household caregiver session stored in localStorage for prototype simplicity.
 * Production deployments should migrate session tokens to httpOnly SameSite cookies.
 */
export interface HarborSession {
  householdId: string;
  householdName: string;
  accessCode: string;
  token: string;
  consentGiven: boolean;
  mealTimes: { breakfast: string; lunch: string; dinner: string };
  monthlyBudgetBdt?: number | null;
}

const STORAGE_KEY = "harbor_session";
const listeners = new Set<() => void>();
let cachedRaw: string | null | undefined;
let cachedSession: HarborSession | null = null;

function notifyListeners() {
  listeners.forEach((fn) => fn());
}

function subscribe(callback: () => void): () => void {
  listeners.add(callback);
  const onStorage = (e: StorageEvent) => {
    if (!e.key || e.key === STORAGE_KEY) {
      cachedRaw = undefined;
      callback();
    }
  };
  if (typeof window !== "undefined") {
    window.addEventListener("storage", onStorage);
  }
  return () => {
    listeners.delete(callback);
    if (typeof window !== "undefined") {
      window.removeEventListener("storage", onStorage);
    }
  };
}

function getSnapshot(): HarborSession | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (raw === cachedRaw) return cachedSession;
  cachedRaw = raw;
  if (!raw) {
    cachedSession = null;
    return null;
  }
  try {
    const parsed = JSON.parse(raw) as Partial<HarborSession>;
    if (
      parsed &&
      typeof parsed.householdId === "string" &&
      parsed.householdId.length > 0 &&
      typeof parsed.token === "string" &&
      parsed.token.length > 0 &&
      typeof parsed.accessCode === "string" &&
      parsed.accessCode.length > 0
    ) {
      cachedSession = parsed as HarborSession;
      return cachedSession;
    }
    window.localStorage.removeItem(STORAGE_KEY);
    cachedRaw = null;
    cachedSession = null;
  } catch {
    cachedSession = null;
  }
  return null;
}

function getServerSnapshot(): HarborSession | null {
  return null;
}

export interface SessionContextValue {
  session: HarborSession | null;
  setSession: (next: HarborSession | null) => void;
  updateMealTimes: (mealTimes: HarborSession["mealTimes"]) => void;
  clearSession: () => void;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const session = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  const setSession = useCallback((next: HarborSession | null) => {
    if (typeof window !== "undefined") {
      if (next) {
        const serialized = JSON.stringify(next);
        cachedRaw = serialized;
        cachedSession = next;
        window.localStorage.setItem(STORAGE_KEY, serialized);
      } else {
        cachedRaw = null;
        cachedSession = null;
        window.localStorage.removeItem(STORAGE_KEY);
      }
      notifyListeners();
    }
  }, []);

  const updateMealTimes = useCallback((mealTimes: HarborSession["mealTimes"]) => {
    const current = getSnapshot();
    if (!current || typeof window === "undefined") return;
    const updated: HarborSession = { ...current, mealTimes };
    const serialized = JSON.stringify(updated);
    cachedRaw = serialized;
    cachedSession = updated;
    window.localStorage.setItem(STORAGE_KEY, serialized);
    notifyListeners();
  }, []);

  const clearSession = useCallback(() => {
    setSession(null);
    if (typeof window !== "undefined" && "caches" in window) {
      window.caches
        .keys()
        .then((keys) => Promise.all(keys.map((k) => window.caches.delete(k))))
        .catch(() => undefined);
    }
  }, [setSession]);

  const value = useMemo<SessionContextValue>(
    () => ({ session, setSession, updateMealTimes, clearSession }),
    [session, setSession, updateMealTimes, clearSession],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const ctx = useContext(SessionContext);
  if (!ctx) {
    throw new Error("useSession must be used within SessionProvider");
  }
  return ctx;
}
