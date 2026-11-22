"use client";

import React from "react";
import Link from "next/link";
import { Award, Cpu, Lock, Palette, ShieldCheck, Sparkles } from "lucide-react";
import { Card } from "@/components/ui";
import { useI18n } from "@/lib/i18n";

export default function HowItWorksPage() {
  const { t } = useI18n();

  const pillars = [
    { title: t("howItWorks.card1Title"), body: t("howItWorks.card1Body"), icon: Cpu },
    { title: t("howItWorks.card2Title"), body: t("howItWorks.card2Body"), icon: ShieldCheck },
    { title: t("howItWorks.card3Title"), body: t("howItWorks.card3Body"), icon: Sparkles },
    { title: t("howItWorks.card4Title"), body: t("howItWorks.card4Body"), icon: Lock },
  ];

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl sm:text-3xl font-extrabold" style={{ color: "var(--text)" }}>
          {t("howItWorks.title")}
        </h1>
        <p className="text-sm sm:text-base" style={{ color: "var(--text-muted)" }}>
          {t("howItWorks.subtitle")}
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        {pillars.map((p, idx) => {
          const Icon = p.icon;
          return (
            <Card key={idx} variant="raised" className="space-y-3">
              <div className="flex items-center gap-2.5">
                <span className="skeu-button flex h-9 w-9 shrink-0 items-center justify-center rounded-[12px]">
                  <Icon className="h-4 w-4" aria-hidden="true" />
                </span>
                <h2 className="text-base sm:text-lg font-extrabold" style={{ color: "var(--text)" }}>
                  {p.title}
                </h2>
              </div>
              <p className="text-sm leading-relaxed" style={{ color: "var(--text-muted)" }}>
                {p.body}
              </p>
            </Card>
          );
        })}
      </div>

      <Card variant="glass" className="space-y-4">
        <h2 className="text-lg font-extrabold" style={{ color: "var(--text)" }}>
          {t("howItWorks.exploreLinksTitle")}
        </h2>
        <div className="flex flex-wrap gap-3">
          <Link
            href="/engine"
            className="skeu-button inline-flex min-h-[48px] items-center gap-2 px-4 py-2.5 text-sm font-bold"
          >
            <Cpu className="h-4 w-4" aria-hidden="true" />
            <span>{t("howItWorks.openEngine")}</span>
          </Link>
          <Link
            href="/eval"
            className="neu-raised-sm inline-flex min-h-[48px] items-center gap-2 px-4 py-2.5 text-sm font-bold"
            style={{ color: "var(--text)" }}
          >
            <Award className="h-4 w-4" style={{ color: "var(--accent)" }} aria-hidden="true" />
            <span>{t("howItWorks.openEval")}</span>
          </Link>
          <Link
            href="/styleguide"
            className="neu-raised-sm inline-flex min-h-[48px] items-center gap-2 px-4 py-2.5 text-sm font-bold"
            style={{ color: "var(--text)" }}
          >
            <Palette className="h-4 w-4" style={{ color: "var(--accent)" }} aria-hidden="true" />
            <span>{t("howItWorks.openStyleguide")}</span>
          </Link>
        </div>
      </Card>
    </div>
  );
}

