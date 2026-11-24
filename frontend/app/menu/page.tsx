"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import {
  CalendarDays,
  ChefHat,
  ChevronDown,
  ChevronUp,
  GitFork,
  Lock,
  Pill,
  ShieldAlert,
  ShoppingBasket,
  Sparkles,
  Unlock,
  Users,
  Utensils,
} from "lucide-react";
import { AuthGuardNotice } from "@/components/AuthGuardNotice";
import { Badge, Button, Card, Input, Sheet, Skeleton, Tabs, Toggle, useToast } from "@/components/ui";
import {
  ApiError,
  harborApi,
  IngredientConflict,
  MealSlot,
  MemberRecord,
  MenuResponse,
  MenuTopDish,
  WeeklyPlanResponse,
  WeeklyPlanSlot,
} from "@/lib/api";
import { getDhakaTodayISO } from "@/lib/date";
import { useI18n } from "@/lib/i18n";
import { useSession } from "@/lib/session";

const DEFAULT_ALLERGEN_KEYS: string[] = [
  "prawn_shellfish",
  "fish",
  "egg",
  "milk",
  "peanut",
  "tree_nut",
  "wheat_gluten",
  "soy",
  "sesame",
];

function conflictBadgeVariant(status: string) {
  if (status === "SAFE_DIRECT") return "SAFE_DIRECT" as const;
  if (status === "SAFE_WITH_SPLIT" || status === "CONVERGENT_SPLIT") return "SAFE_WITH_SPLIT" as const;
  if (status === "UNVERIFIED" || status === "UNVERIFIED_FAIL_CLOSED") return "UNVERIFIED" as const;
  return "BLOCKED" as const;
}

