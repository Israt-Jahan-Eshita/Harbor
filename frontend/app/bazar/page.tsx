"use client";

import React, { useEffect, useState } from "react";
import { CheckCircle2, ShoppingBag, ShoppingBasket, Sparkles } from "lucide-react";
import { AuthGuardNotice } from "@/components/AuthGuardNotice";
import { Badge, Button, Card, Input, Sheet, Skeleton, useToast } from "@/components/ui";
import {
  ApiError,
  BazarBuildResponse,
  BazarItem,
  BazarPurchasedItemPayload,
  harborApi,
} from "@/lib/api";
import { getDhakaMonthISO } from "@/lib/date";
import { useI18n } from "@/lib/i18n";
import { useSession } from "@/lib/session";

function prettifyKey(key: string): string {
  return key
    .split("_")
    .map((w) => (w ? w[0].toUpperCase() + w.slice(1) : ""))
    .join(" ");
}

export default function BazarPage() {
  const { locale, formatNumber, pickLocalized, t } = useI18n();
  const { session } = useSession();
  const { showToast } = useToast();

  const [month, setMonth] = useState(() => getDhakaMonthISO());
  const [budgetOverride, setBudgetOverride] = useState<string | null>(null);
  const budget = budgetOverride ?? String(session?.monthlyBudgetBdt ?? 15000);
  const [plan, setPlan] = useState<BazarBuildResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [building, setBuilding] = useState(false);
  const [confirming, setConfirming] = useState(false);

  const [purchaseOpen, setPurchaseOpen] = useState(false);
  const [savingPurchase, setSavingPurchase] = useState(false);
  const [purchaseDraft, setPurchaseDraft] = useState<
    Record<string, { included: boolean; qty: string; price: string }>
  >({});

  useEffect(() => {
    if (!session) return;
    let cancelled = false;
    harborApi
      .getLatestBazar(session.token, locale)
      .then((res) => {
        if (!cancelled) {
          if (res.bazar_list) {
            setPlan(res.bazar_list);
          }
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [session, locale]);

  async function handleBuild(e: React.FormEvent) {
    e.preventDefault();
    if (!session) return;
    setBuilding(true);
    try {
      const res = await harborApi.buildBazar(
        { month, budget_bdt: Math.max(100, Number(budget) || 15000) },
        session.token,
        locale,
      );
      setPlan(res);
      showToast(t("bazar.buildBtn"), "success");
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("common.errorUnexpected"), "error");
    } finally {
      setBuilding(false);
    }
  }

  function toggleDropItem(ingredientKey: string) {
    if (!plan) return;
    const nextItems: BazarItem[] = plan.items.map((it) =>
      it.ingredient_key === ingredientKey ? { ...it, dropped: !it.dropped } : it,
    );
    const nextTotal = Math.round(
      nextItems
        .filter((it) => !it.dropped)
        .reduce((sum, it) => sum + (it.est_price_bdt || 0), 0) * 100,
    ) / 100;
    setPlan({
      ...plan,
      items: nextItems,
      est_total_bdt: nextTotal,
      over_budget: nextTotal > plan.budget_bdt,
    });
  }

  async function handleConfirmList() {
    if (!session || !plan) return;
    setConfirming(true);
    try {
      const res = await harborApi.confirmBazar(
        { bazar_list_id: plan.bazar_list_id, items: plan.items },
        session.token,
        locale,
      );
      setPlan({ ...plan, status: res.status, est_total_bdt: res.est_total_bdt, items: res.items });
      showToast(t("common.confirm"), "success");
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("common.errorUnexpected"), "error");
    } finally {
      setConfirming(false);
    }
  }

  function openPurchaseSheet() {
    if (!plan) return;
    const draft: Record<string, { included: boolean; qty: string; price: string }> = {};
    for (const it of plan.items) {
      if (!it.dropped) {
        draft[it.ingredient_key] = {
          included: true,
          qty: String(it.qty),
          price: it.est_price_bdt > 0 ? String(it.est_price_bdt) : "",
        };
      }
    }
    setPurchaseDraft(draft);
    setPurchaseOpen(true);
  }

  async function handleSavePurchases(e: React.FormEvent) {
    e.preventDefault();
    if (!session || !plan) return;
    const itemsPayload: BazarPurchasedItemPayload[] = [];
    for (const it of plan.items) {
      const row = purchaseDraft[it.ingredient_key];
      if (!row || !row.included) continue;
      const qtyNum = Number(row.qty);
      if (!qtyNum || qtyNum <= 0) continue;
      const priceNum = row.price ? Number(row.price) : undefined;
      itemsPayload.push({
        ingredient_key: it.ingredient_key,
        qty_base: qtyNum,
        price_bdt: priceNum && priceNum > 0 ? priceNum : null,
        per_qty: qtyNum,
      });
    }
    if (itemsPayload.length === 0) return;

    setSavingPurchase(true);
    try {
      await harborApi.logBazarPurchased(
        { bazar_list_id: plan.bazar_list_id, items: itemsPayload },
        session.token,
        locale,
      );
      setPurchaseOpen(false);
      showToast(t("bazar.savePurchasedBtn"), "success");
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("common.errorUnexpected"), "error");
    } finally {
      setSavingPurchase(false);
    }
  }

  if (!session) return <AuthGuardNotice />;

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl sm:text-3xl font-extrabold" style={{ color: "var(--text)" }}>
          {t("bazar.title")}
        </h1>
        <p className="text-sm sm:text-base" style={{ color: "var(--text-muted)" }}>
          {t("bazar.subtitle")}
        </p>
      </div>

      {/* Builder Controls */}
      <Card variant="raised">
        <form onSubmit={handleBuild} className="grid gap-4 sm:grid-cols-3 items-end">
          <Input
            label={t("bazar.monthLabel")}
            type="month"
            value={month}
            onChange={(e) => setMonth(e.target.value)}
            required
          />
          <Input
            label={t("bazar.budgetLabel")}
            type="number"
            min={100}
            value={budget}
            onChange={(e) => setBudgetOverride(e.target.value)}
            required
            data-testid="bazar-budget-input"
          />
          <Button type="submit" variant="primary" disabled={building} data-testid="bazar-build-btn">
            <ShoppingBasket className="h-4 w-4" aria-hidden="true" />
            <span>{building ? t("common.loading") : t("bazar.buildBtn")}</span>
          </Button>
        </form>
      </Card>

      {loading ? (
        <Skeleton className="h-56 rounded-[20px]" />
      ) : !plan ? (
        <Card variant="inset" className="py-10 text-center">
          <p className="text-sm sm:text-base" style={{ color: "var(--text-muted)" }}>
            {t("bazar.noPlanYet")}
          </p>
        </Card>
      ) : (
        <div className="space-y-6">
          {/* Totals & Actions */}
          <Card variant="glass" className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-xs font-bold" style={{ color: "var(--text-muted)" }}>
                  {t("bazar.totalEstLabel")} ({plan.month})
                </p>
                <div className="flex flex-wrap items-center gap-2 mt-1">
                  <span className="text-2xl font-extrabold font-mono" style={{ color: "var(--text)" }}>
                    {formatNumber(plan.est_total_bdt)} {t("common.bdt")}
                  </span>
                  <Badge variant="ESTIMATED" label={t("common.estimated")} />
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button variant="primary" onClick={handleConfirmList} disabled={confirming}>
                  <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
                  <span>{confirming ? t("common.loading") : t("bazar.confirmBtn")}</span>
                </Button>
                <Button variant="neu" onClick={openPurchaseSheet}>
                  <ShoppingBag className="h-4 w-4" style={{ color: "var(--accent)" }} aria-hidden="true" />
                  <span>{t("bazar.purchasedBtn")}</span>
                </Button>
              </div>
            </div>

            {plan.over_budget && (
              <p className="text-xs font-bold" style={{ color: "var(--saffron-text)" }}>
                {t("bazar.overBudgetWarn")}
              </p>
            )}

            {plan.planned_recipes?.length > 0 && (
              <div className="space-y-1.5 pt-2 border-t border-[var(--border-subtle)]">
                <p className="text-xs font-bold flex items-center gap-1.5" style={{ color: "var(--text)" }}>
                  <Sparkles className="h-3.5 w-3.5" style={{ color: "var(--accent)" }} aria-hidden="true" />
                  <span>{t("bazar.plannedRecipesTitle")}</span>
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {plan.planned_recipes.map((r) => (
                    <span
                      key={r.key}
                      className="rounded-full border border-[var(--border-subtle)] px-2.5 py-1 text-xs font-semibold"
                      style={{ color: "var(--text)" }}
                    >
                      {pickLocalized(r.name_bn, prettifyKey(r.key))}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </Card>

          {/* Bazar Item Grid */}
          <div className="grid gap-3 sm:grid-cols-2">
            {plan.items.map((it) => (
              <Card
                key={it.ingredient_key}
                variant={it.dropped ? "inset" : "raised"}
                className="flex flex-col justify-between gap-3"
                style={it.dropped ? { opacity: 0.72 } : undefined}
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h2 className="text-base font-extrabold" style={{ color: "var(--text)" }}>
                      {pickLocalized(it.name_bn, prettifyKey(it.ingredient_key))}
                    </h2>
                    <p className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                      {formatNumber(it.qty)} {it.unit} • {it.category}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="font-mono text-base font-extrabold" style={{ color: "var(--accent)" }}>
                      {formatNumber(it.est_price_bdt)} {t("common.bdt")}
                    </p>
                    <p className="text-[11px]" style={{ color: "var(--saffron-text)" }}>
                      {t("common.estimated")}
                    </p>
                  </div>
                </div>

                <div className="flex flex-wrap gap-1.5">
                  {it.in_season && <Badge variant="SAFE_DIRECT" label={t("bazar.inSeasonBadge")} />}
                  {it.substitute_used && <Badge variant="SAFE_WITH_SPLIT" label={t("bazar.substituteBadge")} />}
                  {it.dropped && <Badge variant="BLOCKED" label={t("bazar.droppedBadge")} />}
                  {it.missing_price && <Badge variant="UNVERIFIED" label={t("bazar.missingPriceBadge")} />}
                </div>

                {it.flag && (
                  <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                    {it.flag}
                  </p>
                )}

                <div className="pt-1 border-t border-[var(--border-subtle)] flex justify-end">
                  <Button
                    variant="ghost"
                    className="!min-h-[38px] !px-3 !py-1 !text-xs"
                    onClick={() => toggleDropItem(it.ingredient_key)}
                  >
                    {it.dropped ? t("bazar.restoreToggle") : t("bazar.dropToggle")}
                  </Button>
                </div>
              </Card>
            ))}
          </div>
        </div>
      )}

      {/* Purchase Tick-off Sheet */}
      <Sheet
        open={purchaseOpen}
        onClose={() => setPurchaseOpen(false)}
        title={t("bazar.purchasedSheetTitle")}
      >
        {plan && (
          <form onSubmit={handleSavePurchases} className="space-y-4">
            <div className="space-y-3">
              {plan.items
                .filter((it) => !it.dropped)
                .map((it) => {
                  const row = purchaseDraft[it.ingredient_key];
                  if (!row) return null;
                  return (
                    <div key={it.ingredient_key} className="neu-inset p-3 space-y-2">
                      <label className="flex items-center gap-2 text-sm font-bold cursor-pointer">
                        <input
                          type="checkbox"
                          checked={row.included}
                          onChange={(e) =>
                            setPurchaseDraft((prev) => ({
                              ...prev,
                              [it.ingredient_key]: { ...row, included: e.target.checked },
                            }))
                          }
                          className="h-4 w-4 accent-[var(--accent)]"
                        />
                        <span style={{ color: "var(--text)" }}>
                          {pickLocalized(it.name_bn, prettifyKey(it.ingredient_key))}
                        </span>
                      </label>
                      {row.included && (
                        <div className="grid grid-cols-2 gap-2">
                          <Input
                            label={`${t("bazar.actualQtyLabel")} (${it.unit})`}
                            type="number"
                            step="any"
                            value={row.qty}
                            onChange={(e) =>
                              setPurchaseDraft((prev) => ({
                                ...prev,
                                [it.ingredient_key]: { ...row, qty: e.target.value },
                              }))
                            }
                          />
                          <Input
                            label={t("bazar.actualPriceLabel")}
                            type="number"
                            step="any"
                            value={row.price}
                            onChange={(e) =>
                              setPurchaseDraft((prev) => ({
                                ...prev,
                                [it.ingredient_key]: { ...row, price: e.target.value },
                              }))
                            }
                          />
                        </div>
                      )}
                    </div>
                  );
                })}
            </div>
            <div className="flex justify-end gap-3">
              <Button variant="ghost" onClick={() => setPurchaseOpen(false)}>
                {t("common.cancel")}
              </Button>
              <Button type="submit" variant="primary" disabled={savingPurchase}>
                {savingPurchase ? t("common.loading") : t("bazar.savePurchasedBtn")}
              </Button>
            </div>
          </form>
        )}
      </Sheet>
    </div>
  );
}

