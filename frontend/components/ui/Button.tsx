"use client";

import React from "react";

export type ButtonVariant = "primary" | "neu" | "skeu" | "ghost" | "danger";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  fullWidth?: boolean;
}

export function Button({
  variant = "primary",
  fullWidth = false,
  className = "",
  children,
  style,
  type = "button",
  ...rest
}: ButtonProps) {
  const base =
    "inline-flex min-h-[48px] items-center justify-center gap-2 rounded-[18px] px-5 py-3 text-base font-semibold select-none cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed transition-transform duration-150";
  const widthClass = fullWidth ? "w-full" : "";

  let variantClass = "";
  let variantStyle: React.CSSProperties = {};

  switch (variant) {
    case "primary":
    case "skeu":
      variantClass = "skeu-button";
      break;
    case "neu":
      variantClass = "neu-raised-sm active:neu-pressed";
      variantStyle = { color: "var(--text)" };
      break;
    case "ghost":
      variantClass = "border border-[var(--border-strong)] bg-transparent hover:bg-[var(--surface)]";
      variantStyle = { color: "var(--text)" };
      break;
    case "danger":
      variantClass = "border border-[var(--danger)] shadow-md active:translate-y-[1px]";
      variantStyle = {
        backgroundColor: "var(--danger)",
        color: "var(--on-danger)",
      };
      break;
  }

  return (
    <button
      type={type}
      className={`${base} ${variantClass} ${widthClass} ${className}`.trim()}
      style={{ ...variantStyle, ...style }}
      {...rest}
    >
      {children}
    </button>
  );
}

