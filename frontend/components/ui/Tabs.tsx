"use client";

import React from "react";

export interface TabOption {
  id: string;
  label: string;
  "data-testid"?: string;
}

export interface TabsProps {
  options: TabOption[];
  value: string;
  onChange: (id: string) => void;
  ariaLabel?: string;
}

export function Tabs({ options, value, onChange, ariaLabel }: TabsProps) {
  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      className="neu-inset grid gap-1.5 p-1 rounded-[13px]"
      style={{ gridTemplateColumns: `repeat(${options.length}, minmax(0, 1fr))` }}
    >
      {options.map((opt) => {
        const active = opt.id === value;
        return (
          <button
            key={opt.id}
            type="button"
            role="tab"
            aria-selected={active}
            data-testid={opt["data-testid"]}
            onClick={() => onChange(opt.id)}
            className={`min-h-[38px] rounded-[10px] px-3 py-1.5 text-sm font-semibold cursor-pointer transition-all ${
              active ? "skeu-button" : "hover:bg-[var(--surface-elevated)]"
            }`}
            style={active ? undefined : { color: "var(--text)" }}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
