"use client";

import React, { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Package, Plus, SlidersHorizontal } from "lucide-react";
import { AuthGuardNotice } from "@/components/AuthGuardNotice";
import { Badge, Button, Card, Input, Sheet, Skeleton, Toggle, useToast } from "@/components/ui";
import { ApiError, harborApi, StockItem } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useSession } from "@/lib/session";

export default function StockPage() {
  const { locale, formatNumber, pickLocalized, t } = useI18n();
  const { session } = useSession();
  const { showToast } = useToast();

  const [items, setItems] = useState<StockItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("all");
  const [inStockOnly, setInStockOnly] = useState(false);

  const [adjustItem, setAdjustItem] = useState<StockItem | null>(null);
  const [targetQty, setTargetQty] = useState("");
  const [adjustNote, setAdjustNote] = useState("");
  const [savingAdjust, setSavingAdjust] = useState(false);

  const [quickAddOpen, setQuickAddOpen] = useState(false);
  const [quickAddKey, setQuickAddKey] = useState("");
  const [quickAddQty, setQuickAddQty] = useState("500");
  const [quickAddPrice, setQuickAddPrice] = useState("");
  const [quickAddNote, setQuickAddNote] = useState("");
  const [savingQuickAdd, setSavingQuickAdd] = useState(false);

  useEffect(() => {
    if (!session) return;
    let cancelled = false;
    harborApi
      .getStock(session.token, locale)
      .then((res) => {
        if (!cancelled) {
          setItems(res.items);
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

  const categories = useMemo(() => {
    const set = new Set(items.map((it) => it.category));
    return ["all", ...Array.from(set).sort()];
  }, [items]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return items.filter((it) => {
      if (category !== "all" && it.category !== category) return false;
      if (inStockOnly && it.qty_base <= 0) return false;
      if (!q) return true;
      return (
        it.name_bn.toLowerCase().includes(q) ||
        it.name_en.toLowerCase().includes(q) ||
        it.ingredient_key.toLowerCase().includes(q)
      );
    });
  }, [items, search, category, inStockOnly]);

  async function handleSaveAdjust(e: React.FormEvent) {
    e.preventDefault();
    if (!session || !adjustItem) return;
    const numericQty = Math.max(0, Number(targetQty) || 0);
    setSavingAdjust(true);
    try {
      const res = await harborApi.adjustStock(
        adjustItem.ingredient_key,
        numericQty,
        adjustNote.trim() || undefined,
        session.token,
        locale,
      );
      setItems((prev) =>
        prev.map((it) =>
          it.ingredient_key === adjustItem.ingredient_key
            ? { ...it, qty_base: res.new_qty, clamped_negative: false }
            : it,
        ),
      );
      showToast(
        t("stock.adjustSuccess", { qty: res.new_qty, unit: res.unit }),
        "success",
      );
      setAdjustItem(null);
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("common.errorUnexpected"), "error");
    } finally {
      setSavingAdjust(false);
    }
  }

  const selectedQuickItem = useMemo(
    () => items.find((it) => it.ingredient_key === quickAddKey) || items[0] || null,
    [items, quickAddKey],
  );

  function openQuickAddSheet() {
    const first = selectedQuickItem || items[0] || null;
    if (first && !quickAddKey) {
      setQuickAddKey(first.ingredient_key);
      setQuickAddQty(first.base_unit === "piece" ? "4" : "500");
    }
    setQuickAddPrice("");
    setQuickAddNote("");
    setQuickAddOpen(true);
  }

  async function handleQuickAdd(e: React.FormEvent) {
    e.preventDefault();
    if (!session || !selectedQuickItem) return;
    const numericQty = Number(quickAddQty);
    if (!numericQty || numericQty <= 0) return;
    const numericPrice = quickAddPrice.trim() ? Number(quickAddPrice) : null;
    setSavingQuickAdd(true);
    try {
      const res = await harborApi.quickAddStock(
        {
          ingredient_key: selectedQuickItem.ingredient_key,
          qty_base: numericQty,
          price_bdt: numericPrice && numericPrice > 0 ? numericPrice : null,
          note: quickAddNote.trim() || undefined,
        },
        session.token,
        locale,
      );
      setItems((prev) =>
        prev.map((it) =>
          it.ingredient_key === res.ingredient_key
            ? {
                ...it,
                qty_base: res.new_qty,
                last_purchased_at: res.last_purchased_at ?? it.last_purchased_at,
                clamped_negative: false,
              }
            : it,
        ),
      );
      showToast(
        t("stock.quickAddSuccess", {
          added: res.added_qty,
          total: res.new_qty,
          unit: res.unit,
        }),
        "success",
      );
      setQuickAddOpen(false);
      setQuickAddPrice("");
      setQuickAddNote("");
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("common.errorUnexpected"), "error");
    } finally {
      setSavingQuickAdd(false);
    }
  }

  if (!session) return <AuthGuardNotice />;

  const quickPresets =
    selectedQuickItem?.base_unit === "piece" ? [2, 4, 6] : [250, 500, 1000];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl sm:text-3xl font-extrabold" style={{ color: "var(--text)" }}>
            {t("stock.title")}
          </h1>
          <p className="text-sm sm:text-base" style={{ color: "var(--text-muted)" }}>
            {t("stock.subtitle")}
          </p>
        </div>
        <Button
          variant="primary"
          onClick={openQuickAddSheet}
          disabled={loading || items.length === 0}
          data-testid="stock-quick-add-btn"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          <span>{t("stock.quickAddBtn")}</span>
        </Button>
      </div>

      {/* Filters */}
      <Card variant="raised" className="space-y-4">
        <Input
          label={t("stock.searchLabel")}
          placeholder={t("stock.searchPlaceholder")}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          data-testid="stock-search-input"
        />

        <div className="flex flex-wrap gap-2">
          {categories.map((cat) => {
            const active = cat === category;
            return (
              <button
                key={cat}
                type="button"
                onClick={() => setCategory(cat)}
                className={`min-h-[40px] rounded-full px-3.5 py-1.5 text-xs font-bold cursor-pointer ${
                  active ? "skeu-button" : "neu-raised-sm"
                }`}
                style={active ? undefined : { color: "var(--text)" }}
              >
                {cat === "all" ? t("stock.categoryAll") : cat}
              </button>
            );
          })}
        </div>

        <Toggle
          checked={inStockOnly}
          onChange={setInStockOnly}
          label={t("stock.inStockOnly")}
        />
      </Card>

      {errorMsg && (
        <Card variant="glass">
          <p className="text-sm font-semibold" style={{ color: "var(--danger)" }}>
            {errorMsg}
          </p>
        </Card>
      )}

      {loading ? (
        <div className="grid gap-3 sm:grid-cols-2">
          <Skeleton className="h-28 rounded-[18px]" />
          <Skeleton className="h-28 rounded-[18px]" />
          <Skeleton className="h-28 rounded-[18px]" />
          <Skeleton className="h-28 rounded-[18px]" />
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {filtered.map((item) => (
            <Card key={item.ingredient_key} variant="raised" className="flex flex-col justify-between gap-3">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <h2 className="text-base font-extrabold flex items-center gap-1.5" style={{ color: "var(--text)" }}>
                    <Package className="h-4 w-4 shrink-0" style={{ color: "var(--accent)" }} aria-hidden="true" />
                    <span>{pickLocalized(item.name_bn, item.name_en)}</span>
                  </h2>
                  <p className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                    {item.category} • {item.ingredient_key}
                  </p>
                </div>
                <span className="text-lg font-extrabold font-mono" style={{ color: "var(--accent)" }}>
                  {formatNumber(item.qty_base)} {item.base_unit}
                </span>
              </div>

              <div className="flex flex-wrap gap-1.5">
                {item.near_expiry && (
                  <Badge variant="SAFE_WITH_SPLIT" label={t("stock.nearExpiryBadge")} />
                )}
                {item.clamped_negative && (
                  <Badge variant="ESTIMATED" label={t("stock.clampedBadge")} />
                )}
              </div>

              <div className="flex items-center justify-between gap-2 pt-1 border-t border-[var(--border-subtle)]">
                <span className="text-xs flex items-center gap-1" style={{ color: "var(--text-muted)" }}>
                  {item.near_expiry && <AlertTriangle className="h-3.5 w-3.5" style={{ color: "var(--saffron-text)" }} aria-hidden="true" />}
                  {item.last_purchased_at
                    ? `${t("stock.lastPurchased")}: ${new Date(item.last_purchased_at).toLocaleDateString()}`
                    : t("stock.neverPurchased")}
                </span>
                <Button
                  variant="neu"
                  className="!min-h-[40px] !px-3 !py-1.5 !text-xs"
                  onClick={() => {
                    setAdjustItem(item);
                    setTargetQty(String(item.qty_base));
                    setAdjustNote("");
                  }}
                >
                  <SlidersHorizontal className="h-3.5 w-3.5" aria-hidden="true" />
                  <span>{t("stock.adjustBtn")}</span>
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Adjust Stock Sheet */}
      <Sheet
        open={Boolean(adjustItem)}
        onClose={() => setAdjustItem(null)}
        title={t("stock.adjustSheetTitle")}
      >
        {adjustItem && (
          <form onSubmit={handleSaveAdjust} className="space-y-4">
            <p className="text-base font-bold" style={{ color: "var(--text)" }}>
              {pickLocalized(adjustItem.name_bn, adjustItem.name_en)} ({adjustItem.base_unit})
            </p>
            <Input
              label={`${t("stock.targetQtyLabel")} (${adjustItem.base_unit})`}
              type="number"
              min={0}
              step="any"
              value={targetQty}
              onChange={(e) => setTargetQty(e.target.value)}
              required
              data-testid="stock-adjust-qty-input"
            />
            <Input
              label={t("stock.adjustNoteLabel")}
              value={adjustNote}
              onChange={(e) => setAdjustNote(e.target.value)}
            />
            <div className="flex justify-end gap-3">
              <Button variant="ghost" onClick={() => setAdjustItem(null)}>
                {t("common.cancel")}
              </Button>
              <Button type="submit" variant="primary" disabled={savingAdjust}>
                {savingAdjust ? t("common.loading") : t("common.save")}
              </Button>
            </div>
          </form>
        )}
      </Sheet>

      {/* Quick Add Verified Ingredient Sheet */}
      <Sheet
        open={quickAddOpen}
        onClose={() => setQuickAddOpen(false)}
        title={t("stock.quickAddTitle")}
      >
        <form onSubmit={handleQuickAdd} className="space-y-4">
          <p className="text-xs leading-relaxed" style={{ color: "var(--text-muted)" }}>
            {t("stock.quickAddDesc")}
          </p>

          <div className="space-y-1.5">
            <label
              htmlFor="quick-add-ingredient"
              className="block text-sm font-semibold"
              style={{ color: "var(--text)" }}
            >
              {t("stock.quickAddSelectLabel")}
            </label>
            <select
              id="quick-add-ingredient"
              value={selectedQuickItem?.ingredient_key || ""}
              onChange={(e) => {
                const nextKey = e.target.value;
                setQuickAddKey(nextKey);
                const found = items.find((it) => it.ingredient_key === nextKey);
                if (found) {
                  setQuickAddQty(found.base_unit === "piece" ? "4" : "500");
                }
              }}
              className="neu-inset w-full min-h-[46px] px-3 py-2 text-sm"
              style={{ color: "var(--text)" }}
              data-testid="stock-quick-add-select"
            >
              {items.map((it) => (
                <option key={it.ingredient_key} value={it.ingredient_key}>
                  {pickLocalized(it.name_bn, it.name_en)} ({formatNumber(it.qty_base)} {it.base_unit})
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-2">
            <Input
              label={`${t("stock.quickAddQtyLabel")} (${selectedQuickItem?.base_unit || "g"})`}
              type="number"
              min={1}
              step="any"
              value={quickAddQty}
              onChange={(e) => setQuickAddQty(e.target.value)}
              required
              data-testid="stock-quick-add-qty"
            />
            <div className="flex flex-wrap gap-2">
              {quickPresets.map((presetVal) => (
                <button
                  key={presetVal}
                  type="button"
                  onClick={() => setQuickAddQty(String(presetVal))}
                  className="neu-raised-sm min-h-[36px] px-3 py-1 text-xs font-bold cursor-pointer"
                  style={{ color: "var(--text)" }}
                >
                  +{formatNumber(presetVal)} {selectedQuickItem?.base_unit || "g"}
                </button>
              ))}
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <Input
              label={t("stock.quickAddPriceLabel")}
              type="number"
              min={0}
              step="any"
              value={quickAddPrice}
              onChange={(e) => setQuickAddPrice(e.target.value)}
            />
            <Input
              label={t("stock.quickAddNoteLabel")}
              value={quickAddNote}
              onChange={(e) => setQuickAddNote(e.target.value)}
            />
          </div>

          <div className="flex justify-end gap-3 pt-1">
            <Button variant="ghost" onClick={() => setQuickAddOpen(false)}>
              {t("common.cancel")}
            </Button>
            <Button
              type="submit"
              variant="primary"
              disabled={savingQuickAdd || !selectedQuickItem}
              data-testid="stock-quick-add-submit"
            >
              {savingQuickAdd ? t("common.loading") : t("stock.quickAddSubmit")}
            </Button>
          </div>
        </form>
      </Sheet>
    </div>
  );
}

