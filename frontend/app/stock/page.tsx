"use client";

import React, { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Package, SlidersHorizontal } from "lucide-react";
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

  if (!session) return <AuthGuardNotice />;

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl sm:text-3xl font-extrabold" style={{ color: "var(--text)" }}>
          {t("stock.title")}
        </h1>
        <p className="text-sm sm:text-base" style={{ color: "var(--text-muted)" }}>
          {t("stock.subtitle")}
        </p>
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
    </div>
  );
}

