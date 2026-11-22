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
      className="neu-inset grid gap-2 p-1.5 rounded-[20px]"
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
            className={`min-h-[48px] rounded-[14px] px-4 py-2 text-sm sm:text-base font-bold cursor-pointer transition-all ${
              active ? "skeu-button" : "hover:bg-[var(--surface)]"
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

