"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
} from "react";
import { AlertCircle, CheckCircle2, Info, X } from "lucide-react";

export type ToastType = "info" | "success" | "error";

interface ToastItem {
  id: string;
  message: string;
  type: ToastType;
}

interface ToastContextValue {
  showToast: (message: string, type?: ToastType) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((item) => item.id !== id));
  }, []);

  const showToast = useCallback(
    (message: string, type: ToastType = "info") => {
      const id = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
      setToasts((prev) => [...prev, { id, message, type }]);
      setTimeout(() => dismiss(id), 4500);
    },
    [dismiss],
  );

  const value = useMemo(() => ({ showToast }), [showToast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        className="fixed bottom-24 right-4 z-50 flex flex-col gap-2 max-w-sm sm:bottom-6"
        aria-live="polite"
      >
        {toasts.map((toast) => {
          const Icon =
            toast.type === "success"
              ? CheckCircle2
              : toast.type === "error"
                ? AlertCircle
                : Info;
          const accentColor =
            toast.type === "success"
              ? "var(--ok)"
              : toast.type === "error"
                ? "var(--danger)"
                : "var(--accent)";

          return (
            <div
              key={toast.id}
              className="glass flex items-center gap-3 rounded-[18px] px-4 py-3 text-sm font-semibold"
              style={{ color: "var(--text)" }}
              role="status"
            >
              <Icon
                className="h-5 w-5 shrink-0"
                style={{ color: accentColor }}
                aria-hidden="true"
              />
              <span className="flex-1">{toast.message}</span>
              <button
                type="button"
                onClick={() => dismiss(toast.id)}
                className="p-1 cursor-pointer"
                aria-label="Close notification"
              >
                <X className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast must be used within ToastProvider");
  }
  return ctx;
}

