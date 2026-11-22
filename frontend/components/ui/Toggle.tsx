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
          className="block text-base font-medium cursor-pointer"
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
        className="neu-inset relative inline-flex h-8 w-14 shrink-0 cursor-pointer items-center rounded-full p-1 transition-colors disabled:opacity-50"
        style={{
          backgroundColor: checked ? "var(--accent)" : "var(--surface)",
        }}
      >
        <span
          className="inline-block h-6 w-6 rounded-full shadow-md transition-transform duration-150"
          style={{
            backgroundColor: "var(--surface-elevated)",
            border: "1px solid var(--border-strong)",
            transform: checked ? "translateX(24px)" : "translateX(0px)",
          }}
        />
      </button>
    </div>
  );
}

