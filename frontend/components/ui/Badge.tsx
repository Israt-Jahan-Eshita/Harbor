"use client";

import React from "react";
import {
  CheckCircle2,
  GitFork,
  HelpCircle,
  OctagonAlert,
  Tag,
} from "lucide-react";
import { useI18n } from "@/lib/i18n";

export type BadgeVariant =
  | "SAFE_DIRECT"
  | "SAFE_WITH_SPLIT"
  | "BLOCKED"
  | "UNVERIFIED"
  | "ESTIMATED"
  | "INFO";

export interface BadgeProps {
  variant: BadgeVariant;
  label?: string;
  ruleId?: string;
  className?: string;
}

export function Badge({ variant, label, ruleId, className = "" }: BadgeProps) {
  const { t } = useI18n();

  const resolvedLabel =
    label ||
    (variant === "INFO" ? "" : t(`status.${variant}`));

  let Icon = Tag;
  let style: React.CSSProperties = {
    color: "var(--text)",
    borderColor: "var(--border-strong)",
  };

  switch (variant) {
    case "SAFE_DIRECT":
      Icon = CheckCircle2;
      style = {
        backgroundColor: "var(--ok)",
        color: "var(--on-ok)",
        borderColor: "var(--ok)",
      };
      break;
    case "SAFE_WITH_SPLIT":
      Icon = GitFork;
      style = {
        backgroundColor: "var(--saffron)",
        color: "var(--on-saffron)",
        borderColor: "var(--saffron-text)",
      };
      break;
    case "BLOCKED":
      Icon = OctagonAlert;
      style = {
        backgroundColor: "var(--danger)",
        color: "var(--on-danger)",
        borderColor: "var(--danger)",
      };
      break;
    case "UNVERIFIED":
      Icon = HelpCircle;
      style = {
        backgroundColor: "var(--surface)",
        color: "var(--text)",
        borderColor: "var(--text-muted)",
      };
      break;
    case "ESTIMATED":
      Icon = Tag;
      style = {
        backgroundColor: "var(--surface-elevated)",
        color: "var(--saffron-text)",
        borderColor: "var(--saffron-text)",
      };
      break;
    case "INFO":
      Icon = Tag;
      break;
  }

  return (
    <span
      className={`skeu-tag inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-bold tracking-wide ${className}`.trim()}
      style={style}
    >
      <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      <span>{resolvedLabel}</span>
      {ruleId && <span className="font-mono text-[11px] opacity-90">({ruleId})</span>}
    </span>
  );
}

