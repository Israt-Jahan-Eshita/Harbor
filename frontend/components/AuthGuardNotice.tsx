"use client";

import React, { useState } from "react";
import Link from "next/link";
import { KeyRound, Sparkles } from "lucide-react";
import { Button, Card, useToast } from "@/components/ui";
import { ApiError, harborApi } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useSession } from "@/lib/session";

export function AuthGuardNotice({ onAuthenticated }: { onAuthenticated?: () => void }) {
  const { locale, t } = useI18n();
  const { setSession } = useSession();
  const { showToast } = useToast();
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
      onAuthenticated?.();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : t("common.errorUnexpected");
      showToast(msg, "error");
    } finally {
      setLoadingDemo(false);
    }
  }

  return (
    <Card variant="raised" className="mx-auto max-w-xl space-y-4">
      <div className="flex items-start gap-3">
        <KeyRound className="h-6 w-6 shrink-0 mt-0.5" style={{ color: "var(--accent)" }} aria-hidden="true" />
        <div className="space-y-1">
          <h2 className="text-lg font-bold" style={{ color: "var(--text)" }}>
            {t("auth.requiredTitle")}
          </h2>
          <p className="text-sm leading-relaxed" style={{ color: "var(--text-muted)" }}>
            {t("auth.requiredDesc")}
          </p>
        </div>
      </div>
      <div className="flex flex-wrap gap-3">
        <Link
          href="/welcome"
          className="skeu-button inline-flex min-h-[48px] items-center justify-center gap-2 px-5 py-3 text-sm font-bold"
        >
          <KeyRound className="h-4 w-4" aria-hidden="true" />
          <span>{t("auth.goWelcome")}</span>
        </Link>
        <Button
          variant="neu"
          onClick={handleQuickDemo}
          disabled={loadingDemo}
          data-testid="auth-guard-load-demo"
        >
          <Sparkles className="h-4 w-4" style={{ color: "var(--saffron-text)" }} aria-hidden="true" />
          <span>{loadingDemo ? t("common.loading") : t("auth.quickDemo")}</span>
        </Button>
      </div>
    </Card>
  );
}

