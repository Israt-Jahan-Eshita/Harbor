"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  Bell,
  Calendar,
  Copy,
  Pill,
  Utensils,
} from "lucide-react";
import { AuthGuardNotice } from "@/components/AuthGuardNotice";
import { Badge, Button, Card, Skeleton, useToast } from "@/components/ui";
import {
  ApiError,
  CaregiverDosesDashboardResponse,
  harborApi,
  HouseholdStateResponse,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useSession } from "@/lib/session";

function prettifyKey(key: string): string {
  return key
    .split("_")
    .map((w) => (w ? w[0].toUpperCase() + w.slice(1) : ""))
    .join(" ");
}

export default function DashboardPage() {
  const { locale, formatNumber, pickLocalized, t } = useI18n();
  const { session } = useSession();
  const { showToast } = useToast();

  const [state, setState] = useState<HouseholdStateResponse | null>(null);
  const [doses, setDoses] = useState<CaregiverDosesDashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!session) return;
    let cancelled = false;
    Promise.all([
      harborApi.getHouseholdState(session.householdId, session.token, locale),
      harborApi.getCaregiverDosesDashboard(session.token, locale),
    ])
      .then(([hhState, doseData]) => {
        if (!cancelled) {
          setState(hhState);
          setDoses(doseData);
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
  }, [session, locale, t]);

  if (!session) return <AuthGuardNotice />;

  const totalDoses = doses
    ? doses.summary.taken +
      doses.summary.taken_late +
      doses.summary.pending +
      doses.summary.missed +
      doses.summary.escalated
    : 0;
  const takenDoses = doses ? doses.summary.taken + doses.summary.taken_late : 0;
  const adherencePct = totalDoses > 0 ? Math.round((takenDoses / totalDoses) * 100) : 0;

  return (
    <div className="space-y-6 harbor-reveal">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div className="space-y-1">
          <h1 className="font-display text-2xl sm:text-3xl font-bold" style={{ color: "var(--text)" }}>
            {t("dashboard.title")}
          </h1>
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>
            {t("dashboard.subtitle")}
          </p>
        </div>

        <Link href="/menu" className="shrink-0">
          <Button variant="primary">
            <Utensils className="h-4 w-4" aria-hidden="true" />
            <span>{t("dashboard.actionMenu")}</span>
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </Button>
        </Link>
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
          <Skeleton className="h-32 rounded-[18px]" />
          <Skeleton className="h-44 rounded-[18px]" />
        </div>
      ) : state ? (
        <>
          {/* Household Status Header + 4-Metric Strip */}
          <Card variant="raised" className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-bold" style={{ color: "var(--text)" }}>
                  {state.name}
                </h2>
                <p className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                  {t("dashboard.accessCodeLabel")}: {state.access_code} · {state.for_date}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  variant="neu"
                  className="!min-h-[36px] !px-3 !py-1.5 !text-xs"
                  onClick={() => {
                    if (typeof window !== "undefined") {
                      void navigator.clipboard?.writeText(state.access_code);
                      showToast(t("common.copied"), "success");
                    }
                  }}
                >
                  <Copy className="h-3.5 w-3.5" aria-hidden="true" />
                  <span>{t("dashboard.copyCodeBtn")}</span>
                </Button>
                <Badge variant="SAFE_DIRECT" label={`${formatNumber(state.members.length)} ${t("nav.members")}`} />
              </div>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="neu-inset p-3 text-center">
                <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                  {t("dashboard.presentMembers")}
                </p>
                <p className="text-xl font-bold font-mono mt-0.5" style={{ color: "var(--text)" }}>
                  {formatNumber(state.present_member_count)}
                </p>
              </div>
              <div className="neu-inset p-3 text-center">
                <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                  {t("dashboard.guestsCount")}
                </p>
                <p className="text-xl font-bold font-mono mt-0.5" style={{ color: "var(--saffron-text)" }}>
                  {formatNumber(state.guest_count)}
                </p>
              </div>
              <div className="neu-inset p-3 text-center">
                <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                  {t("dashboard.stockItemsCount")}
                </p>
                <p className="text-xl font-bold font-mono mt-0.5" style={{ color: "var(--accent)" }}>
                  {formatNumber(state.stock_item_count)}
                </p>
              </div>
              <div className="neu-inset p-3 text-center">
                <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                  {t("reminders.summaryTaken")}
                </p>
                <p className="text-xl font-bold font-mono mt-0.5" style={{ color: "var(--ok)" }}>
                  {formatNumber(takenDoses)}
                </p>
              </div>
            </div>
          </Card>

          {/* Dose Adherence + Near-Expiry Watch */}
          <div className="grid gap-5 md:grid-cols-2">
            {doses && (
              <Card variant="raised" className="space-y-4">
                <div className="flex items-center justify-between gap-2">
                  <h2 className="text-base font-bold flex items-center gap-2" style={{ color: "var(--text)" }}>
                    <Pill className="h-4 w-4" style={{ color: "var(--accent)" }} aria-hidden="true" />
                    <span>{t("dashboard.dosesTitle")}</span>
                  </h2>
                  <Link href="/reminders" className="text-xs font-semibold underline" style={{ color: "var(--accent)" }}>
                    {t("dashboard.viewDetails")}
                  </Link>
                </div>

                {totalDoses > 0 && (
                  <div className="space-y-1.5">
                    <div className="flex justify-between text-xs">
                      <span style={{ color: "var(--text-muted)" }}>
                        {t("dashboard.dosesTakenOf", { taken: takenDoses, total: totalDoses })}
                      </span>
                      <span className="font-mono font-semibold" style={{ color: "var(--ok)" }}>
                        {formatNumber(adherencePct)}%
                      </span>
                    </div>
                    <div className="h-2 w-full rounded-full overflow-hidden bg-[var(--surface)]">
                      <div
                        className="h-full rounded-full transition-all duration-300"
                        style={{ width: `${adherencePct}%`, backgroundColor: "var(--ok)" }}
                      />
                    </div>
                  </div>
                )}

                <div className="grid grid-cols-3 gap-2 text-center text-xs">
                  <div className="neu-inset p-2.5">
                    <p style={{ color: "var(--text-muted)" }}>{t("reminders.summaryTaken")}</p>
                    <p className="text-base font-bold font-mono mt-0.5" style={{ color: "var(--ok)" }}>
                      {formatNumber(takenDoses)}
                    </p>
                  </div>
                  <div className="neu-inset p-2.5">
                    <p style={{ color: "var(--text-muted)" }}>{t("reminders.summaryPending")}</p>
                    <p className="text-base font-bold font-mono mt-0.5" style={{ color: "var(--text)" }}>
                      {formatNumber(doses.summary.pending)}
                    </p>
                  </div>
                  <div className="neu-inset p-2.5">
                    <p style={{ color: "var(--text-muted)" }}>{t("reminders.summaryMissed")}</p>
                    <p className="text-base font-bold font-mono mt-0.5" style={{ color: "var(--danger)" }}>
                      {formatNumber(doses.summary.missed + doses.summary.escalated)}
                    </p>
                  </div>
                </div>
              </Card>
            )}

            <Card variant="raised" className="space-y-3">
              <div className="flex items-center justify-between gap-2">
                <h2 className="text-base font-bold flex items-center gap-2" style={{ color: "var(--text)" }}>
                  <AlertTriangle className="h-4 w-4" style={{ color: "var(--saffron-text)" }} aria-hidden="true" />
                  <span>{t("dashboard.nearExpiryTitle")}</span>
                </h2>
                <Link href="/stock" className="text-xs font-semibold underline" style={{ color: "var(--accent)" }}>
                  {t("nav.stock")}
                </Link>
              </div>
              {state.near_expiry_items.length === 0 ? (
                <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                  {t("dashboard.noNearExpiry")}
                </p>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {state.near_expiry_items.map((it) => (
                    <Badge
                      key={it.ingredient_key}
                      variant="SAFE_WITH_SPLIT"
                      label={pickLocalized(it.name_bn, prettifyKey(it.ingredient_key))}
                    />
                  ))}
                </div>
              )}
            </Card>
          </div>

          {/* Today Events & Alerts */}
          <div className="grid gap-5 md:grid-cols-2">
            <Card variant="raised" className="space-y-3">
              <div className="flex items-center justify-between gap-2">
                <h2 className="text-base font-bold flex items-center gap-2" style={{ color: "var(--text)" }}>
                  <Calendar className="h-4 w-4" style={{ color: "var(--accent)" }} aria-hidden="true" />
                  <span>{t("dashboard.todayEventsTitle")}</span>
                </h2>
                <Link href="/log" className="text-xs font-semibold underline" style={{ color: "var(--accent)" }}>
                  {t("nav.log")}
                </Link>
              </div>
              {state.today_events.length === 0 ? (
                <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                  {t("dashboard.noTodayEvents")}
                </p>
              ) : (
                <div className="space-y-2">
                  {state.today_events.map((ev, i) => (
                    <div key={ev.id || i} className="neu-inset px-3 py-2 text-xs font-mono" style={{ color: "var(--text)" }}>
                      {ev.kind}
                    </div>
                  ))}
                </div>
              )}
            </Card>

            <Card variant="raised" className="space-y-3">
              <h2 className="text-base font-bold flex items-center gap-2" style={{ color: "var(--text)" }}>
                <Bell className="h-4 w-4" style={{ color: "var(--accent)" }} aria-hidden="true" />
                <span>{t("dashboard.alertsTitle")}</span>
              </h2>
              {state.recent_alerts.length === 0 ? (
                <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                  {t("dashboard.noAlerts")}
                </p>
              ) : (
                <div className="space-y-2">
                  {state.recent_alerts.slice(0, 5).map((al) => (
                    <div key={al.id} className="neu-inset flex justify-between px-3 py-2 text-xs">
                      <span className="font-semibold" style={{ color: "var(--text)" }}>
                        {al.kind}
                      </span>
                      <span className="font-mono" style={{ color: "var(--text-muted)" }}>
                        {new Date(al.sent_at).toLocaleTimeString()}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </div>
        </>
      ) : null}
    </div>
  );
}
