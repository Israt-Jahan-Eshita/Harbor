"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { KeyRound, ShieldAlert, Sparkles } from "lucide-react";
import { Button, Card, Input, Tabs, useToast } from "@/components/ui";
import { ApiError, harborApi } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useSession } from "@/lib/session";

export default function WelcomePage() {
  const router = useRouter();
  const { locale, t } = useI18n();
  const { setSession } = useSession();
  const { showToast } = useToast();

  const [tab, setTab] = useState("create");
  const [householdName, setHouseholdName] = useState("");
  const [pin, setPin] = useState("");
  const [budget, setBudget] = useState("14000");
  const [consentGiven, setConsentGiven] = useState(false);

  const [loginCode, setLoginCode] = useState("");
  const [loginPin, setLoginPin] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setErrorMsg(null);
    if (!consentGiven) {
      setErrorMsg(t("welcome.consentRequired"));
      return;
    }
    setSubmitting(true);
    try {
      const res = await harborApi.createHousehold(
        {
          name: householdName.trim(),
          pin: pin.trim(),
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

  return (
    <div className="mx-auto max-w-xl space-y-6 py-4">
      <div className="space-y-1">
        <h1 className="text-2xl sm:text-3xl font-extrabold" style={{ color: "var(--text)" }}>
          {t("welcome.title")}
        </h1>
        <p className="text-sm sm:text-base" style={{ color: "var(--text-muted)" }}>
          {t("welcome.subtitle")}
        </p>
      </div>

      <Tabs
        value={tab}
        onChange={(next) => {
          setTab(next);
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
              data-testid="input-household-name"
            />
            <Input
              label={t("welcome.pinLabel")}
              placeholder={t("welcome.pinPlaceholder")}
              type="password"
              inputMode="numeric"
              minLength={4}
              maxLength={8}
              value={pin}
              onChange={(e) => setPin(e.target.value)}
              required
              data-testid="input-household-pin"
            />
            <Input
              label={t("welcome.budgetLabel")}
              type="number"
              min={500}
              value={budget}
              onChange={(e) => setBudget(e.target.value)}
              data-testid="input-household-budget"
            />

            {/* Privacy & Consent Card (Guardrail #10) */}
            <Card variant="inset" className="space-y-3 p-4">
              <div className="flex items-start gap-2.5">
                <ShieldAlert
                  className="h-5 w-5 shrink-0 mt-0.5"
                  style={{ color: "var(--accent)" }}
                  aria-hidden="true"
                />
                <div className="space-y-1">
                  <h2 className="text-sm font-bold" style={{ color: "var(--text)" }}>
                    {t("welcome.consentTitle")}
                  </h2>
                  <p className="text-xs leading-relaxed" style={{ color: "var(--text-muted)" }}>
                    {t("welcome.consentBody")}
                  </p>
                </div>
              </div>
              <label className="flex min-h-[48px] items-center gap-3 cursor-pointer text-sm font-semibold">
                <input
                  type="checkbox"
                  checked={consentGiven}
                  onChange={(e) => setConsentGiven(e.target.checked)}
                  className="h-5 w-5 accent-[var(--accent)]"
                  data-testid="consent-checkbox"
                />
                <span style={{ color: "var(--text)" }}>{t("welcome.consentCheckbox")}</span>
              </label>
            </Card>

            {errorMsg && (
              <p className="text-sm font-semibold" style={{ color: "var(--danger)" }} role="alert">
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
              data-testid="input-login-code"
            />
            <Input
              label={t("welcome.pinLabel")}
              placeholder={t("welcome.pinPlaceholder")}
              type="password"
              inputMode="numeric"
              value={loginPin}
              onChange={(e) => setLoginPin(e.target.value)}
              required
              data-testid="input-login-pin"
            />

            {errorMsg && (
              <p className="text-sm font-semibold" style={{ color: "var(--danger)" }} role="alert">
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

      <Card variant="glass" className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex items-start gap-3">
          <Sparkles className="h-5 w-5 shrink-0 mt-0.5" style={{ color: "var(--saffron-text)" }} aria-hidden="true" />
          <div className="space-y-1 text-sm">
            <p className="font-bold" style={{ color: "var(--text)" }}>
              {t("welcome.demoTipTitle")}
            </p>
            <p style={{ color: "var(--text-muted)" }}>{t("welcome.demoTipBody")}</p>
          </div>
        </div>
        <Button
          variant="neu"
          onClick={async () => {
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
          }}
          disabled={submitting}
          data-testid="welcome-quick-demo"
          className="shrink-0"
        >
          {submitting ? t("common.loading") : t("welcome.demoQuickLoad")}
        </Button>
      </Card>
    </div>
  );
}

