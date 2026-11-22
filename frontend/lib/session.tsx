"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
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

function loadInitialSession(): HarborSession | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as HarborSession;
  } catch {
    return null;
  }
}

export interface SessionContextValue {
  session: HarborSession | null;
  setSession: (next: HarborSession | null) => void;
  updateMealTimes: (mealTimes: HarborSession["mealTimes"]) => void;
  clearSession: () => void;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [session, setSessionState] = useState<HarborSession | null>(() =>
    loadInitialSession(),
  );

  const setSession = useCallback((next: HarborSession | null) => {
    setSessionState(next);
    if (typeof window !== "undefined") {
      if (next) {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      } else {
        window.localStorage.removeItem(STORAGE_KEY);
      }
    }
  }, []);

  const updateMealTimes = useCallback(
    (mealTimes: HarborSession["mealTimes"]) => {
      setSessionState((prev) => {
        if (!prev) return prev;
        const updated = { ...prev, mealTimes };
        if (typeof window !== "undefined") {
          window.localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
        }
        return updated;
      });
    },
    [],
  );

  const clearSession = useCallback(() => {
    setSession(null);
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