export default function MenuPage() {
  const { locale, formatNumber, pickLocalized, t } = useI18n();
  const { session } = useSession();
  const { showToast } = useToast();

  const [viewMode, setViewMode] = useState<"daily" | "weekly">("daily");

  // Daily menu state
  const [forDate, setForDate] = useState(() => getDhakaTodayISO());
  const [meal, setMeal] = useState<MealSlot>("dinner");
  const [useAgent, setUseAgent] = useState(false);
  const [allergenKeys, setAllergenKeys] = useState<string[]>(DEFAULT_ALLERGEN_KEYS);
  const [menuData, setMenuData] = useState<MenuResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const [expandedScores, setExpandedScores] = useState<Record<string, boolean>>({});
  const [excludedOpen, setExcludedOpen] = useState(false);
  const [reviewOpen, setReviewOpen] = useState(false);

  const [members, setMembers] = useState<MemberRecord[]>([]);
  const [guestCount, setGuestCount] = useState("0");
  const [guestRestrictions, setGuestRestrictions] = useState<string[]>([]);
  const [awayMemberIds, setAwayMemberIds] = useState<string[]>([]);

  // Whole-week planner state
  const [weekStartDate, setWeekStartDate] = useState(() => getDhakaTodayISO());
  const [useWeeklyAiSummary, setUseWeeklyAiSummary] = useState(false);
  const [weeklyPlan, setWeeklyPlan] = useState<WeeklyPlanResponse | null>(null);
  const [weeklyLoading, setWeeklyLoading] = useState(false);
  const [weeklyError, setWeeklyError] = useState<string | null>(null);
  const [swappingSlotKey, setSwappingSlotKey] = useState<string | null>(null);
  const [bazarConvertedId, setBazarConvertedId] = useState<string | null>(null);

  useEffect(() => {
    if (!session) return;
    let cancelled = false;
    Promise.resolve(harborApi.listMembers(session.token, locale))
      .then((res) => {
        if (!cancelled && res?.members) setMembers(res.members);
      })
      .catch(() => {
        /* members list optional until review opens */
      });
    Promise.resolve(harborApi.getEngineCatalog(session.token, locale))
      .then((cat) => {
        if (!cancelled && cat?.allergens?.length) {
          setAllergenKeys(cat.allergens);
        }
      })
      .catch(() => {
        /* fallback allergen list stays active */
      });
    return () => {
      cancelled = true;
    };
  }, [session, locale]);

  useEffect(() => {
    if (!session || viewMode !== "weekly") return;
    let cancelled = false;
    Promise.resolve(harborApi.getLatestWeeklyPlan(session.token, locale))
      .then((res) => {
        if (!cancelled && res?.plan) {
          setWeeklyPlan(res.plan);
        }
      })
      .catch(() => {
        /* no prior weekly plan yet */
      });
    return () => {
      cancelled = true;
    };
  }, [session, locale, viewMode]);

  async function runSuggest(targetDate: string, targetMeal: MealSlot, targetUseAgent: boolean) {
    if (!session) return;
    setLoading(true);
    setErrorMsg(null);
    try {
      const res = await harborApi.suggestMenu(
        { for_date: targetDate, meal: targetMeal, use_agent: targetUseAgent },
        session.token,
        locale,
      );
      setMenuData(res);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : t("common.errorUnexpected");
      setErrorMsg(msg);
      showToast(msg, "error");
    } finally {
      setLoading(false);
    }
  }

  async function handleSuggest() {
    await runSuggest(forDate, meal, useAgent);
  }

  async function handleApplyReview(e: React.FormEvent) {
    e.preventDefault();
    if (!session) return;
    setLoading(true);
    setErrorMsg(null);
    try {
      const res = await harborApi.reviewMenu(
        {
          for_date: forDate,
          meal,
          guest_count: Math.max(0, Number(guestCount) || 0),
          guest_restrictions: guestRestrictions,
          away_member_ids: awayMemberIds,
          use_agent: useAgent,
        },
        session.token,
        locale,
      );
      setMenuData(res);
      setReviewOpen(false);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : t("common.errorUnexpected");
      setErrorMsg(msg);
      showToast(msg, "error");
    } finally {
      setLoading(false);
    }
  }

  async function handleMarkCooked(dish: MenuTopDish) {
    if (!session) return;
    try {
      await harborApi.markMenuCooked(
        { recipe_id: dish.recipe_id, servings: dish.scaled_servings, for_date: forDate, meal },
        session.token,
        locale,
      );
      showToast(t("menu.cookedToast"), "success");
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("common.errorUnexpected"), "error");
    }
  }

  async function handleGenerateWeeklyPlan() {
    if (!session) return;
    setWeeklyLoading(true);
    setWeeklyError(null);
    setBazarConvertedId(null);
    try {
      const res = await harborApi.generateWeeklyPlan(
        { start_date: weekStartDate, days: 7, use_ai_summary: useWeeklyAiSummary },
        session.token,
        locale,
      );
      setWeeklyPlan(res);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : t("common.errorUnexpected");
      setWeeklyError(msg);
      showToast(msg, "error");
    } finally {
      setWeeklyLoading(false);
    }
  }

  async function handleSwapOrLockSlot(
    slotDate: string,
    slotMeal: MealSlot,
    nextRecipeKey?: string,
    nextLocked?: boolean,
  ) {
    if (!session || !weeklyPlan) return;
    const key = `${slotDate}:${slotMeal}`;
    setSwappingSlotKey(key);
    try {
      const updated = await harborApi.updateWeeklyPlanSlot(
        weeklyPlan.plan_id,
        {
          for_date: slotDate,
          meal: slotMeal,
          ...(nextRecipeKey !== undefined ? { recipe_key: nextRecipeKey } : {}),
          ...(nextLocked !== undefined ? { locked: nextLocked } : {}),
        },
        session.token,
        locale,
      );
      setWeeklyPlan(updated);
      if (nextRecipeKey !== undefined) {
        showToast(t("menu.weekly.swapSuccess"), "success");
      }
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("common.errorUnexpected"), "error");
    } finally {
      setSwappingSlotKey(null);
    }
  }

  async function handleConvertWeeklyToBazar() {
    if (!session || !weeklyPlan) return;
    setWeeklyLoading(true);
    try {
      const res = await harborApi.convertWeeklyPlanToBazar(
        weeklyPlan.plan_id,
        session.token,
        locale,
      );
      setBazarConvertedId(res.bazar_list_id);
      showToast(
        t("menu.weekly.toBazarSuccess", {
          count: formatNumber(res.items_count),
          bdt: formatNumber(res.est_total_bdt),
        }),
        "success",
      );
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("common.errorUnexpected"), "error");
    } finally {
      setWeeklyLoading(false);
    }
  }

  function renderConflictCard(conf: IngredientConflict) {
    return (
      <div
        key={conf.ingredient_key}
        className="neu-inset p-3.5 space-y-2"
        data-testid={`conflict-card-${conf.ingredient_key}`}
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <ShieldAlert className="h-4 w-4 shrink-0" style={{ color: "var(--saffron-text)" }} aria-hidden="true" />
            <span className="font-extrabold text-sm" style={{ color: "var(--text)" }}>
              {pickLocalized(conf.ingredient_name_bn, conf.ingredient_name_en)}
            </span>
          </div>
          <Badge variant={conflictBadgeVariant(conf.winning_status)} ruleId={conf.winning_reasons[0]} />
        </div>
        <p className="text-xs leading-relaxed" style={{ color: "var(--text)" }}>
          {pickLocalized(conf.explanation_bn, conf.explanation_en)}
        </p>
        <div className="flex flex-wrap gap-1.5">
          {conf.positions.map((pos) => (
            <span
              key={pos.member_id}
              className="rounded-full border border-[var(--border-subtle)] px-2.5 py-0.5 text-[11px] font-semibold"
              style={{ color: "var(--text-muted)" }}
            >
              {pos.member_name}: {pos.reasons.length ? pos.reasons.join(", ") : t("status.SAFE_DIRECT")}
            </span>
          ))}
        </div>
        {conf.safe_substitutes && conf.safe_substitutes.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5 pt-1 text-[11px]">
            <span className="font-bold" style={{ color: "var(--text)" }}>
              {t("bazar.substituteBadge")}:
            </span>
            {conf.safe_substitutes.map((sub) => (
              <span
                key={sub.ingredient_key}
                className="rounded-full px-2 py-0.5 font-semibold"
                style={{ backgroundColor: "var(--surface-elevated)", color: "var(--accent)" }}
              >
                {pickLocalized(sub.name_bn, sub.name_en)}
              </span>
            ))}
          </div>
        )}
      </div>
    );
  }

  function renderWeeklySlotCard(dayDate: string, slot: WeeklyPlanSlot) {
    const slotKey = `${dayDate}:${slot.meal}`;
    const busy = swappingSlotKey === slotKey;
    const isDeadlock = slot.status === "DEADLOCK_NO_SAFE_DISH";

    return (
      <div key={slotKey} className="neu-inset p-3.5 space-y-2.5 flex flex-col justify-between">
        <div className="space-y-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-xs font-extrabold uppercase tracking-wide" style={{ color: "var(--accent)" }}>
              {t(`memberDetail.slots.${slot.meal}`)}
            </span>
            <div className="flex flex-wrap items-center gap-1.5">
              {slot.locked && (
                <Badge variant="INFO" label={t("menu.weekly.lockedBadge")} />
              )}
              {isDeadlock ? (
                <Badge variant="BLOCKED" label={t("menu.weekly.deadlockBadge")} />
              ) : (
                <Badge
                  variant={slot.status === "SAFE_WITH_SPLIT" ? "SAFE_WITH_SPLIT" : "SAFE_DIRECT"}
                />
              )}
            </div>
          </div>

          <h4 className="text-base font-extrabold leading-snug" style={{ color: "var(--text)" }}>
            {pickLocalized(slot.name_bn, slot.name_en)}
          </h4>

          {slot.lock_overridden && slot.lock_override_reason_bn && (
            <p className="text-[11px] font-semibold" style={{ color: "var(--saffron-text)" }}>
              {slot.lock_override_reason_bn}
            </p>
          )}

          {slot.status === "SAFE_WITH_SPLIT" && slot.split_step_bn && (
            <div className="rounded-xl border border-[var(--saffron-text)]/35 p-2 text-[11px] space-y-0.5">
              <div className="flex items-center gap-1 font-bold" style={{ color: "var(--saffron-text)" }}>
                <GitFork className="h-3 w-3 shrink-0" aria-hidden="true" />
                <span>{slot.split_step_bn}</span>
              </div>
              {slot.split_for.length > 0 && (
                <p style={{ color: "var(--text-muted)" }}>
                  {t("menu.splitForMembers", { names: slot.split_for.join(", ") })}
                </p>
              )}
            </div>
          )}

          {isDeadlock && slot.explanation_bn && (
            <p className="text-xs leading-relaxed" style={{ color: "var(--danger)" }}>
              {pickLocalized(slot.explanation_bn, slot.explanation_en || slot.explanation_bn)}
            </p>
          )}

          {slot.linked_medicines.length > 0 && (
            <div className="space-y-1 pt-1">
              <p className="text-[11px] font-bold flex items-center gap-1" style={{ color: "var(--text-muted)" }}>
                <Pill className="h-3 w-3 shrink-0" style={{ color: "var(--accent)" }} aria-hidden="true" />
                <span>{t("menu.weekly.linkedMedsLabel")}:</span>
              </p>
              <div className="flex flex-wrap gap-1">
                {slot.linked_medicines.map((med, idx) => (
                  <span
                    key={`${med.member_id}-${idx}`}
                    className="rounded-full border border-[var(--border-subtle)] px-2 py-0.5 text-[10px] font-semibold"
                    style={{ color: "var(--text)" }}
                  >
                    {med.member_name}: {med.medicine_name} ({t(`memberDetail.timings.${med.timing}`)})
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        {!isDeadlock && slot.recipe_key && (
          <div className="flex items-center gap-2 pt-2 border-t border-[var(--border-subtle)]">
            <select
              aria-label={t("menu.weekly.swapLabel")}
              value={slot.recipe_key}
              disabled={busy || slot.alternatives.length === 0}
              onChange={(e) => {
                if (e.target.value && e.target.value !== slot.recipe_key) {
                  void handleSwapOrLockSlot(dayDate, slot.meal, e.target.value);
                }
              }}
              className="neu-inset flex-1 min-h-[36px] px-2 py-1 text-xs font-medium"
              style={{ color: "var(--text)" }}
              data-testid={`weekly-swap-${dayDate}-${slot.meal}`}
            >
              <option value={slot.recipe_key}>
                {pickLocalized(slot.name_bn, slot.name_en)}
              </option>
              {slot.alternatives.map((alt) => (
                <option key={alt.recipe_key} value={alt.recipe_key}>
                  ↔ {pickLocalized(alt.name_bn, alt.name_en)}
                </option>
              ))}
            </select>

            <button
              type="button"
              disabled={busy}
              onClick={() => void handleSwapOrLockSlot(dayDate, slot.meal, undefined, !slot.locked)}
              className={`min-h-[36px] min-w-[36px] inline-flex items-center justify-center rounded-xl px-2.5 text-xs font-bold cursor-pointer ${
                slot.locked ? "skeu-button" : "neu-raised-sm"
              }`}
              title={slot.locked ? t("menu.weekly.unlockBtn") : t("menu.weekly.lockBtn")}
              data-testid={`weekly-lock-${dayDate}-${slot.meal}`}
            >
              {slot.locked ? (
                <Lock className="h-3.5 w-3.5" aria-hidden="true" />
              ) : (
                <Unlock className="h-3.5 w-3.5" aria-hidden="true" />
              )}
            </button>
          </div>
        )}
      </div>
    );
  }

  if (!session) return <AuthGuardNotice />;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-2xl sm:text-3xl font-extrabold" style={{ color: "var(--text)" }}>
            {viewMode === "weekly" ? t("menu.weekly.title") : t("menu.title")}
          </h1>
          <p className="text-sm sm:text-base" style={{ color: "var(--text-muted)" }}>
            {viewMode === "weekly" ? t("menu.weekly.subtitle") : t("menu.subtitle")}
          </p>
        </div>

        <Tabs
          value={viewMode}
          onChange={(v) => setViewMode(v as "daily" | "weekly")}
          ariaLabel={t("menu.mealLabel")}
          options={[
            { id: "daily", label: t("menu.tabDaily") },
            { id: "weekly", label: t("menu.tabWeekly") },
          ]}
        />
      </div>

      {viewMode === "daily" ? (
        <>
          {/* Daily Controls Card */}
          <Card variant="raised" className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <Input
                label={t("menu.dateLabel")}
                type="date"
                value={forDate}
                onChange={(e) => {
                  const nextDate = e.target.value;
                  setForDate(nextDate);
                  if (menuData && !useAgent && nextDate) {
                    void runSuggest(nextDate, meal, false);
                  }
                }}
                data-testid="menu-date-input"
              />
              <div className="space-y-1.5">
                <span className="block text-sm font-semibold" style={{ color: "var(--text)" }}>
                  {t("menu.mealLabel")}
                </span>
                <Tabs
                  value={meal}
                  onChange={(m) => {
                    const nextMeal = m as MealSlot;
                    setMeal(nextMeal);
                    if (menuData && !useAgent) {
                      void runSuggest(forDate, nextMeal, false);
                    }
                  }}
                  ariaLabel={t("menu.mealLabel")}
                  options={[
                    { id: "breakfast", label: t("memberDetail.slots.breakfast") },
                    { id: "lunch", label: t("memberDetail.slots.lunch") },
                    { id: "dinner", label: t("memberDetail.slots.dinner") },
                  ]}
                />
              </div>
            </div>

            <Toggle
              checked={useAgent}
              onChange={setUseAgent}
              label={t("menu.useAgentLabel")}
              data-testid="menu-toggle-agent"
            />

            <div className="flex flex-wrap gap-3">
              <Button
                variant="primary"
                onClick={handleSuggest}
                disabled={loading}
                data-testid="menu-suggest-btn"
              >
                <Utensils className="h-4 w-4" aria-hidden="true" />
                <span>{loading ? t("common.loading") : t("menu.ctaSuggest")}</span>
              </Button>
              <Button
                variant="neu"
                onClick={() => setReviewOpen(true)}
                data-testid="menu-review-btn"
              >
                <Users className="h-4 w-4" style={{ color: "var(--accent)" }} aria-hidden="true" />
                <span>{t("menu.ctaReviewGuests")}</span>
              </Button>
            </div>
          </Card>

          {errorMsg && (
            <Card variant="glass">
              <p className="text-sm font-semibold" style={{ color: "var(--danger)" }}>
                {errorMsg}
              </p>
            </Card>
          )}

          {loading && !menuData && (
            <div className="space-y-4">
              <Skeleton className="h-48 rounded-[20px]" />
              <Skeleton className="h-48 rounded-[20px]" />
            </div>
          )}

          {!loading && !menuData && (
            <Card variant="inset" className="text-center py-8 space-y-2">
              <ChefHat className="h-9 w-9 mx-auto" style={{ color: "var(--accent)" }} aria-hidden="true" />
              <p className="text-sm sm:text-base font-medium" style={{ color: "var(--text-muted)" }}>
                {t("menu.emptyState")}
              </p>
            </Card>
          )}

          {menuData && (
            <div className="space-y-6" data-testid="menu-results">
              {/* Context Strip */}
              <Card variant="glass" className="flex flex-wrap items-center justify-between gap-3">
                <div className="space-y-1 text-sm">
                  <p className="font-bold" style={{ color: "var(--text)" }}>
                    {t("menu.presentLabel")}: {menuData.present_member_names.join(", ") || t("common.none")}
                    {menuData.guest_count > 0 &&
                      ` (+${formatNumber(menuData.guest_count)} ${t("menu.guestsLabel")})`}
                  </p>
                  <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                    {t("menu.candidatesLabel")}: {formatNumber(menuData.total_candidates)}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {menuData.validated && (
                    <Badge variant="SAFE_DIRECT" label={t("menu.validatedBadge")} />
                  )}
                  {menuData.used_template && (
                    <Badge variant="INFO" label={t("menu.templateBadge")} />
                  )}
                  {menuData.used_fallback && (
                    <Badge variant="ESTIMATED" label={t("menu.fallbackBadge")} />
                  )}
                </div>
              </Card>

              {/* Conflict Summary Banner if conflicts resolved */}
              {menuData.conflict_summary && menuData.conflict_summary.conflicted_ingredients.length > 0 && (
                <Card variant="glass" className="space-y-3" data-testid="daily-conflict-summary">
                  <h2 className="text-base font-extrabold" style={{ color: "var(--text)" }}>
                    {t("menu.conflictBannerTitle", {
                      count: formatNumber(menuData.conflict_summary.conflicted_ingredients.length),
                    })}
                  </h2>
                  {menuData.conflict_summary.zero_safe_deadlock && menuData.conflict_summary.deadlock_recovery_bn && (
                    <div className="neu-inset p-3 text-sm font-bold" style={{ color: "var(--danger)" }}>
                      {pickLocalized(
                        menuData.conflict_summary.deadlock_recovery_bn,
                        menuData.conflict_summary.deadlock_recovery_en || menuData.conflict_summary.deadlock_recovery_bn,
                      )}
                    </div>
                  )}
                  <div className="grid gap-3 md:grid-cols-2">
                    {menuData.conflict_summary.conflicted_ingredients.slice(0, 4).map(renderConflictCard)}
                  </div>
                </Card>
              )}

              {/* Top 3 Dishes */}
              <div className="space-y-4">
                <h2 className="text-xl font-extrabold" style={{ color: "var(--text)" }}>
                  {t("menu.top3Title")}
                </h2>
                {menuData.top_3.map((dish, idx) => {
                  const scoreOpen = Boolean(expandedScores[dish.recipe_id]);
                  const splitInstruction = pickLocalized(
                    dish.split_instruction_bn || dish.split_step_bn,
                    dish.split_instruction_en || dish.split_step_bn,
                  );
                  return (
                    <Card
                      key={dish.recipe_id}
                      variant="raised"
                      className="space-y-4"
                      data-testid={`menu-dish-card-${idx}`}
                    >
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="space-y-1">
                          <h3 className="text-xl font-extrabold" style={{ color: "var(--text)" }}>
                            {formatNumber(idx + 1)}. {pickLocalized(dish.name_bn, dish.name_en)}
                          </h3>
                          <p className="text-xs font-semibold" style={{ color: "var(--text-muted)" }}>
                            {t("menu.servingsText", { count: dish.scaled_servings })} • {dish.category}
                          </p>
                        </div>
                        <Badge
                          variant={dish.status === "SAFE_WITH_SPLIT" ? "SAFE_WITH_SPLIT" : "SAFE_DIRECT"}
                          ruleId={dish.rule_ids[0]}
                        />
                      </div>

                      <p className="text-sm sm:text-base leading-relaxed" style={{ color: "var(--text)" }}>
                        {pickLocalized(dish.explanation_bn, dish.explanation_en)}
                      </p>

                      {dish.status === "SAFE_WITH_SPLIT" && splitInstruction && (
                        <div
                          className="neu-inset p-4 space-y-1"
                          style={{ borderColor: "var(--saffron-text)" }}
                          data-testid={`menu-split-callout-${idx}`}
                        >
                          <div className="flex items-center gap-2 text-sm font-extrabold" style={{ color: "var(--saffron-text)" }}>
                            <GitFork className="h-4 w-4" aria-hidden="true" />
                            <span>{t("menu.splitCalloutTitle")}</span>
                          </div>
                          {dish.split_for.length > 0 && (
                            <p className="text-xs font-bold" style={{ color: "var(--text)" }}>
                              {t("menu.splitForMembers", { names: dish.split_for.join(", ") })}
                            </p>
                          )}
                          <p className="text-sm font-medium" style={{ color: "var(--text)" }}>
                            {splitInstruction}
                          </p>
                        </div>
                      )}

                      {dish.missing_ingredients.length > 0 && (
                        <div className="neu-inset p-3.5 space-y-2 text-xs">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <span className="font-bold" style={{ color: "var(--text)" }}>
                              {t("menu.missingLabel")}
                            </span>
                            <Badge
                              variant="ESTIMATED"
                              label={`${t("menu.shortfallEst")}: ${formatNumber(dish.shortfall_cost_bdt)} ${t("common.bdt")} (${t("common.estimated")})`}
                            />
                          </div>
                          <div className="flex flex-wrap gap-2">
                            {dish.missing_ingredients.map((mi) => (
                              <span
                                key={mi.ingredient_key}
                                className="rounded-full border border-[var(--border-subtle)] px-2.5 py-1"
                                style={{ color: "var(--text-muted)" }}
                              >
                                {mi.name_bn || mi.ingredient_key}: {formatNumber(mi.missing_qty)} {mi.unit}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
                        <button
                          type="button"
                          onClick={() =>
                            setExpandedScores((prev) => ({
                              ...prev,
                              [dish.recipe_id]: !scoreOpen,
                            }))
                          }
                          className="neu-raised-sm inline-flex min-h-[44px] items-center gap-1.5 px-3.5 py-2 text-xs font-bold cursor-pointer"
                          style={{ color: "var(--text)" }}
                          data-testid={`menu-score-toggle-${idx}`}
                        >
                          <Sparkles className="h-3.5 w-3.5" style={{ color: "var(--accent)" }} aria-hidden="true" />
                          <span>{t("menu.whyDishBtn")}</span>
                          {scoreOpen ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                        </button>

                        <Button
                          variant="primary"
                          onClick={() => handleMarkCooked(dish)}
                          data-testid={`menu-cooked-btn-${idx}`}
                        >
                          {t("menu.markCookedBtn")}
                        </Button>
                      </div>

                      {scoreOpen && (
                        <div className="neu-inset p-4 space-y-2.5" data-testid={`menu-score-panel-${idx}`}>
                          {Object.entries(dish.components).map(([ck, val]) => {
                            const pct = Math.min(100, Math.max(0, Math.round(Number(val) * 100)));
                            return (
                              <div key={ck} className="space-y-1 text-xs">
                                <div className="flex justify-between font-semibold">
                                  <span style={{ color: "var(--text)" }}>
                                    {t(`menu.scoreLabels.${ck}`)}
                                  </span>
                                  <span className="font-mono" style={{ color: "var(--text-muted)" }}>
                                    {formatNumber(pct)}%
                                  </span>
                                </div>
                                <div className="h-2 w-full rounded-full overflow-hidden bg-[var(--surface-elevated)]">
                                  <div
                                    className="h-full rounded-full"
                                    style={{
                                      width: `${pct}%`,
                                      backgroundColor: "var(--accent)",
                                    }}
                                  />
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </Card>
                  );
                })}
              </div>

              {/* Excluded Dishes Glass Panel */}
              <Card variant="glass" className="space-y-3" data-testid="menu-excluded-panel">
                <button
                  type="button"
                  onClick={() => setExcludedOpen((v) => !v)}
                  className="flex w-full items-center justify-between text-left cursor-pointer min-h-[44px]"
                >
                  <span className="text-base font-extrabold" style={{ color: "var(--text)" }}>
                    {t("menu.excludedTitle", { count: menuData.excluded.length })}
                  </span>
                  {excludedOpen ? <ChevronUp className="h-5 w-5" /> : <ChevronDown className="h-5 w-5" />}
                </button>
                {excludedOpen && (
                  <div className="space-y-3">
                    {menuData.excluded.length === 0 ? (
                      <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                        {t("menu.excludedEmpty")}
                      </p>
                    ) : (
                      menuData.excluded.map((excl) => (
                        <div key={excl.recipe_id} className="neu-inset p-3.5 space-y-2">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <span className="font-bold text-sm" style={{ color: "var(--text)" }}>
                              {pickLocalized(excl.name_bn, excl.name_en)}
                            </span>
                            <Badge variant="BLOCKED" ruleId={excl.reasons[0]} />
                          </div>
                          <div className="space-y-1.5 text-xs">
                            {excl.member_details.map((md, mi) => (
                              <div key={mi} className="border-t border-[var(--border-subtle)] pt-1.5">
                                <span className="font-bold" style={{ color: "var(--danger)" }}>
                                  {md.member_name}: {md.reasons.join(", ")}
                                </span>
                                {md.trace.length > 0 && (
                                  <p className="font-mono mt-0.5" style={{ color: "var(--text-muted)" }}>
                                    {md.trace[0]}
                                  </p>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                )}
              </Card>
            </div>
          )}
        </>
      ) : (
        /* Whole-Week Household Meal Planner */
        <div className="space-y-6" data-testid="weekly-planner-view">
          <Card variant="raised" className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2 items-end">
              <Input
                label={t("menu.weekly.startDateLabel")}
                type="date"
                value={weekStartDate}
                onChange={(e) => setWeekStartDate(e.target.value)}
                data-testid="weekly-start-date-input"
              />
              <Toggle
                checked={useWeeklyAiSummary}
                onChange={setUseWeeklyAiSummary}
                label={t("menu.weekly.aiSummaryLabel")}
                data-testid="weekly-ai-toggle"
              />
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <Button
                variant="primary"
                onClick={handleGenerateWeeklyPlan}
                disabled={weeklyLoading}
                data-testid="weekly-generate-btn"
              >
                <CalendarDays className="h-4 w-4" aria-hidden="true" />
                <span>{weeklyLoading ? t("menu.weekly.generating") : t("menu.weekly.generateBtn")}</span>
              </Button>

              {weeklyPlan && (
                <Button
                  variant="neu"
                  onClick={handleConvertWeeklyToBazar}
                  disabled={weeklyLoading || weeklyPlan.shortfall_items.length === 0}
                  data-testid="weekly-to-bazar-btn"
                >
                  <ShoppingBasket className="h-4 w-4" style={{ color: "var(--accent)" }} aria-hidden="true" />
                  <span>{t("menu.weekly.toBazarBtn")}</span>
                </Button>
              )}

              {bazarConvertedId && (
                <Link
                  href="/bazar"
                  className="skeu-button inline-flex min-h-[40px] items-center gap-1.5 rounded-full px-4 py-1.5 text-xs font-bold"
                >
                  {t("menu.weekly.goToBazarLink")} →
                </Link>
              )}
            </div>
          </Card>

          {weeklyError && (
            <Card variant="glass">
              <p className="text-sm font-semibold" style={{ color: "var(--danger)" }}>
                {weeklyError}
              </p>
            </Card>
          )}

          {weeklyLoading && !weeklyPlan && (
            <div className="space-y-4">
              <Skeleton className="h-28 rounded-[20px]" />
              <Skeleton className="h-64 rounded-[20px]" />
            </div>
          )}

          {!weeklyLoading && !weeklyPlan && (
            <Card variant="inset" className="text-center py-8 space-y-2">
              <CalendarDays className="h-9 w-9 mx-auto" style={{ color: "var(--accent)" }} aria-hidden="true" />
              <p className="text-sm sm:text-base font-medium" style={{ color: "var(--text-muted)" }}>
                {t("menu.weekly.emptyState")}
              </p>
            </Card>
          )}

          {weeklyPlan && (
            <div className="space-y-6" data-testid="weekly-plan-results">
              {/* KPI Strip */}
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <Card variant="raised" className="space-y-1">
                  <p className="text-xs font-bold" style={{ color: "var(--text-muted)" }}>
                    {t("menu.weekly.kpiSafeSlots")}
                  </p>
                  <p className="text-2xl font-extrabold font-mono" style={{ color: "var(--ok)" }}>
                    {formatNumber(weeklyPlan.safe_slots_count)} / {formatNumber(weeklyPlan.total_slots)}
                  </p>
                </Card>
                <Card variant="raised" className="space-y-1">
                  <p className="text-xs font-bold" style={{ color: "var(--text-muted)" }}>
                    {t("menu.weekly.kpiUniqueDishes")}
                  </p>
                  <p className="text-2xl font-extrabold font-mono" style={{ color: "var(--text)" }}>
                    {formatNumber(weeklyPlan.unique_dishes_count)}
                  </p>
                </Card>
                <Card variant="raised" className="space-y-1">
                  <p className="text-xs font-bold" style={{ color: "var(--text-muted)" }}>
                    {t("menu.weekly.kpiConflicts")}
                  </p>
                  <p className="text-2xl font-extrabold font-mono" style={{ color: "var(--saffron-text)" }}>
                    {formatNumber(weeklyPlan.conflict_matrix.length)}
                  </p>
                </Card>
                <Card variant="raised" className="space-y-1">
                  <p className="text-xs font-bold" style={{ color: "var(--text-muted)" }}>
                    {t("menu.weekly.kpiShortfall")}
                  </p>
                  <p className="text-2xl font-extrabold font-mono" style={{ color: weeklyPlan.over_weekly_budget ? "var(--danger)" : "var(--text)" }}>
                    {formatNumber(weeklyPlan.est_weekly_shortfall_bdt)} {t("common.bdt")}
                  </p>
                  <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                    {weeklyPlan.over_weekly_budget
                      ? t("menu.weekly.budgetOver", { target: formatNumber(weeklyPlan.weekly_budget_target_bdt) })
                      : t("menu.weekly.budgetWithin", { target: formatNumber(weeklyPlan.weekly_budget_target_bdt) })}
                  </p>
                </Card>
              </div>

              {/* Coach Summary Card */}
              <Card variant="glass" className="space-y-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <Badge
                    variant={weeklyPlan.used_ai_summary ? "SAFE_WITH_SPLIT" : "SAFE_DIRECT"}
                    label={weeklyPlan.used_ai_summary ? t("menu.weekly.aiCoachBadge") : t("menu.weekly.detCoachBadge")}
                  />
                  <span className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                    {weeklyPlan.start_date} → {weeklyPlan.end_date}
                  </span>
                </div>
                <p className="text-sm leading-relaxed font-medium" style={{ color: "var(--text)" }}>
                  {pickLocalized(weeklyPlan.coach_summary_bn, weeklyPlan.coach_summary_en)}
                </p>
              </Card>

              {/* 7-Day Grid */}
              <div className="space-y-4">
                {weeklyPlan.days.map((day) => (
                  <Card key={day.for_date} variant="raised" className="space-y-3" data-testid={`weekly-day-${day.for_date}`}>
                    <div className="flex flex-wrap items-center justify-between gap-2 pb-2 border-b border-[var(--border-subtle)]">
                      <div>
                        <h3 className="text-lg font-extrabold" style={{ color: "var(--text)" }}>
                          {pickLocalized(day.weekday_bn, day.weekday_en)} · {day.for_date}
                        </h3>
                        <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                          {t("menu.presentLabel")}: {day.present_member_names.join(", ")}
                          {day.guest_count > 0 && ` (+${formatNumber(day.guest_count)} ${t("menu.guestsLabel")})`}
                        </p>
                      </div>
                      <Badge
                        variant="INFO"
                        label={t("menu.servingsText", { count: day.people_count })}
                      />
                    </div>
                    <div className="grid gap-3 md:grid-cols-3">
                      {day.slots.map((slot) => renderWeeklySlotCard(day.for_date, slot))}
                    </div>
                  </Card>
                ))}
              </div>

              {/* Ingredient Conflict Matrix */}
              <Card variant="glass" className="space-y-3" data-testid="weekly-conflict-matrix">
                <h2 className="text-lg font-extrabold" style={{ color: "var(--text)" }}>
                  {t("menu.weekly.conflictMatrixTitle", {
                    count: formatNumber(weeklyPlan.conflict_matrix.length),
                  })}
                </h2>
                {weeklyPlan.conflict_matrix.length === 0 ? (
                  <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                    {t("menu.weekly.conflictMatrixEmpty")}
                  </p>
                ) : (
                  <div className="grid gap-3 md:grid-cols-2">
                    {weeklyPlan.conflict_matrix.map(renderConflictCard)}
                  </div>
                )}
              </Card>

              {/* Consolidated 7-Day Shortfall */}
              <Card variant="raised" className="space-y-3" data-testid="weekly-shortfall-panel">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h2 className="text-lg font-extrabold" style={{ color: "var(--text)" }}>
                    {t("menu.weekly.shortfallTitle", {
                      count: formatNumber(weeklyPlan.shortfall_items.length),
                    })}
                  </h2>
                  <Badge
                    variant="ESTIMATED"
                    label={`${formatNumber(weeklyPlan.est_weekly_shortfall_bdt)} ${t("common.bdt")} (${t("common.estimated")})`}
                  />
                </div>
                {weeklyPlan.shortfall_items.length === 0 ? (
                  <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                    {t("menu.weekly.shortfallEmpty")}
                  </p>
                ) : (
                  <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                    {weeklyPlan.shortfall_items.map((item) => (
                      <div
                        key={item.ingredient_key}
                        className="neu-inset px-3 py-2 flex items-center justify-between gap-2 text-xs"
                      >
                        <div>
                          <p className="font-bold" style={{ color: "var(--text)" }}>
                            {pickLocalized(item.name_bn, item.name_en)}
                          </p>
                          <p style={{ color: "var(--text-muted)" }}>
                            {formatNumber(item.qty)} {item.unit}
                          </p>
                        </div>
                        <span className="font-mono font-bold" style={{ color: "var(--saffron-text)" }}>
                          {formatNumber(item.est_price_bdt)} {t("common.bdt")}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </Card>
            </div>
          )}
        </div>
      )}

      {/* Guests & Absence Review Sheet */}
      <Sheet open={reviewOpen} onClose={() => setReviewOpen(false)} title={t("menu.reviewSheetTitle")}>
        <form onSubmit={handleApplyReview} className="space-y-4">
          <Input
            label={t("menu.guestCountLabel")}
            type="number"
            min={0}
            max={50}
            value={guestCount}
            onChange={(e) => setGuestCount(e.target.value)}
            data-testid="review-guest-count"
          />

          <div className="space-y-2">
            <p className="text-sm font-semibold" style={{ color: "var(--text)" }}>
              {t("menu.guestRestrictionsLabel")}
            </p>
            <div className="flex flex-wrap gap-2">
              {allergenKeys.map((ak) => {
                const active = guestRestrictions.includes(ak);
                return (
                  <button
                    key={ak}
                    type="button"
                    onClick={() =>
                      setGuestRestrictions((prev) =>
                        prev.includes(ak) ? prev.filter((x) => x !== ak) : [...prev, ak],
                      )
                    }
                    className={`min-h-[40px] rounded-full px-3 py-1 text-xs font-bold cursor-pointer ${
                      active ? "skeu-button" : "neu-raised-sm"
                    }`}
                    style={active ? undefined : { color: "var(--text)" }}
                  >
                    {DEFAULT_ALLERGEN_KEYS.includes(ak) ? t(`members.allergens.${ak}`) : ak}
                  </button>
                );
              })}
            </div>
          </div>

          {members.length > 0 && (
            <div className="space-y-2">
              <p className="text-sm font-semibold" style={{ color: "var(--text)" }}>
                {t("menu.awayMembersLabel")}
              </p>
              <div className="flex flex-wrap gap-2">
                {members.map((m) => {
                  const away = awayMemberIds.includes(m.id);
                  return (
                    <button
                      key={m.id}
                      type="button"
                      onClick={() =>
                        setAwayMemberIds((prev) =>
                          prev.includes(m.id) ? prev.filter((x) => x !== m.id) : [...prev, m.id],
                        )
                      }
                      className={`min-h-[40px] rounded-full px-3 py-1 text-xs font-bold cursor-pointer ${
                        away ? "skeu-button" : "neu-raised-sm"
                      }`}
                      style={away ? undefined : { color: "var(--text)" }}
                    >
                      {m.name}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          <div className="flex justify-end gap-3 pt-2">
            <Button variant="ghost" onClick={() => setReviewOpen(false)}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" variant="primary" disabled={loading} data-testid="review-apply-btn">
              {loading ? t("common.loading") : t("menu.applyReviewBtn")}
            </Button>
          </div>
        </form>
      </Sheet>
    </div>
  );
}
