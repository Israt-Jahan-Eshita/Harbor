"use client";

import React, { useEffect, useState } from "react";
import {
  ChefHat,
  ChevronDown,
  ChevronUp,
  GitFork,
  Sparkles,
  Users,
  Utensils,
} from "lucide-react";
import { AuthGuardNotice } from "@/components/AuthGuardNotice";
import { Badge, Button, Card, Input, Sheet, Skeleton, Tabs, Toggle, useToast } from "@/components/ui";
import { ApiError, harborApi, MealSlot, MemberRecord, MenuResponse, MenuTopDish } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useSession } from "@/lib/session";

const ALLERGEN_KEYS = [
  "prawn_shellfish",
  "fish",
  "egg",
  "milk",
  "peanut",
  "tree_nut",
  "wheat_gluten",
  "soy",
  "sesame",
] as const;

export default function MenuPage() {
  const { locale, formatNumber, pickLocalized, t } = useI18n();
  const { session } = useSession();
  const { showToast } = useToast();

  const [forDate, setForDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [meal, setMeal] = useState<MealSlot>("dinner");
  const [useAgent, setUseAgent] = useState(true);
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

  useEffect(() => {
    if (!session) return;
    let cancelled = false;
    harborApi
      .listMembers(session.token, locale)
      .then((res) => {
        if (!cancelled) setMembers(res.members);
      })
      .catch(() => {
        /* members list optional until review opens */
      });
    return () => {
      cancelled = true;
    };
  }, [session, locale]);

  async function handleSuggest() {
    if (!session) return;
    setLoading(true);
    setErrorMsg(null);
    try {
      const res = await harborApi.suggestMenu(
        { for_date: forDate, meal, use_agent: useAgent },
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
        { recipe_id: dish.recipe_id, servings: dish.scaled_servings, for_date: forDate },
        session.token,
        locale,
      );
      showToast(t("menu.cookedToast"), "success");
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("common.errorUnexpected"), "error");
    }
  }

  if (!session) return <AuthGuardNotice />;

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl sm:text-3xl font-extrabold" style={{ color: "var(--text)" }}>
          {t("menu.title")}
        </h1>
        <p className="text-sm sm:text-base" style={{ color: "var(--text-muted)" }}>
          {t("menu.subtitle")}
        </p>
      </div>

      {/* Controls Card */}
      <Card variant="raised" className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Input
            label={t("menu.dateLabel")}
            type="date"
            value={forDate}
            onChange={(e) => setForDate(e.target.value)}
            data-testid="menu-date-input"
          />
          <div className="space-y-1.5">
            <span className="block text-sm font-semibold" style={{ color: "var(--text)" }}>
              {t("menu.mealLabel")}
            </span>
            <Tabs
              value={meal}
              onChange={(m) => setMeal(m as MealSlot)}
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

                  {/* Bilingual Explanation */}
                  <p className="text-sm sm:text-base leading-relaxed" style={{ color: "var(--text)" }}>
                    {pickLocalized(dish.explanation_bn, dish.explanation_en)}
                  </p>

                  {/* Split Callout */}
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

                  {/* Missing Ingredients & Estimated Cost */}
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
                            {mi.name_bn || mi.ingredient_key}: {formatNumber(mi.shortfall)} {mi.unit}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Actions & Score Breakdown Toggle */}
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
              {ALLERGEN_KEYS.map((ak) => {
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
                    {t(`members.allergens.${ak}`)}
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

