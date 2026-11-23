"use client";

import React, { useId } from "react";

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  hint?: string;
  error?: string;
}

export function Input({
  label,
  hint,
  error,
  id,
  className = "",
  ...rest
}: InputProps) {
  const autoId = useId();
  const inputId = id || autoId;

  return (
    <div className="space-y-1.5">
      {label && (
        <label
          htmlFor={inputId}
          className="block text-xs font-semibold tracking-wide"
          style={{ color: "var(--text)" }}
        >
          {label}
        </label>
      )}
      <input
        id={inputId}
        className={`neu-inset w-full min-h-[42px] rounded-[11px] px-3.5 py-2 text-sm placeholder:text-[var(--text-muted)] focus:border-[var(--accent)] focus:outline-none ${className}`.trim()}
        style={{
          color: "var(--text)",
          borderColor: error ? "var(--danger)" : undefined,
        }}
        aria-invalid={Boolean(error)}
        {...rest}
      />
      {hint && !error && (
        <p className="text-xs" style={{ color: "var(--text-muted)" }}>
          {hint}
        </p>
      )}
      {error && (
        <p className="text-xs font-semibold" style={{ color: "var(--danger)" }} role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
