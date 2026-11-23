"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  BellOff,
  CheckCircle2,
  Clock,
  EyeOff,
  GitFork,
  Mic,
  ShieldCheck,
  Sparkles,
  Utensils,
} from "lucide-react";
import { Badge, Button, Card, useToast } from "@/components/ui";
import { ApiError, harborApi } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useSession } from "@/lib/session";

type PreviewMemberId = "mother" | "father" | "arif";

export default function LandingPage() {
  const router = useRouter();
  const { locale, formatNumber, t } = useI18n();
  const { setSession } = useSession();
  const { showToast } = useToast();

  const [selectedMember, setSelectedMember] = useState<PreviewMemberId>("mother");
  const [loadingDemo, setLoadingDemo] = useState(false);

  async function handleQuickDemo() {
    setLoadingDemo(true);
    try {
      const res = await harborApi.seedDemoHousehold(locale);
      setSession({
        householdId: res.household_id,
        householdName: res.name,
        accessCode: res.access_code,
        token: res.token,
        consentGiven: res.consent_given,
        mealTimes: res.meal_times,
        monthlyBudgetBdt: res.monthly_budget_bdt,
      });
      showToast(`${t("welcome.loginSuccess")} (${res.access_code})`, "success");
      router.push("/dashboard");
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : t("common.errorUnexpected");
      showToast(msg, "error");
    } finally {
      setLoadingDemo(false);
    }
  }

  const previewMembers: { id: PreviewMemberId; labelKey: string }[] = [
    { id: "mother", labelKey: "landing.previewMember1" },
    { id: "father", labelKey: "landing.previewMember2" },
    { id: "arif", labelKey: "landing.previewMember3" },
  ];

  const isArif = selectedMember === "arif";
  const isFather = selectedMember === "father";

  return (
    <div className="relative space-y-16 sm:space-y-24 pb-12">
      {/* Subtle Ambient Warm Glow */}
      <div
        aria-hidden="true"
        className="harbor-ambient-glow pointer-events-none fixed inset-0 -z-10"
      />

      {/* Section 1: Asymmetric Editorial Split Hero */}
      <section className="grid gap-10 lg:grid-cols-12 lg:items-center pt-4 sm:pt-8">
        <div className="lg:col-span-7 space-y-6 harbor-reveal">
          <Badge variant="ESTIMATED" label={t("landing.badge")} />

          <div className="space-y-4">
            <h1
              className="font-display text-3xl sm:text-5xl font-bold leading-[1.14] tracking-tight"
              style={{ color: "var(--text)" }}
            >
              {t("landing.heroTitle")}{" "}
              <span className="block mt-1" style={{ color: "var(--accent)" }}>
                {t("landing.heroTitleAccent")}
              </span>
            </h1>
            <p
              className="text-sm sm:text-base leading-relaxed max-w-2xl"
              style={{ color: "var(--text-muted)" }}
            >
              {t("landing.heroDesc")}
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3 pt-1">
            <Link href="/welcome?tab=create">
              <Button variant="primary" data-testid="landing-start-btn">
                <span>{t("landing.ctaStart")}</span>
                <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </Button>
            </Link>
            <Link href="/welcome?tab=login">
              <Button variant="neu">{t("landing.ctaSignIn")}</Button>
            </Link>
            <Button
              variant="ghost"
              onClick={handleQuickDemo}
              disabled={loadingDemo}
              data-testid="landing-demo-btn"
            >
              <Sparkles className="h-4 w-4" style={{ color: "var(--saffron-text)" }} aria-hidden="true" />
              <span>{loadingDemo ? t("common.loading") : t("landing.ctaDemo")}</span>
            </Button>
          </div>

          <div className="grid gap-3 sm:grid-cols-3 pt-3 border-t border-[var(--border-subtle)] text-xs font-medium">
            <div className="flex items-center gap-2" style={{ color: "var(--text-muted)" }}>
              <CheckCircle2 className="h-4 w-4 shrink-0" style={{ color: "var(--ok)" }} aria-hidden="true" />
              <span>{t("landing.heroMetric1")}</span>
            </div>
            <div className="flex items-center gap-2" style={{ color: "var(--text-muted)" }}>
              <GitFork className="h-4 w-4 shrink-0" style={{ color: "var(--saffron-text)" }} aria-hidden="true" />
              <span>{t("landing.heroMetric2")}</span>
            </div>
            <div className="flex items-center gap-2" style={{ color: "var(--text-muted)" }}>
              <EyeOff className="h-4 w-4 shrink-0" style={{ color: "var(--accent)" }} aria-hidden="true" />
              <span>{t("landing.heroMetric3")}</span>
            </div>
          </div>
        </div>

        {/* Interactive Tonight's Kitchen Card */}
        <div className="lg:col-span-5 harbor-reveal harbor-delay-2">
          <Card variant="plate" className="space-y-4">
            <div className="flex items-center justify-between gap-2">
              <div className="space-y-0.5">
                <p className="text-[11px] font-bold uppercase tracking-wider" style={{ color: "var(--accent)" }}>
                  {t("landing.previewTag")}
                </p>
                <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                  {t("landing.previewTitle")}
                </p>
              </div>
              <Utensils className="h-4 w-4 shrink-0" style={{ color: "var(--accent)" }} aria-hidden="true" />
            </div>

            {/* Interactive Member Filter Chips */}
            <div className="flex flex-wrap gap-1.5">
              {previewMembers.map((pm) => {
                const active = selectedMember === pm.id;
                return (
                  <button
                    key={pm.id}
                    type="button"
                    onClick={() => setSelectedMember(pm.id)}
                    className={`rounded-full px-3 py-1.5 text-xs font-semibold cursor-pointer transition-all ${
                      active ? "skeu-button" : "neu-raised-sm"
                    }`}
                    style={active ? undefined : { color: "var(--text)" }}
                  >
                    {t(pm.labelKey)}
                  </button>
                );
              })}
            </div>

            {/* Dynamic Dish Preview */}
            <div className="neu-raised p-4 space-y-3">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-[11px] font-medium" style={{ color: "var(--text-muted)" }}>
                    {t("landing.previewPrompt")}
                  </p>
                  <h2 className="text-base font-bold mt-0.5" style={{ color: "var(--text)" }}>
                    {t("landing.previewSafeDish")}
                  </h2>
                </div>
                <Badge variant={isArif ? "SAFE_DIRECT" : "SAFE_WITH_SPLIT"} />
              </div>

              <p className="text-xs leading-relaxed" style={{ color: "var(--text-muted)" }}>
                {isArif ? t("landing.previewSafeDesc") : t("landing.previewSplitNote")}
              </p>

              {!isArif && (
                <div className="neu-inset p-3 flex items-start gap-2 text-xs">
                  <GitFork className="h-3.5 w-3.5 shrink-0 mt-0.5" style={{ color: "var(--saffron-text)" }} aria-hidden="true" />
                  <span className="font-semibold" style={{ color: "var(--text)" }}>
                    {isFather ? t("landing.previewSplitTag") : t("landing.previewSplitTag")}
                  </span>
                </div>
              )}

              {isArif && (
                <div className="neu-inset p-3 flex items-center justify-between gap-2 text-xs">
                  <div>
                    <p className="font-semibold" style={{ color: "var(--text)" }}>
                      {t("landing.previewBlockedDish")}
                    </p>
                    <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                      {t("landing.previewBlockedReason")}
                    </p>
                  </div>
                  <Badge variant="BLOCKED" />
                </div>
              )}
            </div>

            {/* Floating Calm Patient Reminder Preview */}
            <div className="glass rounded-[14px] px-3.5 py-2.5 flex items-center justify-between gap-3 harbor-float">
              <div className="flex items-center gap-2.5">
                <span
                  className="flex h-8 w-8 items-center justify-center rounded-full"
                  style={{ backgroundColor: "var(--surface)", color: "var(--accent)" }}
                >
                  <Clock className="h-4 w-4" aria-hidden="true" />
                </span>
                <div className="leading-tight">
                  <p className="text-xs font-bold" style={{ color: "var(--text)" }}>
                    {t("landing.previewReminderText")}
                  </p>
                  <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                    {t("landing.previewReminderTime")}
                  </p>
                </div>
              </div>
              <Badge variant="SAFE_DIRECT" label={formatNumber(1)} />
            </div>
          </Card>
        </div>
      </section>

      {/* Section 2: Quiet Care Pillars (Asymmetric Bento) */}
      <section id="features" className="space-y-6 scroll-mt-24">
        <div className="max-w-xl space-y-1.5">
          <p className="text-xs font-bold uppercase tracking-wider" style={{ color: "var(--accent)" }}>
            {t("landing.featuresEyebrow")}
          </p>
          <h2 className="font-display text-2xl sm:text-3xl font-bold" style={{ color: "var(--text)" }}>
            {t("landing.featuresTitle")}
          </h2>
        </div>

        <div className="grid gap-5 md:grid-cols-12">
          <Card variant="raised" className="md:col-span-7 space-y-4">
            <Badge variant="SAFE_WITH_SPLIT" label={t("landing.feature1Badge")} />
            <h3 className="text-lg font-bold" style={{ color: "var(--text)" }}>
              {t("landing.feature1Title")}
            </h3>
            <p className="text-sm leading-relaxed" style={{ color: "var(--text-muted)" }}>
              {t("landing.feature1Desc")}
            </p>
            <div className="grid gap-2 sm:grid-cols-2 pt-1 text-xs font-medium" style={{ color: "var(--text)" }}>
              <div className="neu-inset px-3 py-2.5 flex items-center gap-2">
                <CheckCircle2 className="h-3.5 w-3.5 shrink-0" style={{ color: "var(--ok)" }} aria-hidden="true" />
                <span>{t("landing.feature1Point1")}</span>
              </div>
              <div className="neu-inset px-3 py-2.5 flex items-center gap-2">
                <GitFork className="h-3.5 w-3.5 shrink-0" style={{ color: "var(--saffron-text)" }} aria-hidden="true" />
                <span>{t("landing.feature1Point2")}</span>
              </div>
            </div>
          </Card>

          <Card variant="raised" className="md:col-span-5 flex flex-col justify-between gap-4">
            <div className="space-y-3">
              <Badge variant="SAFE_DIRECT" label={t("landing.feature2Badge")} />
              <h3 className="text-lg font-bold" style={{ color: "var(--text)" }}>
                {t("landing.feature2Title")}
              </h3>
              <p className="text-sm leading-relaxed" style={{ color: "var(--text-muted)" }}>
                {t("landing.feature2Desc")}
              </p>
            </div>
            <div className="neu-inset px-3.5 py-2.5 flex items-center gap-2 text-xs font-semibold" style={{ color: "var(--text)" }}>
              <BellOff className="h-4 w-4 shrink-0" style={{ color: "var(--accent)" }} aria-hidden="true" />
              <span>{t("landing.feature2PrivacyNote")}</span>
            </div>
          </Card>

          <Card variant="raised" className="md:col-span-12 grid gap-4 md:grid-cols-12 md:items-center">
            <div className="md:col-span-7 space-y-2.5">
              <Badge variant="ESTIMATED" label={t("landing.feature3Badge")} />
              <h3 className="text-lg font-bold" style={{ color: "var(--text)" }}>
                {t("landing.feature3Title")}
              </h3>
              <p className="text-sm leading-relaxed" style={{ color: "var(--text-muted)" }}>
                {t("landing.feature3Desc")}
              </p>
            </div>
            <div className="md:col-span-5 neu-inset p-4 space-y-2.5">
              <div className="flex items-center gap-2 text-xs" style={{ color: "var(--text-muted)" }}>
                <Mic className="h-3.5 w-3.5 shrink-0" style={{ color: "var(--accent)" }} aria-hidden="true" />
                <span>{t("landing.feature3VoiceSample")}</span>
              </div>
              <div className="flex items-center gap-2 text-xs font-bold" style={{ color: "var(--ok)" }}>
                <CheckCircle2 className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                <span>{t("landing.feature3ParsedSample")}</span>
              </div>
            </div>
          </Card>
        </div>
      </section>

      {/* Section 3: A Calm Daily Rhythm */}
      <section id="daily-rhythm" className="space-y-6 scroll-mt-24">
        <div className="max-w-xl space-y-1.5">
          <p className="text-xs font-bold uppercase tracking-wider" style={{ color: "var(--accent)" }}>
            {t("landing.rhythmEyebrow")}
          </p>
          <h2 className="font-display text-2xl sm:text-3xl font-bold" style={{ color: "var(--text)" }}>
            {t("landing.rhythmTitle")}
          </h2>
        </div>

        <div className="grid gap-5 md:grid-cols-3">
          {[
            {
              time: t("landing.rhythmMorningTime"),
              title: t("landing.rhythmMorningTitle"),
              desc: t("landing.rhythmMorningDesc"),
            },
            {
              time: t("landing.rhythmAfternoonTime"),
              title: t("landing.rhythmAfternoonTitle"),
              desc: t("landing.rhythmAfternoonDesc"),
            },
            {
              time: t("landing.rhythmEveningTime"),
              title: t("landing.rhythmEveningTitle"),
              desc: t("landing.rhythmEveningDesc"),
            },
          ].map((beat) => (
            <Card key={beat.time} variant="raised" className="space-y-2.5">
              <p className="font-mono text-xs font-semibold" style={{ color: "var(--accent)" }}>
                {beat.time}
              </p>
              <h3 className="text-base font-bold" style={{ color: "var(--text)" }}>
                {beat.title}
              </h3>
              <p className="text-sm leading-relaxed" style={{ color: "var(--text-muted)" }}>
                {beat.desc}
              </p>
            </Card>
          ))}
        </div>
      </section>

      {/* Section 4: Privacy & Trust Promise */}
      <section id="trust" className="space-y-6 scroll-mt-24">
        <div className="max-w-xl space-y-1.5">
          <p className="text-xs font-bold uppercase tracking-wider" style={{ color: "var(--accent)" }}>
            {t("landing.trustEyebrow")}
          </p>
          <h2 className="font-display text-2xl sm:text-3xl font-bold" style={{ color: "var(--text)" }}>
            {t("landing.trustTitle")}
          </h2>
        </div>

        <div className="grid gap-5 md:grid-cols-3">
          {[
            { title: t("landing.trust1Title"), desc: t("landing.trust1Desc") },
            { title: t("landing.trust2Title"), desc: t("landing.trust2Desc") },
            { title: t("landing.trust3Title"), desc: t("landing.trust3Desc") },
          ].map((item) => (
            <Card key={item.title} variant="inset" className="space-y-2">
              <div className="flex items-center gap-2">
                <ShieldCheck className="h-4 w-4 shrink-0" style={{ color: "var(--ok)" }} aria-hidden="true" />
                <h3 className="text-sm font-bold" style={{ color: "var(--text)" }}>
                  {item.title}
                </h3>
              </div>
              <p className="text-xs leading-relaxed" style={{ color: "var(--text-muted)" }}>
                {item.desc}
              </p>
            </Card>
          ))}
        </div>
      </section>

      {/* Closing CTA + Minimal Product Footer */}
      <Card variant="plate" className="p-6 sm:p-8 flex flex-col sm:flex-row sm:items-center justify-between gap-6">
        <div className="space-y-1.5 max-w-xl">
          <h2 className="font-display text-2xl font-bold" style={{ color: "var(--text)" }}>
            {t("landing.closingTitle")}
          </h2>
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>
            {t("landing.closingDesc")}
          </p>
        </div>
        <div className="flex flex-wrap gap-3 shrink-0">
          <Link href="/welcome?tab=create">
            <Button variant="primary">{t("landing.closingCta")}</Button>
          </Link>
        </div>
      </Card>

      <footer className="pt-4 border-t border-[var(--border-subtle)] text-xs leading-relaxed" style={{ color: "var(--text-muted)" }}>
        {t("app.prototypeNotice")}
      </footer>
    </div>
  );
}
