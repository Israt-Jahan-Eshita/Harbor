"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  Bell,
  Calendar,
  Mic,
  Package,
  Pill,
  ShoppingBasket,
  Users,
  Utensils,
} from "lucide-react";
import { AuthGuardNotice } from "@/components/AuthGuardNotice";
import { Badge, Card, Skeleton } from "@/components/ui";
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

  const quickActions = [
    { href: "/menu", label: t("dashboard.actionMenu"), icon: Utensils },
    { href: "/log", label: t("dashboard.actionLog"), icon: Mic },
    { href: "/members", label: t("dashboard.actionMembers"), icon: Users },
    { href: "/bazar", label: t("dashboard.actionBazar"), icon: ShoppingBasket },
    { href: "/stock", label: t("dashboard.actionStock"), icon: Package },
    { href: "/reminders", label: t("dashboard.actionReminders"), icon: Pill },
  ];

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl sm:text-3xl font-extrabold" style={{ color: "var(--text)" }}>
          {t("dashboard.title")}
        </h1>
        <p className="text-sm sm:text-base" style={{ color: "var(--text-muted)" }}>
          {t("dashboard.subtitle")}
        </p>
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
          <Skeleton className="h-32 rounded-[20px]" />
          <Skeleton className="h-44 rounded-[20px]" />
        </div>
      ) : state ? (
        <>
          {/* Hero KPI Strip */}
          <Card variant="glass" className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h2 className="text-xl font-extrabold" style={{ color: "var(--text)" }}>
                  {state.name}
                </h2>
                <p className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                  {t("dashboard.accessCodeLabel")}: {state.access_code} • {state.for_date}
                </p>
              </div>
              <Badge variant="SAFE_DIRECT" label={`${formatNumber(state.members.length)} ${t("nav.members")}`} />
            </div>

            <div className="grid grid-cols-3 gap-3">
              <div className="neu-inset p-3 text-center">
                <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                  {t("dashboard.presentMembers")}
                </p>
                <p className="text-2xl font-extrabold font-mono" style={{ color: "var(--text)" }}>
                  {formatNumber(state.present_member_count)}
                </p>
              </div>
              <div className="neu-inset p-3 text-center">
                <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                  {t("dashboard.guestsCount")}
                </p>
                <p className="text-2xl font-extrabold font-mono" style={{ color: "var(--saffron-text)" }}>
                  {formatNumber(state.guest_count)}
                </p>
              </div>
              <div className="neu-inset p-3 text-center">
                <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                  {t("dashboard.stockItemsCount")}
                </p>
                <p className="text-2xl font-extrabold font-mono" style={{ color: "var(--accent)" }}>
                  {formatNumber(state.stock_item_count)}
                </p>
              </div>
            </div>
          </Card>

          {/* Quick Actions */}
          <div className="space-y-3">
            <h2 className="text-lg font-extrabold" style={{ color: "var(--text)" }}>
              {t("dashboard.quickActionsTitle")}
            </h2>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {quickActions.map((act) => {
                const Icon = act.icon;
                return (
                  <Link
                    key={act.href}
                    href={act.href}
                    className="neu-raised flex min-h-[64px] items-center gap-3 p-4 font-bold transition-transform hover:-translate-y-0.5"
                    style={{ color: "var(--text)" }}
                  >
                    <span className="skeu-button flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px]">
                      <Icon className="h-5 w-5" aria-hidden="true" />
                    </span>
                    <span className="text-sm sm:text-base">{act.label}</span>
                  </Link>
                );
              })}
            </div>
          </div>

          {/* Dose Summary + Alerts + Near Expiry */}
          <div className="grid gap-5 md:grid-cols-2">
            {doses && (
              <Card variant="raised" className="space-y-3">
                <div className="flex items-center justify-between">
                  <h2 className="text-base font-extrabold flex items-center gap-2" style={{ color: "var(--text)" }}>
                    <Pill className="h-4 w-4" style={{ color: "var(--accent)" }} aria-hidden="true" />
                    <span>{t("dashboard.dosesTitle")}</span>
                  </h2>
                  <Link href="/reminders" className="text-xs font-bold underline" style={{ color: "var(--accent)" }}>
                    {t("nav.reminders")}
                  </Link>
                </div>
                <div className="grid grid-cols-3 gap-2 text-center text-xs">
                  <div className="neu-inset p-2.5">
                    <p style={{ color: "var(--text-muted)" }}>{t("reminders.summaryTaken")}</p>
                    <p className="text-lg font-extrabold font-mono" style={{ color: "var(--ok)" }}>
                      {formatNumber(doses.summary.taken + doses.summary.taken_late)}
                    </p>
                  </div>
                  <div className="neu-inset p-2.5">
                    <p style={{ color: "var(--text-muted)" }}>{t("reminders.summaryPending")}</p>
                    <p className="text-lg font-extrabold font-mono" style={{ color: "var(--text)" }}>
                      {formatNumber(doses.summary.pending)}
                    </p>
                  </div>
                  <div className="neu-inset p-2.5">
                    <p style={{ color: "var(--text-muted)" }}>{t("reminders.summaryMissed")}</p>
                    <p className="text-lg font-extrabold font-mono" style={{ color: "var(--danger)" }}>
                      {formatNumber(doses.summary.missed + doses.summary.escalated)}
                    </p>
                  </div>
                </div>
              </Card>
            )}

            <Card variant="raised" className="space-y-3">
              <div className="flex items-center justify-between">
                <h2 className="text-base font-extrabold flex items-center gap-2" style={{ color: "var(--text)" }}>
                  <AlertTriangle className="h-4 w-4" style={{ color: "var(--saffron-text)" }} aria-hidden="true" />
                  <span>{t("dashboard.nearExpiryTitle")}</span>
                </h2>
                <Link href="/stock" className="text-xs font-bold underline" style={{ color: "var(--accent)" }}>
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

          <div className="grid gap-5 md:grid-cols-2">
            <Card variant="raised" className="space-y-3">
              <h2 className="text-base font-extrabold flex items-center gap-2" style={{ color: "var(--text)" }}>
                <Calendar className="h-4 w-4" style={{ color: "var(--accent)" }} aria-hidden="true" />
                <span>{t("dashboard.todayEventsTitle")}</span>
              </h2>
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
              <h2 className="text-base font-extrabold flex items-center gap-2" style={{ color: "var(--text)" }}>
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
                      <span className="font-bold" style={{ color: "var(--text)" }}>
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

