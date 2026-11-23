"use client";

import React, { useEffect } from "react";
import { X } from "lucide-react";
import { useI18n } from "@/lib/i18n";

export interface SheetProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
}

export function Sheet({ open, onClose, title, children }: SheetProps) {
  const { t } = useI18n();

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center sm:items-center p-4"
      style={{ backgroundColor: "rgba(24, 20, 17, 0.48)" }}
      role="dialog"
      aria-modal="true"
      aria-label={title}
      onClick={onClose}
    >
      <div
        className="glass harbor-sheet-in w-full max-w-lg rounded-[20px] p-5 space-y-4 max-h-[85vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-base font-bold" style={{ color: "var(--text)" }}>
            {title}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label={t("common.close")}
            className="neu-raised-sm flex h-10 w-10 items-center justify-center rounded-full cursor-pointer"
            style={{ color: "var(--text)" }}
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
        <div>{children}</div>
      </div>
    </div>
  );
}
