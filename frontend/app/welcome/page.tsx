"use client";

import React, { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Eye, EyeOff, KeyRound, Lock, ShieldAlert, Sparkles } from "lucide-react";
import { Button, Card, Input, Tabs, useToast } from "@/components/ui";
import { ApiError, harborApi } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useSession } from "@/lib/session";

function WelcomeContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialTab = searchParams?.get("tab") === "login" ? "login" : "create";

  const { locale, t } = useI18n();
  const { setSession } = useSession();
  const { showToast } = useToast();

  const [tab, setTab] = useState<"create" | "login">(initialTab);
  const [householdName, setHouseholdName] = useState("");
  const [pin, setPin] = useState("");
  const [pinConfirm, setPinConfirm] = useState("");
  const [showPin, setShowPin] = useState(false);
  const [budget, setBudget] = useState("15000");
  const [consentGiven, setConsentGiven] = useState(false);

  const [loginCode, setLoginCode] = useState("");
  const [loginPin, setLoginPin] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setErrorMsg(null);
    const trimmedPin = pin.trim();
    if (trimmedPin.length < 4 || trimmedPin.length > 8 || trimmedPin !== pinConfirm.trim()) {
      setErrorMsg(t("welcome.pinMismatch"));
      return;
    }
    if (!consentGiven) {
      setErrorMsg(t("welcome.consentRequired"));
      return;
    }
    setSubmitting(true);
    try {
      const res = await harborApi.createHousehold(
        {
          name: householdName.trim(),
          pin: trimmedPin,
          consent_given: consentGiven,
          meal_times: { breakfast: "08:00", lunch: "13:30", dinner: "21:00" },
          monthly_budget_bdt: budget ? Number(budget) : null,
        },
        locale,
      );
      setSession({
        householdId: res.household_id,
        householdName: res.name,
        accessCode: res.access_code,
        token: res.token,
        consentGiven: res.consent_given,
        mealTimes: res.meal_times,
        monthlyBudgetBdt: res.monthly_budget_bdt,
      });
      showToast(`${t("welcome.createdSuccess")} (${res.access_code})`, "success");
      router.push("/members");
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.status === 404 || err.status === 0
            ? t("common.comingSoon")
            : err.message
          : t("common.errorUnexpected");
      setErrorMsg(msg);
      showToast(msg, "error");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setErrorMsg(null);
    setSubmitting(true);
    try {
      const res = await harborApi.loginHousehold(
        {
          access_code: loginCode.trim().toUpperCase(),
          pin: loginPin.trim(),
        },
        locale,
      );
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
      router.push("/dashboard");
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.status === 429
            ? err.message
            : err.status === 404 || err.status === 0
              ? t("common.comingSoon")
              : err.message
          : t("common.errorUnexpected");
      setErrorMsg(msg);
      showToast(msg, "error");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleLoadDemo() {
    setSubmitting(true);
    setErrorMsg(null);
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
      setErrorMsg(msg);
      showToast(msg, "error");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-md space-y-6 py-4 sm:py-8 harbor-reveal">
      <div className="space-y-1.5 text-center">
        <h1 className="font-display text-2xl sm:text-3xl font-bold" style={{ color: "var(--text)" }}>
          {t("welcome.title")}
        </h1>
        <p className="text-sm" style={{ color: "var(--text-muted)" }}>
          {t("welcome.subtitle")}
        </p>
      </div>

      <Tabs
        value={tab}
        onChange={(next) => {
          setTab(next as "create" | "login");
          setErrorMsg(null);
        }}
        ariaLabel={t("welcome.title")}
        options={[
          { id: "create", label: t("welcome.tabCreate"), "data-testid": "tab-create-household" },
          { id: "login", label: t("welcome.tabLogin"), "data-testid": "tab-login-household" },
        ]}
      />

      {tab === "create" ? (
        <Card variant="raised">
          <form onSubmit={handleCreate} className="space-y-4">
            <Input
              label={t("welcome.householdNameLabel")}
              placeholder={t("welcome.householdNamePlaceholder")}
              value={householdName}
              onChange={(e) => setHouseholdName(e.target.value)}
              required
              autoComplete="organization"
              data-testid="input-household-name"
            />

            <div className="space-y-3">
              <div className="relative">
                <Input
                  label={t("welcome.pinLabel")}
                  placeholder={t("welcome.pinPlaceholder")}
                  type={showPin ? "text" : "password"}
                  inputMode="numeric"
                  minLength={4}
                  maxLength={8}
                  value={pin}
                  onChange={(e) => setPin(e.target.value)}
                  required
                  autoComplete="new-password"
                  className="pr-11"
                  data-testid="input-household-pin"
                />
                <button
                  type="button"
                  onClick={() => setShowPin((v) => !v)}
                  aria-label={showPin ? t("welcome.hidePin") : t("welcome.showPin")}
                  className="absolute right-2 top-[29px] flex h-8 w-8 items-center justify-center rounded-[8px] cursor-pointer hover:bg-[var(--surface-elevated)]"
                  style={{ color: "var(--text-muted)" }}
                >
                  {showPin ? <EyeOff className="h-4 w-4" aria-hidden="true" /> : <Eye className="h-4 w-4" aria-hidden="true" />}
                </button>
              </div>

              <Input
                label={t("welcome.pinConfirmLabel")}
                placeholder={t("welcome.pinConfirmPlaceholder")}
                type={showPin ? "text" : "password"}
                inputMode="numeric"
                minLength={4}
                maxLength={8}
                value={pinConfirm}
                onChange={(e) => setPinConfirm(e.target.value)}
                required
                autoComplete="new-password"
                data-testid="input-household-pin-confirm"
              />
            </div>

            <Input
              label={t("welcome.budgetLabel")}
              type="number"
              min={500}
              value={budget}
              onChange={(e) => setBudget(e.target.value)}
              data-testid="input-household-budget"
            />

            {/* Privacy & Consent Card */}
            <div className="neu-inset p-3.5 space-y-2.5">
              <div className="flex items-start gap-2.5">
                <ShieldAlert
                  className="h-4 w-4 shrink-0 mt-0.5"
                  style={{ color: "var(--accent)" }}
                  aria-hidden="true"
                />
                <div className="space-y-1">
                  <p className="text-xs font-bold" style={{ color: "var(--text)" }}>
                    {t("welcome.consentTitle")}
                  </p>
                  <p className="text-[11px] leading-relaxed" style={{ color: "var(--text-muted)" }}>
                    {t("welcome.consentBody")}
                  </p>
                </div>
              </div>
              <label className="flex min-h-[40px] items-center gap-2.5 cursor-pointer text-xs font-semibold">
                <input
                  type="checkbox"
                  checked={consentGiven}
                  onChange={(e) => setConsentGiven(e.target.checked)}
                  className="h-4 w-4 shrink-0 accent-[var(--accent)]"
                  data-testid="consent-checkbox"
                />
                <span style={{ color: "var(--text)" }}>{t("welcome.consentCheckbox")}</span>
              </label>
            </div>

            {errorMsg && (
              <p className="text-xs font-semibold" style={{ color: "var(--danger)" }} role="alert">
                {errorMsg}
              </p>
            )}

            <Button
              type="submit"
              variant="primary"
              fullWidth
              disabled={submitting}
              data-testid="submit-create-household"
            >
              {submitting ? t("common.loading") : t("welcome.createSubmit")}
            </Button>
          </form>
        </Card>
      ) : (
        <Card variant="raised">
          <form onSubmit={handleLogin} className="space-y-4">
            <Input
              label={t("welcome.accessCodeLabel")}
              placeholder={t("welcome.accessCodePlaceholder")}
              value={loginCode}
              onChange={(e) => setLoginCode(e.target.value)}
              required
              autoComplete="username"
              data-testid="input-login-code"
            />
            <div className="relative">
              <Input
                label={t("welcome.pinLabel")}
                placeholder={t("welcome.pinPlaceholder")}
                type={showPin ? "text" : "password"}
                inputMode="numeric"
                value={loginPin}
                onChange={(e) => setLoginPin(e.target.value)}
                required
                autoComplete="current-password"
                className="pr-11"
                data-testid="input-login-pin"
              />
              <button
                type="button"
                onClick={() => setShowPin((v) => !v)}
                aria-label={showPin ? t("welcome.hidePin") : t("welcome.showPin")}
                className="absolute right-2 top-[29px] flex h-8 w-8 items-center justify-center rounded-[8px] cursor-pointer hover:bg-[var(--surface-elevated)]"
                style={{ color: "var(--text-muted)" }}
              >
                {showPin ? <EyeOff className="h-4 w-4" aria-hidden="true" /> : <Eye className="h-4 w-4" aria-hidden="true" />}
              </button>
            </div>

            <div className="flex items-start gap-2 text-[11px]" style={{ color: "var(--text-muted)" }}>
              <Lock className="h-3.5 w-3.5 shrink-0 mt-0.5" style={{ color: "var(--ok)" }} aria-hidden="true" />
              <span>{t("welcome.securityHint")}</span>
            </div>

            {errorMsg && (
              <p className="text-xs font-semibold" style={{ color: "var(--danger)" }} role="alert">
                {errorMsg}
              </p>
            )}

            <Button
              type="submit"
              variant="primary"
              fullWidth
              disabled={submitting}
              data-testid="submit-login-household"
            >
              <KeyRound className="h-4 w-4" aria-hidden="true" />
              <span>{submitting ? t("common.loading") : t("welcome.loginSubmit")}</span>
            </Button>
          </form>
        </Card>
      )}

      {/* Demo Household Access */}
      <Card variant="glass" className="space-y-3">
        <div className="flex items-start gap-2.5">
          <Sparkles className="h-4 w-4 shrink-0 mt-0.5" style={{ color: "var(--saffron-text)" }} aria-hidden="true" />
          <div className="space-y-1 text-xs">
            <p className="font-bold" style={{ color: "var(--text)" }}>
              {t("welcome.demoTipTitle")}
            </p>
            <p className="leading-relaxed" style={{ color: "var(--text-muted)" }}>
              {t("welcome.demoTipBody")}
            </p>
          </div>
        </div>
        <Button
          variant="neu"
          fullWidth
          onClick={handleLoadDemo}
          disabled={submitting}
          data-testid="welcome-quick-demo"
        >
          {submitting ? t("common.loading") : t("welcome.demoQuickLoad")}
        </Button>
      </Card>
    </div>
  );
}

export default function WelcomePage() {
  return (
    <Suspense fallback={<div className="mx-auto max-w-md py-12" />}>
      <WelcomeContent />
    </Suspense>
  );
}
