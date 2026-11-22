"use client";

import React from "react";
import Link from "next/link";
import { ArrowRight, BookOpen, Cpu, MessageSquareText, Palette, ShieldCheck } from "lucide-react";
import { Badge, Button, Card } from "@/components/ui";
import { useI18n } from "@/lib/i18n";

export default function LandingPage() {
  const { t } = useI18n();

  return (
    <div className="space-y-8 py-4">
      {/* Hero Card */}
      <Card variant="plate" className="p-6 sm:p-10 space-y-6">
        <Badge variant="SAFE_WITH_SPLIT" label={t("landing.badge")} />

        <div className="space-y-4 max-w-3xl">
          <h1
            className="text-3xl sm:text-4xl font-extrabold leading-snug"
            style={{ color: "var(--text)" }}
          >
            {t("landing.heroTitle")}
          </h1>
          <p className="text-base sm:text-lg leading-relaxed" style={{ color: "var(--text-muted)" }}>
            {t("landing.heroDesc")}
          </p>
        </div>

        <div className="flex flex-wrap gap-3 pt-2">
          <Link href="/welcome">
            <Button variant="primary" data-testid="landing-start-btn">
              <span>{t("landing.ctaStart")}</span>
              <ArrowRight className="h-5 w-5" aria-hidden="true" />
            </Button>
          </Link>
          <Link href="/styleguide">
            <Button variant="neu" data-testid="landing-styleguide-btn">
              <Palette className="h-4 w-4" aria-hidden="true" />
              <span>{t("landing.ctaDemo")}</span>
            </Button>
          </Link>
          <Link href="/how-it-works">
            <Button variant="ghost">
              <BookOpen className="h-4 w-4" aria-hidden="true" />
              <span>{t("landing.ctaHowItWorks")}</span>
            </Button>
          </Link>
        </div>
      </Card>

      {/* Three-step Architecture Explainer */}
      <section className="grid gap-5 md:grid-cols-3" aria-label="Architecture steps">
        <Card variant="raised" className="space-y-3">
          <div className="neu-inset flex h-12 w-12 items-center justify-center rounded-[14px]">
            <MessageSquareText className="h-6 w-6" style={{ color: "var(--accent)" }} aria-hidden="true" />
          </div>
          <h2 className="text-lg font-bold" style={{ color: "var(--text)" }}>
            {t("landing.step1Title")}
          </h2>
          <p className="text-sm leading-relaxed" style={{ color: "var(--text-muted)" }}>
            {t("landing.step1Desc")}
          </p>
        </Card>

        <Card variant="raised" className="space-y-3">
          <div className="neu-inset flex h-12 w-12 items-center justify-center rounded-[14px]">
            <Cpu className="h-6 w-6" style={{ color: "var(--accent)" }} aria-hidden="true" />
          </div>
          <h2 className="text-lg font-bold" style={{ color: "var(--text)" }}>
            {t("landing.step2Title")}
          </h2>
          <p className="text-sm leading-relaxed" style={{ color: "var(--text-muted)" }}>
            {t("landing.step2Desc")}
          </p>
        </Card>

        <Card variant="raised" className="space-y-3">
          <div className="neu-inset flex h-12 w-12 items-center justify-center rounded-[14px]">
            <ShieldCheck className="h-6 w-6" style={{ color: "var(--ok)" }} aria-hidden="true" />
          </div>
          <h2 className="text-lg font-bold" style={{ color: "var(--text)" }}>
            {t("landing.step3Title")}
          </h2>
          <p className="text-sm leading-relaxed" style={{ color: "var(--text-muted)" }}>
            {t("landing.step3Desc")}
          </p>
        </Card>
      </section>

      {/* Prototype Honest Disclaimer */}
      <Card variant="glass" className="text-xs sm:text-sm" style={{ color: "var(--text-muted)" }}>
        {t("app.prototypeNotice")}
      </Card>
    </div>
  );
}

