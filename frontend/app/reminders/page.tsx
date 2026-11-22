"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { Bell, Copy, ExternalLink, Pill, RefreshCw } from "lucide-react";
import { AuthGuardNotice } from "@/components/AuthGuardNotice";
import { Badge, Button, Card, Input, Skeleton, useToast } from "@/components/ui";
import { ApiError, CaregiverDosesDashboardResponse, harborApi } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useSession } from "@/lib/session";

export default function RemindersDashboardPage() {
  const { locale, formatNumber, t } = useI18n();
  const { session } = useSession();
  const { showToast } = useToast();

  const [forDate, setForDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [data, setData] = useState<CaregiverDosesDashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!session) return;
    let cancelled = false;
    harborApi
      .getCaregiverDosesDashboard(session.token, locale, forDate)
      .then((res) => {
        if (!cancelled) {
          setData(res);
          setErrorMsg(null);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setErrorMsg(err instanceof ApiError ? err.message : t("common.errorUnexpected"));
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [session, locale, forDate, t]);

  async function handleRefresh() {
    if (!session) return;
    setLoading(true);
    try {
      const res = await harborApi.getCaregiverDosesDashboard(session.token, locale, forDate);
      setData(res);
      setErrorMsg(null);
    } catch (err) {
      setErrorMsg(err instanceof ApiError ? err.message : t("common.errorUnexpected"));
    } finally {
      setLoading(false);
    }
  }

  function statusBadgeVariant(status: string) {
    if (status === "taken") return "SAFE_DIRECT" as const;
    if (status === "taken_late" || status === "pending") return "SAFE_WITH_SPLIT" as const;
    return "BLOCKED" as const;
  }

  if (!session) return <AuthGuardNotice />;

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-2xl sm:text-3xl font-extrabold" style={{ color: "var(--text)" }}>
            {t("reminders.title")}
          </h1>
          <p className="text-sm sm:text-base" style={{ color: "var(--text-muted)" }}>
            {t("reminders.subtitle")}
          </p>
        </div>
        <div className="flex items-end gap-2">
          <Input
            label={t("menu.dateLabel")}
            type="date"
            value={forDate}
            onChange={(e) => setForDate(e.target.value)}
          />
          <Button variant="neu" onClick={handleRefresh} aria-label={t("common.refresh")}>
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>
      </div>

      {errorMsg && (
        <Card variant="glass">
          <p className="text-sm font-semibold" style={{ color: "var(--danger)" }}>
            {errorMsg}
          </p>
        </Card>
      )}

      {loading ? (
        <div className="space-y-4">
          <Skeleton className="h-28 rounded-[20px]" />
          <Skeleton className="h-48 rounded-[20px]" />
        </div>
      ) : data ? (
        <>
          {/* Summary Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
            {(
              [
                ["taken", t("reminders.summaryTaken"), "var(--ok)"],
                ["taken_late", t("reminders.summaryLate"), "var(--saffron-text)"],
                ["pending", t("reminders.summaryPending"), "var(--text)"],
                ["missed", t("reminders.summaryMissed"), "var(--danger)"],
                ["escalated", t("reminders.summaryEscalated"), "var(--danger)"],
              ] as const
            ).map(([key, label, color]) => (
              <Card key={key} variant="raised" className="p-4 text-center space-y-1">
                <p className="text-xs font-semibold" style={{ color: "var(--text-muted)" }}>
                  {label}
                </p>
                <p className="text-2xl font-extrabold font-mono" style={{ color }}>
                  {formatNumber(data.summary[key] ?? 0)}
                </p>
              </Card>
            ))}
          </div>

          {/* Patient Cards */}
          {data.patients.length === 0 ? (
            <Card variant="inset" className="py-8 text-center">
              <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                {t("reminders.noPatients")}
              </p>
            </Card>
          ) : (
            <div className="space-y-4">
              {data.patients.map((pt) => (
                <Card key={pt.member_id} variant="raised" className="space-y-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <h2 className="text-lg font-extrabold" style={{ color: "var(--text)" }}>
                        {pt.name}
                      </h2>
                      <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                        {t(`members.roles.${pt.role}`)}
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Button
                        variant="ghost"
                        className="!min-h-[40px] !px-3 !py-1.5 !text-xs"
                        onClick={() => {
                          if (typeof window !== "undefined") {
                            const url = `${window.location.origin}/patient/${pt.patient_token}`;
                            void navigator.clipboard.writeText(url);
                            showToast(t("common.copied"), "success");
                          }
                        }}
                      >
                        <Copy className="h-3.5 w-3.5" aria-hidden="true" />
                        <span>{t("reminders.copyPatientBtn")}</span>
                      </Button>
                      <Link
                        href={`/patient/${pt.patient_token}`}
                        className="skeu-button inline-flex min-h-[40px] items-center gap-1.5 px-3.5 py-1.5 text-xs font-bold"
                      >
                        <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                        <span>{t("reminders.openPatientBtn")}</span>
                      </Link>
                    </div>
                  </div>

                  <div className="space-y-2">
                    {pt.doses.map((d) => (
                      <div
                        key={d.dose_id}
                        className="neu-inset flex flex-wrap items-center justify-between gap-2 px-3.5 py-2.5 text-sm"
                      >
                        <div className="flex items-center gap-2">
                          <Pill className="h-4 w-4 shrink-0" style={{ color: "var(--accent)" }} aria-hidden="true" />
                          <span className="font-bold" style={{ color: "var(--text)" }}>
                            {d.medicine_name}
                          </span>
                          <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                            ({t(`memberDetail.timings.${d.timing}`)})
                          </span>
                        </div>
                        <div className="flex items-center gap-3">
                          <span className="font-mono text-xs" style={{ color: "var(--text-muted)" }}>
                            {new Date(d.due_at).toLocaleTimeString([], {
                              hour: "2-digit",
                              minute: "2-digit",
                            })}
                          </span>
                          <Badge
                            variant={statusBadgeVariant(d.status)}
                            label={t(`reminders.doseStatuses.${d.status}`)}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                </Card>
              ))}
            </div>
          )}

          {/* Escalation Alerts */}
          <Card variant="glass" className="space-y-3">
            <div className="flex items-center gap-2">
              <Bell className="h-5 w-5" style={{ color: "var(--accent)" }} aria-hidden="true" />
              <h2 className="text-base font-extrabold" style={{ color: "var(--text)" }}>
                {t("reminders.alertsTitle")}
              </h2>
            </div>
            {data.alerts.length === 0 ? (
              <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                {t("reminders.noAlerts")}
              </p>
            ) : (
              <div className="space-y-2">
                {data.alerts.map((al) => (
                  <div key={al.id} className="neu-inset flex flex-wrap justify-between gap-2 px-3.5 py-2 text-xs">
                    <span className="font-bold" style={{ color: "var(--text)" }}>
                      {al.kind} ({al.channel})
                    </span>
                    <span className="font-mono" style={{ color: "var(--text-muted)" }}>
                      {new Date(al.sent_at).toLocaleString()}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </>
      ) : null}
    </div>
  );
}

