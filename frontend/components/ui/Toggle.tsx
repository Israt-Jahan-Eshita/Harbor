"use client";

import React, { useId } from "react";

export interface ToggleProps {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
  hint?: string;
  disabled?: boolean;
  "data-testid"?: string;
}

export function Toggle({
  checked,
  onChange,
  label,
  hint,
  disabled = false,
  "data-testid": testId,
}: ToggleProps) {
  const id = useId();

  return (
    <div className="flex items-center justify-between gap-4 py-1">
      <div className="space-y-0.5">
        <label
          htmlFor={id}
          className="block text-sm font-medium cursor-pointer"
          style={{ color: "var(--text)" }}
        >
          {label}
        </label>
        {hint && (
          <p className="text-xs" style={{ color: "var(--text-muted)" }}>
            {hint}
          </p>
        )}
      </div>
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        disabled={disabled}
        data-testid={testId}
        onClick={() => onChange(!checked)}
        className="neu-inset relative inline-flex h-7 w-12 shrink-0 cursor-pointer items-center rounded-full p-1 transition-colors disabled:opacity-50"
        style={{
          backgroundColor: checked ? "var(--accent)" : "var(--surface)",
        }}
      >
        <span
          className="inline-block h-5 w-5 rounded-full shadow-sm transition-transform duration-150"
          style={{
            backgroundColor: "var(--surface-elevated)",
            border: "1px solid var(--border-strong)",
            transform: checked ? "translateX(20px)" : "translateX(0px)",
          }}
        />
      </button>
    </div>
  );
}

