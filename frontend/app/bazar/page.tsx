"use client";

import React, { useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  CheckSquare,
  Plus,
  ShoppingBag,
  ShoppingBasket,
  Sparkles,
} from "lucide-react";
import { AuthGuardNotice } from "@/components/AuthGuardNotice";
import { Badge, Button, Card, Input, Sheet, Skeleton, useToast } from "@/components/ui";
import {
  ApiError,
  BazarBuildResponse,
  BazarItem,
  BazarPredictItemResponse,
  BazarPurchasedItemPayload,
  harborApi,
  StockItem,
} from "@/lib/api";
import { getDhakaMonthISO } from "@/lib/date";
import { useI18n } from "@/lib/i18n";
import { useSession } from "@/lib/session";

function prettifyKey(key: string): string {
  return key
    .replace(/^custom_/, "")
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
  const [stockOptions, setStockOptions] = useState<StockItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [building, setBuilding] = useState(false);
  const [confirming, setConfirming] = useState(false);

  // Add item & price prediction sheet state
  const [addOpen, setAddOpen] = useState(false);
  const [addMode, setAddMode] = useState<"verified" | "custom">("verified");
  const [addIngKey, setAddIngKey] = useState("");
  const [customName, setCustomName] = useState("");
  const [addQty, setAddQty] = useState("500");
  const [addUnit, setAddUnit] = useState<"g" | "ml" | "piece">("g");
  const [useAiEstimate, setUseAiEstimate] = useState(false);
  const [predicting, setPredicting] = useState(false);
  const [prediction, setPrediction] = useState<BazarPredictItemResponse | null>(null);
  const [priceOverride, setPriceOverride] = useState("");

  // Purchase tick-off sheet state
  const [purchaseOpen, setPurchaseOpen] = useState(false);
  const [savingPurchase, setSavingPurchase] = useState(false);
  const [purchaseDraft, setPurchaseDraft] = useState<
    Record<string, { included: boolean; qty: string; price: string }>
  >({});

  useEffect(() => {
    if (!session) return;
    let cancelled = false;
    Promise.all([
      harborApi.getLatestBazar(session.token, locale),
      harborApi.getStock(session.token, locale),
    ])
      .then(([bRes, sRes]) => {
        if (cancelled) return;
        if (bRes.bazar_list) {
          setPlan(bRes.bazar_list);
        }
        const items = sRes.items || [];
        setStockOptions(items);
        if (items.length > 0) {
          setAddIngKey((prev) => prev || items[0].ingredient_key);
        }
        setLoading(false);
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

  function recalcPlanItems(nextItems: BazarItem[], nextStatus?: string) {
    if (!plan) return;
    const nextTotal =
      Math.round(
        nextItems
          .filter((it) => !it.dropped)
          .reduce((sum, it) => sum + (it.est_price_bdt || 0), 0) * 100,
      ) / 100;
    setPlan({
      ...plan,
      status: nextStatus ?? "draft",
      items: nextItems,
      est_total_bdt: nextTotal,
      over_budget: nextTotal > plan.budget_bdt,
    });
  }

  function toggleDropItem(ingredientKey: string) {
    if (!plan) return;
    const nextItems: BazarItem[] = plan.items.map((it) =>
      it.ingredient_key === ingredientKey ? { ...it, dropped: !it.dropped } : it,
    );
    recalcPlanItems(nextItems);
  }

  function selectAllItems() {
    if (!plan) return;
    const nextItems: BazarItem[] = plan.items.map((it) => ({ ...it, dropped: false }));
    recalcPlanItems(nextItems);
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

  function openAddItemSheet() {
    const first = stockOptions.find((s) => s.ingredient_key === addIngKey) || stockOptions[0];
    if (first) {
      setAddIngKey(first.ingredient_key);
      setAddUnit((first.base_unit as "g" | "ml" | "piece") || "g");
      setAddQty(first.base_unit === "piece" ? "4" : "500");
    }
    setAddMode("verified");
    setCustomName("");
    setUseAiEstimate(false);
    setPrediction(null);
    setPriceOverride("");
    setAddOpen(true);
  }

  async function handlePredictPrice(e: React.FormEvent) {
    e.preventDefault();
    if (!session || !plan) return;
    const qtyNum = Number(addQty);
    if (!qtyNum || qtyNum <= 0) return;
    setPredicting(true);
    try {
      const res = await harborApi.predictBazarItem(
        {
          ingredient_key: addMode === "verified" ? addIngKey : null,
          custom_name: addMode === "custom" ? customName.trim() : null,
          qty: qtyNum,
          unit: addUnit,
          month: plan.month,
          budget_bdt: plan.budget_bdt,
          current_total_bdt: plan.est_total_bdt,
          use_ai_estimate: useAiEstimate,
        },
        session.token,
        locale,
      );
      setPrediction(res);
      setPriceOverride(String(res.item.est_price_bdt));
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("common.errorUnexpected"), "error");
    } finally {
      setPredicting(false);
    }
  }

  function handleConfirmAddItem() {
    if (!plan || !prediction) return;
    const finalPrice = Math.max(0, Number(priceOverride || prediction.item.est_price_bdt) || 0);
    const preparedItem: BazarItem = {
      ...prediction.item,
      est_price_bdt: Math.round(finalPrice * 100) / 100,
      missing_price: finalPrice <= 0 && prediction.item.missing_price,
      dropped: false,
    };

    const existingIdx = plan.items.findIndex(
      (it) => it.ingredient_key === preparedItem.ingredient_key,
    );
    let nextItems: BazarItem[];
    if (existingIdx >= 0) {
      nextItems = plan.items.map((it, idx) =>
        idx === existingIdx
          ? {
              ...it,
              qty: Math.round((it.qty + preparedItem.qty) * 100) / 100,
              est_price_bdt:
                Math.round((it.est_price_bdt + preparedItem.est_price_bdt) * 100) / 100,
              dropped: false,
              flag: preparedItem.flag,
            }
          : it,
      );
    } else {
      nextItems = [...plan.items, preparedItem];
    }

    recalcPlanItems(nextItems, "draft");
    setAddOpen(false);
    setPrediction(null);
    showToast(t("bazar.itemAddedToast", { name: preparedItem.name_bn }), "success");
  }

  function openPurchaseSheet() {
    if (!plan) return;
    const draft: Record<string, { included: boolean; qty: string; price: string }> = {};
    for (const it of plan.items) {
      if (!it.dropped && !it.ingredient_key.startsWith("custom_")) {
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

  function sourceLabel(src: string): string {
    if (src === "user_purchase") return t("bazar.sourceUserPurchase");
    if (src === "reference_table") return t("bazar.sourceReference");
    if (src === "ai_market_estimate") return t("bazar.sourceAiEstimate");
    return t("bazar.sourceMissing");
  }

  if (!session) return <AuthGuardNotice />;

  const includedCount = plan ? plan.items.filter((it) => !it.dropped).length : 0;
  const anyDropped = plan ? plan.items.some((it) => it.dropped) : false;

  const effectivePreviewPrice = prediction
    ? Math.max(0, Number(priceOverride !== "" ? priceOverride : prediction.item.est_price_bdt) || 0)
    : 0;
  const liveProjectedTotal = plan
    ? Math.round((plan.est_total_bdt + effectivePreviewPrice) * 100) / 100
    : effectivePreviewPrice;
  const liveOverBudget = plan ? liveProjectedTotal > plan.budget_bdt : false;
  const liveDelta = plan ? Math.round((liveProjectedTotal - plan.budget_bdt) * 100) / 100 : 0;

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
                  <Badge
                    variant={plan.status === "confirmed" ? "SAFE_DIRECT" : "INFO"}
                    label={
                      plan.status === "confirmed" ? t("bazar.confirmedBadge") : t("bazar.draftBadge")
                    }
                  />
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button variant="primary" onClick={handleConfirmList} disabled={confirming} data-testid="bazar-confirm-btn">
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

          {/* Pre-Approval Checklist Toolbar + Add Extra Item CTA */}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2.5">
              <span className="text-sm font-bold flex items-center gap-1.5" style={{ color: "var(--text)" }}>
                <CheckSquare className="h-4 w-4" style={{ color: "var(--accent)" }} aria-hidden="true" />
                <span>
                  {t("bazar.selectedSummary", {
                    selected: includedCount,
                    total: plan.items.length,
                  })}
                </span>
              </span>
              {anyDropped && (
                <Button
                  variant="ghost"
                  className="!min-h-[36px] !px-3 !py-1 !text-xs"
                  onClick={selectAllItems}
                >
                  {t("bazar.selectAllBtn")}
                </Button>
              )}
            </div>

            <Button
              variant="primary"
              className="!min-h-[42px] !px-4 !py-2 !text-xs"
              onClick={openAddItemSheet}
              data-testid="bazar-add-item-btn"
            >
              <Plus className="h-4 w-4" aria-hidden="true" />
              <span>{t("bazar.addItemBtn")}</span>
            </Button>
          </div>

          {/* Bazar Item Grid with Explicit Pre-Approval Checkboxes */}
          <div className="grid gap-3 sm:grid-cols-2">
            {plan.items.map((it) => {
              const checked = !it.dropped;
              return (
                <Card
                  key={it.ingredient_key}
                  variant={it.dropped ? "inset" : "raised"}
                  className="flex flex-col justify-between gap-3"
                  style={it.dropped ? { opacity: 0.72 } : undefined}
                >
                  <div className="flex items-start justify-between gap-3">
                    <label className="flex items-start gap-2.5 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggleDropItem(it.ingredient_key)}
                        aria-label={`${t("bazar.includeCheckboxLabel")}: ${pickLocalized(it.name_bn, prettifyKey(it.ingredient_key))}`}
                        className="mt-1 h-4.5 w-4.5 shrink-0 accent-[var(--accent)] cursor-pointer"
                        data-testid={`bazar-item-check-${it.ingredient_key}`}
                      />
                      <div>
                        <h2
                          className={`text-base font-extrabold ${it.dropped ? "line-through" : ""}`}
                          style={{ color: "var(--text)" }}
                        >
                          {pickLocalized(it.name_bn, prettifyKey(it.ingredient_key))}
                        </h2>
                        <p className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                          {formatNumber(it.qty)} {it.unit} • {it.category}
                        </p>
                      </div>
                    </label>
                    <div className="text-right shrink-0">
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
              );
            })}
          </div>
        </div>
      )}

      {/* 2-Step Add Extra Item & Price Prediction Sheet */}
      <Sheet
        open={addOpen}
        onClose={() => setAddOpen(false)}
        title={t("bazar.addItemSheetTitle")}
      >
        <div className="space-y-4">
          <p className="text-xs leading-relaxed" style={{ color: "var(--text-muted)" }}>
            {t("bazar.addItemSheetDesc")}
          </p>

          {/* Verified vs Custom Mode Toggle */}
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => {
                setAddMode("verified");
                setUseAiEstimate(false);
                setPrediction(null);
                const found = stockOptions.find((s) => s.ingredient_key === addIngKey);
                if (found) {
                  setAddUnit((found.base_unit as "g" | "ml" | "piece") || "g");
                  setAddQty(found.base_unit === "piece" ? "4" : "500");
                }
              }}
              className={`min-h-[40px] rounded-[12px] px-3 py-1.5 text-xs font-bold cursor-pointer ${
                addMode === "verified" ? "skeu-button" : "neu-raised-sm"
              }`}
              style={addMode === "verified" ? undefined : { color: "var(--text)" }}
            >
              {t("bazar.modeVerified")}
            </button>
            <button
              type="button"
              onClick={() => {
                setAddMode("custom");
                setUseAiEstimate(true);
                setPrediction(null);
              }}
              className={`min-h-[40px] rounded-[12px] px-3 py-1.5 text-xs font-bold cursor-pointer ${
                addMode === "custom" ? "skeu-button" : "neu-raised-sm"
              }`}
              style={addMode === "custom" ? undefined : { color: "var(--text)" }}
              data-testid="bazar-mode-custom"
            >
              {t("bazar.modeCustom")}
            </button>
          </div>

          <form onSubmit={handlePredictPrice} className="space-y-3">
            {addMode === "verified" ? (
              <div className="space-y-1.5">
                <label htmlFor="bazar-add-ing" className="block text-sm font-semibold" style={{ color: "var(--text)" }}>
                  {t("bazar.selectIngredientLabel")}
                </label>
                <select
                  id="bazar-add-ing"
                  value={addIngKey}
                  onChange={(e) => {
                    const nextKey = e.target.value;
                    setAddIngKey(nextKey);
                    setPrediction(null);
                    const found = stockOptions.find((s) => s.ingredient_key === nextKey);
                    if (found) {
                      setAddUnit((found.base_unit as "g" | "ml" | "piece") || "g");
                      setAddQty(found.base_unit === "piece" ? "4" : "500");
                    }
                  }}
                  className="neu-inset w-full min-h-[44px] px-3 py-2 text-sm"
                  style={{ color: "var(--text)" }}
                  data-testid="bazar-add-select"
                >
                  {stockOptions.map((s) => (
                    <option key={s.ingredient_key} value={s.ingredient_key}>
                      {pickLocalized(s.name_bn, s.name_en)} ({s.base_unit})
                    </option>
                  ))}
                </select>
              </div>
            ) : (
              <Input
                label={t("bazar.customItemNameLabel")}
                placeholder={t("bazar.customItemNamePlaceholder")}
                value={customName}
                onChange={(e) => {
                  setCustomName(e.target.value);
                  setPrediction(null);
                }}
                required
                data-testid="bazar-custom-name"
              />
            )}

            <div className="grid grid-cols-2 gap-3">
              <Input
                label={t("bazar.itemQtyLabel")}
                type="number"
                min={1}
                step="any"
                value={addQty}
                onChange={(e) => {
                  setAddQty(e.target.value);
                  setPrediction(null);
                }}
                required
                data-testid="bazar-add-qty"
              />
              <div className="space-y-1.5">
                <label htmlFor="bazar-add-unit" className="block text-sm font-semibold" style={{ color: "var(--text)" }}>
                  {t("bazar.itemUnitLabel")}
                </label>
                <select
                  id="bazar-add-unit"
                  value={addUnit}
                  disabled={addMode === "verified"}
                  onChange={(e) => {
                    setAddUnit(e.target.value as "g" | "ml" | "piece");
                    setPrediction(null);
                  }}
                  className="neu-inset w-full min-h-[46px] px-3 py-2 text-sm disabled:opacity-65"
                  style={{ color: "var(--text)" }}
                >
                  <option value="g">g</option>
                  <option value="ml">ml</option>
                  <option value="piece">piece</option>
                </select>
              </div>
            </div>

            <label className="flex items-start gap-2.5 text-xs font-medium cursor-pointer">
              <input
                type="checkbox"
                checked={useAiEstimate}
                onChange={(e) => {
                  setUseAiEstimate(e.target.checked);
                  setPrediction(null);
                }}
                className="mt-0.5 h-4 w-4 accent-[var(--accent)]"
              />
              <span style={{ color: "var(--text)" }}>{t("bazar.useAiEstimateLabel")}</span>
            </label>

            <Button
              type="submit"
              variant="neu"
              fullWidth
              disabled={predicting || (addMode === "custom" && !customName.trim())}
              data-testid="bazar-predict-btn"
            >
              <Sparkles className="h-4 w-4" style={{ color: "var(--accent)" }} aria-hidden="true" />
              <span>{predicting ? t("common.loading") : t("bazar.predictBtn")}</span>
            </Button>
          </form>

          {/* Prediction Preview Box — user reviews price, budget impact, & safety before confirming */}
          {prediction && (
            <div className="neu-inset p-4 space-y-3" data-testid="bazar-prediction-preview">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm font-extrabold" style={{ color: "var(--text)" }}>
                  {t("bazar.previewTitle")}
                </p>
                <Badge
                  variant={prediction.used_ai ? "ESTIMATED" : "SAFE_DIRECT"}
                  label={sourceLabel(prediction.prediction_source)}
                />
              </div>

              <div className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                    {t("bazar.predictedPriceLabel")}
                  </p>
                  <p className="text-lg font-extrabold font-mono" style={{ color: "var(--accent)" }}>
                    {formatNumber(effectivePreviewPrice)} {t("common.bdt")}
                  </p>
                </div>
                <div>
                  <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                    {t("bazar.projectedTotalLabel")}
                  </p>
                  <p
                    className="text-lg font-extrabold font-mono"
                    style={{ color: liveOverBudget ? "var(--saffron-text)" : "var(--ok)" }}
                  >
                    {formatNumber(liveProjectedTotal)} {t("common.bdt")}
                  </p>
                </div>
              </div>

              {(prediction.market_note_bn || prediction.market_note_en) && (
                <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                  {pickLocalized(prediction.market_note_bn, prediction.market_note_en)}
                </p>
              )}

              <p
                className="text-xs font-bold"
                style={{ color: liveOverBudget ? "var(--saffron-text)" : "var(--ok)" }}
              >
                {liveOverBudget
                  ? t("bazar.overBudgetDeltaNote", { delta: liveDelta })
                  : t("bazar.withinBudgetNote")}
              </p>

              {prediction.safety_warnings.length > 0 && (
                <div className="rounded-[12px] border border-[var(--danger)] p-3 space-y-1.5">
                  <p className="text-xs font-bold flex items-center gap-1.5" style={{ color: "var(--danger)" }}>
                    <AlertTriangle className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                    <span>{t("bazar.safetyWarningTitle")}</span>
                  </p>
                  {prediction.safety_warnings.map((w, i) => (
                    <p key={i} className="text-xs" style={{ color: "var(--text)" }}>
                      <strong>{w.member_name}</strong> ({t(`status.${w.status}`)}) ·{" "}
                      <span className="font-mono">{w.reasons.join(", ")}</span>
                    </p>
                  ))}
                </div>
              )}

              <Input
                label={t("bazar.overridePriceLabel")}
                type="number"
                min={0}
                step="any"
                value={priceOverride}
                onChange={(e) => setPriceOverride(e.target.value)}
                data-testid="bazar-override-price"
              />

              <Button
                type="button"
                variant="primary"
                fullWidth
                onClick={handleConfirmAddItem}
                data-testid="bazar-confirm-add-btn"
              >
                <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
                <span>{t("bazar.confirmAddBtn")}</span>
              </Button>
            </div>
          )}
        </div>
      </Sheet>

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
                .filter((it) => !it.dropped && !it.ingredient_key.startsWith("custom_"))
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
