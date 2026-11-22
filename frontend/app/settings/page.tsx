"use client";

import React, { useState } from "react";
import { Bell, Clock, Languages, Palette, Sparkles } from "lucide-react";
import { Button, Card, Input, Tabs, Toggle, useToast } from "@/components/ui";
import { ApiError, harborApi } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useSession } from "@/lib/session";
import { ThemeMode, useTheme } from "@/lib/theme";

export default function SettingsPage() {
  const { locale, setLocale, formatNumber, t } = useI18n();
  const { themeMode, setThemeMode } = useTheme();
  const { session, setSession, updateMealTimes } = useSession();
  const { showToast } = useToast();

  const [breakfast, setBreakfast] = useState(session?.mealTimes.breakfast || "08:00");
  const [lunch, setLunch] = useState(session?.mealTimes.lunch || "13:30");
  const [dinner, setDinner] = useState(session?.mealTimes.dinner || "21:00");
  const [pushEnabled, setPushEnabled] = useState(false);
  const [consent, setConsent] = useState(session?.consentGiven ?? false);
  const [loadingDemo, setLoadingDemo] = useState(false);

  function handleSaveMealTimes(e: React.FormEvent) {
    e.preventDefault();
    updateMealTimes({ breakfast, lunch, dinner });
    showToast(t("settings.savedToast"), "success");
  }

  async function handleLoadDemo() {
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
      showToast(t("welcome.loginSuccess"), "success");
    } catch (err) {
      const msg =
        err instanceof ApiError && (err.status === 404 || err.status === 0)
          ? t("common.comingSoon")
          : t("common.errorUnexpected");
      showToast(msg, "info");
    } finally {
      setLoadingDemo(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl sm:text-3xl font-extrabold" style={{ color: "var(--text)" }}>
          {t("settings.title")}
        </h1>
        <p className="text-sm sm:text-base" style={{ color: "var(--text-muted)" }}>
          {t("settings.subtitle")}
        </p>
      </div>

      {/* Language Switcher (Full-System EN <-> BN) */}
      <Card variant="raised" className="space-y-4">
        <div className="flex items-start gap-3">
          <Languages className="h-5 w-5 shrink-0 mt-1" style={{ color: "var(--accent)" }} aria-hidden="true" />
          <div className="space-y-1">
            <h2 className="text-lg font-bold" style={{ color: "var(--text)" }}>
              {t("settings.languageCardTitle")}
            </h2>
            <p className="text-sm" style={{ color: "var(--text-muted)" }}>
              {t("settings.languageCardDesc")}
            </p>
          </div>
        </div>
        <Tabs
          value={locale}
          onChange={(val) => setLocale(val as "bn" | "en")}
          ariaLabel={t("common.languageLabel")}
          options={[
            { id: "bn", label: "বাংলা (BN)", "data-testid": "settings-lang-bn" },
            { id: "en", label: "English (EN)", "data-testid": "settings-lang-en" },
          ]}
        />
        <p className="text-xs font-semibold" style={{ color: "var(--text-muted)" }}>
          {t("common.estimated")}: {formatNumber(1250)} BDT
        </p>
      </Card>

      {/* Theme Mode */}
      <Card variant="raised" className="space-y-4">
        <div className="flex items-start gap-3">
          <Palette className="h-5 w-5 shrink-0 mt-1" style={{ color: "var(--accent)" }} aria-hidden="true" />
          <div className="space-y-1">
            <h2 className="text-lg font-bold" style={{ color: "var(--text)" }}>
              {t("settings.themeCardTitle")}
            </h2>
            <p className="text-sm" style={{ color: "var(--text-muted)" }}>
              {t("settings.themeCardDesc")}
            </p>
          </div>
        </div>
        <Tabs
          value={themeMode}
          onChange={(val) => setThemeMode(val as ThemeMode)}
          ariaLabel={t("common.themeLabel")}
          options={[
            { id: "light", label: t("common.lightMode"), "data-testid": "settings-theme-light" },
            { id: "dark", label: t("common.darkMode"), "data-testid": "settings-theme-dark" },
            { id: "system", label: t("common.systemMode"), "data-testid": "settings-theme-system" },
          ]}
        />
      </Card>

      {/* Meal Times */}
      <Card variant="raised">
        <form onSubmit={handleSaveMealTimes} className="space-y-4">
          <div className="flex items-start gap-3">
            <Clock className="h-5 w-5 shrink-0 mt-1" style={{ color: "var(--accent)" }} aria-hidden="true" />
            <div className="space-y-1">
              <h2 className="text-lg font-bold" style={{ color: "var(--text)" }}>
                {t("settings.mealTimesTitle")}
              </h2>
              <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                {t("settings.mealTimesDesc")}
              </p>
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-3">
            <Input
              label={t("settings.breakfast")}
              type="time"
              value={breakfast}
              onChange={(e) => setBreakfast(e.target.value)}
            />
            <Input
              label={t("settings.lunch")}
              type="time"
              value={lunch}
              onChange={(e) => setLunch(e.target.value)}
            />
            <Input
              label={t("settings.dinner")}
              type="time"
              value={dinner}
              onChange={(e) => setDinner(e.target.value)}
            />
          </div>

          <Button type="submit" variant="primary" data-testid="settings-save-meals">
            {t("common.save")}
          </Button>
        </form>
      </Card>

      {/* Privacy & Notifications */}
      <Card variant="raised" className="space-y-4">
        <div className="flex items-center gap-2.5">
          <Bell className="h-5 w-5" style={{ color: "var(--accent)" }} aria-hidden="true" />
          <h2 className="text-lg font-bold" style={{ color: "var(--text)" }}>
            {t("settings.notificationsTitle")}
          </h2>
        </div>
        <Toggle
          checked={pushEnabled}
          onChange={(v) => setPushEnabled(v)}
          label={t("settings.pushLabel")}
          hint={t("settings.pushHint")}
          data-testid="toggle-push"
        />
        <Toggle
          checked={consent}
          onChange={(v) => setConsent(v)}
          label={t("settings.consentStatusLabel")}
          data-testid="toggle-consent"
        />
      </Card>

      {/* Demo Household Loader */}
      <Card variant="glass" className="space-y-3">
        <div className="flex items-center gap-2.5">
          <Sparkles className="h-5 w-5" style={{ color: "var(--saffron-text)" }} aria-hidden="true" />
          <h2 className="text-lg font-bold" style={{ color: "var(--text)" }}>
            {t("settings.demoTitle")}
          </h2>
        </div>
        <p className="text-sm" style={{ color: "var(--text-muted)" }}>
          {t("settings.demoDesc")}
        </p>
        <Button
          variant="neu"
          onClick={handleLoadDemo}
          disabled={loadingDemo}
          data-testid="settings-load-demo"
        >
          {loadingDemo ? t("common.loading") : t("settings.demoButton")}
        </Button>
      </Card>
    </div>
  );
}

