import React from "react";

export function Skeleton({ className = "h-6 w-full" }: { className?: string }) {
  return (
    <div
      className={`animate-pulse rounded-[14px] ${className}`.trim()}
      style={{ backgroundColor: "var(--shadow-dark)", opacity: 0.45 }}
      aria-hidden="true"
    />
  );
}

