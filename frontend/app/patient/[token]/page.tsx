"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { BellRing, CheckCircle2, Clock, Languages, Moon, Sun } from "lucide-react";
import { Button, Card, PatientDomeButton, Skeleton, useToast } from "@/components/ui";
import { ApiError, harborApi, PatientDueResponse } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useTheme } from "@/lib/theme";

export default function PatientReminderPage() {
  const params = useParams<{ token: string }>();
  const token = params?.token || "";
  const { locale, toggleLocale, formatNumber, pickLocalized, t } = useI18n();
  const { resolvedTheme, toggleTheme } = useTheme();
  const { showToast } = useToast();

  const [data, setData] = useState<PatientDueResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [justConfirmed, setJustConfirmed] = useState(false);

  const loadDue = useCallback(async () => {
    if (!token) return;
    try {
      const res = await harborApi.getPatientDueReminders(token, locale);
      setData(res);
      setErrorMsg(null);
      if (res.has_due_dose) {
        setJustConfirmed(false);
      }
    } catch (err) {
      const msg =
        err instanceof ApiError && err.status === 401
          ? t("patient.invalidToken")
          : err instanceof ApiError
            ? err.message
            : t("common.errorUnexpected");
      setErrorMsg(msg);
    } finally {
      setLoading(false);
    }
  }, [token, locale, t]);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    harborApi
      .getPatientDueReminders(token, locale)
      .then((res) => {
        if (!cancelled) {
          setData(res);
          setErrorMsg(null);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          const msg =
            err instanceof ApiError && err.status === 401
              ? t("patient.invalidToken")
              : err instanceof ApiError
                ? err.message
                : t("common.errorUnexpected");
          setErrorMsg(msg);
          setLoading(false);
        }
      });

    const interval = setInterval(() => {
      if (!cancelled) {
        void loadDue();
      }
    }, 15000);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [token, locale, loadDue, t]);

  async function handleConfirmDose() {
    if (!data || data.due_doses.length === 0 || confirming) return;
    setConfirming(true);
    try {
      const target = data.due_doses[0];
      await harborApi.markPatientDoseTaken(target.dose_id, token, locale);
      setJustConfirmed(true);
      showToast(t("patient.domeConfirmed"), "success");
      await loadDue();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("common.errorUnexpected"), "error");
    } finally {
      setConfirming(false);
    }
  }

  const activeDue = data?.due_doses[0] || null;
  const nextUpcoming = data?.upcoming_doses[0] || null;

  return (
    <div
      className="min-h-screen flex flex-col justify-between px-4 py-6 sm:py-10 mx-auto max-w-lg"
      data-testid="patient-screen"
    >
      {/* Minimal Top Bar: Language + Theme only (zero nav chrome) */}
      <div className="flex items-center justify-end gap-2">
        <button
          type="button"
          onClick={toggleLocale}
          data-testid="patient-lang-toggle"
          aria-label={t("common.languageLabel")}
          className="neu-raised-sm inline-flex min-h-[48px] items-center gap-1.5 px-3.5 py-2 text-sm font-bold cursor-pointer"
          style={{ color: "var(--text)" }}
        >
          <Languages className="h-4 w-4" style={{ color: "var(--accent)" }} aria-hidden="true" />
          <span>{locale === "bn" ? "বাং → EN" : "EN → বাং"}</span>
        </button>
        <button
          type="button"
          onClick={toggleTheme}
          data-testid="patient-theme-toggle"
          aria-label={t("common.themeLabel")}
          className="neu-raised-sm inline-flex min-h-[48px] min-w-[48px] items-center justify-center px-3 py-2 cursor-pointer"
          style={{ color: "var(--text)" }}
        >
          {resolvedTheme === "dark" ? (
            <Sun className="h-4 w-4" style={{ color: "var(--saffron)" }} aria-hidden="true" />
          ) : (
            <Moon className="h-4 w-4" style={{ color: "var(--accent)" }} aria-hidden="true" />
          )}
        </button>
      </div>

      {/* Main High-Contrast Single-Purpose Body */}
      <div className="flex-1 flex flex-col items-center justify-center py-8 text-center space-y-8">
        {loading ? (
          <div className="w-full space-y-6">
            <Skeleton className="h-12 w-56 mx-auto rounded-[16px]" />
            <Skeleton className="h-56 w-56 mx-auto rounded-full" />
          </div>
        ) : errorMsg ? (
          <Card variant="raised" className="w-full space-y-4">
            <p className="text-lg font-bold" style={{ color: "var(--danger)" }}>
              {errorMsg}
            </p>
            <Button variant="primary" onClick={() => void loadDue()}>
              {t("common.retry")}
            </Button>
          </Card>
        ) : data ? (
          <>
            <div className="space-y-2">
              <p className="text-xl sm:text-2xl font-bold" style={{ color: "var(--text-muted)" }}>
                {t("patient.greeting", { name: data.member_name })}
              </p>
              {activeDue ? (
                <h1
                  className="text-3xl sm:text-4xl font-extrabold flex items-center justify-center gap-3"
                  style={{ color: "var(--text)" }}
                  data-testid="patient-due-heading"
                >
                  <BellRing className="h-8 w-8 shrink-0" style={{ color: "var(--accent)" }} aria-hidden="true" />
                  <span>{pickLocalized(activeDue.prompt_bn, activeDue.prompt_en)}</span>
                </h1>
              ) : (
                <div className="space-y-2" data-testid="patient-nodue-heading">
                  <CheckCircle2
                    className="h-12 w-12 mx-auto"
                    style={{ color: "var(--ok)" }}
                    aria-hidden="true"
                  />
                  <h1 className="text-2xl sm:text-3xl font-extrabold" style={{ color: "var(--text)" }}>
                    {t("patient.noDueTitle")}
                  </h1>
                  <p className="text-base" style={{ color: "var(--text-muted)" }}>
                    {t("patient.noDueDesc")}
                  </p>
                </div>
              )}
            </div>

            {activeDue && (
              <div className="py-2">
                <PatientDomeButton
                  label={confirming ? t("common.loading") : t("patient.domeIdle")}
                  confirmedLabel={t("patient.domeConfirmed")}
                  confirmed={justConfirmed}
                  disabled={confirming}
                  onClick={handleConfirmDose}
                  data-testid="patient-dome-button"
                />
              </div>
            )}

            <div className="w-full grid gap-3 sm:grid-cols-2">
              {nextUpcoming && (
                <Card variant="inset" className="p-4 text-center space-y-1">
                  <p className="text-xs font-bold flex items-center justify-center gap-1" style={{ color: "var(--text-muted)" }}>
                    <Clock className="h-3.5 w-3.5" aria-hidden="true" />
                    <span>{t("patient.upcomingLabel")}</span>
                  </p>
                  <p className="text-xl font-extrabold font-mono" style={{ color: "var(--text)" }}>
                    {new Date(nextUpcoming.due_at).toLocaleTimeString([], {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </p>
                </Card>
              )}
              <Card
                variant="inset"
                className={`p-4 text-center space-y-1 ${!nextUpcoming ? "sm:col-span-2" : ""}`}
              >
                <p className="text-xs font-bold" style={{ color: "var(--text-muted)" }}>
                  {t("patient.takenCountLabel")}
                </p>
                <p className="text-2xl font-extrabold font-mono" style={{ color: "var(--ok)" }}>
                  {formatNumber(data.taken_today_count)}
                </p>
              </Card>
            </div>
          </>
        ) : null}
      </div>

      <p className="text-center text-xs" style={{ color: "var(--text-muted)" }}>
        {t("patient.pollingHint")}
      </p>
    </div>
  );
}

