"use client";

import React, { useEffect, useState } from "react";
import { Cpu, Play } from "lucide-react";
import { Badge, Button, Card, Input, Skeleton, Tabs, useToast } from "@/components/ui";
import {
  AgeGroup,
  ApiError,
  DrugClass,
  EngineCatalogResponse,
  EngineCheckResponse,
  harborApi,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useSession } from "@/lib/session";

export default function EngineExplorerPage() {
  const { locale, pickLocalized, t } = useI18n();
  const { session } = useSession();
  const { showToast } = useToast();

  const [catalog, setCatalog] = useState<EngineCatalogResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);

  const [mode, setMode] = useState<"member" | "custom">("custom");
  const [selectedMemberId, setSelectedMemberId] = useState("");
  const [selectedRecipeKey, setSelectedRecipeKey] = useState("");

  const [customName, setCustomName] = useState("Test Profile");
  const [customAge, setCustomAge] = useState<AgeGroup>("adult");
  const [customPresets, setCustomPresets] = useState<string[]>(["low_potassium"]);
  const [customAllergies, setCustomAllergies] = useState<string[]>([]);
  const [customDrugs, setCustomDrugs] = useState<DrugClass[]>(["ace_inhibitor"]);

  const [result, setResult] = useState<EngineCheckResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    harborApi
      .getEngineCatalog(session?.token, locale)
      .then((res) => {
        if (cancelled) return;
        setCatalog(res);
        if (res.recipes.length > 0) setSelectedRecipeKey(res.recipes[0].key);
        if (res.members.length > 0) {
          setSelectedMemberId(res.members[0].id);
          setMode("member");
        }
        setLoading(false);
      })
      .catch(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [session?.token, locale]);

  function toggle<T extends string>(list: T[], val: T, setter: (next: T[]) => void) {
    setter(list.includes(val) ? list.filter((x) => x !== val) : [...list, val]);
  }

  async function handleRun() {
    if (!selectedRecipeKey) return;
    setRunning(true);
    try {
      const payload =
        mode === "member" && selectedMemberId
          ? { member_id: selectedMemberId, recipe_key: selectedRecipeKey }
          : {
              recipe_key: selectedRecipeKey,
              custom_member: {
                name: customName.trim() || "Custom Member",
                role: "patient",
                age_group: customAge,
                presets: customPresets,
                diet_presets: customPresets,
                allergies: customAllergies,
                medicines: customDrugs.map((dc) => ({
                  name_as_written: dc,
                  drug_class: dc,
                  verified_by_caregiver: true,
                  active: true,
                })),
              },
            };
      const res = await harborApi.checkEngineRuleTrace(payload, session?.token, locale);
      setResult(res);
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("common.errorUnexpected"), "error");
    } finally {
      setRunning(false);
    }
  }

  function mapStatusVariant(status: string) {
    if (status === "SAFE_DIRECT") return "SAFE_DIRECT" as const;
    if (status === "SAFE_WITH_SPLIT") return "SAFE_WITH_SPLIT" as const;
    if (status === "UNVERIFIED") return "UNVERIFIED" as const;
    return "BLOCKED" as const;
  }

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl sm:text-3xl font-extrabold" style={{ color: "var(--text)" }}>
          {t("engine.title")}
        </h1>
        <p className="text-sm sm:text-base" style={{ color: "var(--text-muted)" }}>
          {t("engine.subtitle")}
        </p>
      </div>

      {loading ? (
        <Skeleton className="h-64 rounded-[20px]" />
      ) : catalog ? (
        <Card variant="raised" className="space-y-5">
          {catalog.members.length > 0 && (
            <Tabs
              value={mode}
              onChange={(m) => setMode(m as "member" | "custom")}
              options={[
                { id: "member", label: t("engine.modeMember") },
                { id: "custom", label: t("engine.modeCustom") },
              ]}
            />
          )}

          <div className="grid gap-4 sm:grid-cols-2">
            {mode === "member" && catalog.members.length > 0 ? (
              <div className="space-y-1.5">
                <label htmlFor="engine-member-select" className="block text-sm font-semibold" style={{ color: "var(--text)" }}>
                  {t("engine.memberSelectLabel")}
                </label>
                <select
                  id="engine-member-select"
                  value={selectedMemberId}
                  onChange={(e) => setSelectedMemberId(e.target.value)}
                  className="neu-inset w-full min-h-[48px] px-3 py-2 text-sm"
                  style={{ color: "var(--text)" }}
                  data-testid="engine-member-select"
                >
                  {catalog.members.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name} ({t(`members.roles.${m.role}`)})
                    </option>
                  ))}
                </select>
              </div>
            ) : (
              <Input
                label={t("engine.customNameLabel")}
                value={customName}
                onChange={(e) => setCustomName(e.target.value)}
              />
            )}

            <div className="space-y-1.5">
              <label htmlFor="engine-recipe-select" className="block text-sm font-semibold" style={{ color: "var(--text)" }}>
                {t("engine.recipeSelectLabel", { count: catalog.recipes.length })}
              </label>
              <select
                id="engine-recipe-select"
                value={selectedRecipeKey}
                onChange={(e) => setSelectedRecipeKey(e.target.value)}
                className="neu-inset w-full min-h-[48px] px-3 py-2 text-sm"
                style={{ color: "var(--text)" }}
                data-testid="engine-recipe-select"
              >
                {catalog.recipes.map((r) => (
                  <option key={r.key} value={r.key}>
                    {pickLocalized(r.name_bn, r.name_en)}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {mode === "custom" && (
            <div className="space-y-4 pt-2 border-t border-[var(--border-subtle)]">
              <div className="space-y-1.5">
                <label htmlFor="engine-custom-age-select" className="block text-sm font-semibold" style={{ color: "var(--text)" }}>
                  {t("engine.customAgeLabel")}
                </label>
                <select
                  id="engine-custom-age-select"
                  value={customAge}
                  onChange={(e) => setCustomAge(e.target.value as AgeGroup)}
                  className="neu-inset w-full min-h-[48px] px-3 py-2 text-sm"
                  style={{ color: "var(--text)" }}
                >
                  {catalog.age_groups.map((ag) => (
                    <option key={ag} value={ag}>
                      {t(`members.ageGroups.${ag}`)}
                    </option>
                  ))}
                </select>
              </div>

              <div className="space-y-1.5">
                <p className="text-sm font-semibold" style={{ color: "var(--text)" }}>
                  {t("members.presetsLabel")}
                </p>
                <div className="flex flex-wrap gap-2">
                  {catalog.presets.map((pk) => {
                    const active = customPresets.includes(pk);
                    return (
                      <button
                        key={pk}
                        type="button"
                        onClick={() => toggle(customPresets, pk, setCustomPresets)}
                        className={`min-h-[38px] rounded-full px-3 py-1 text-xs font-bold cursor-pointer ${
                          active ? "skeu-button" : "neu-raised-sm"
                        }`}
                        style={active ? undefined : { color: "var(--text)" }}
                      >
                        {t(`members.presets.${pk}`)}
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="space-y-1.5">
                <p className="text-sm font-semibold" style={{ color: "var(--text)" }}>
                  {t("members.allergiesLabel")}
                </p>
                <div className="flex flex-wrap gap-2">
                  {catalog.allergens.map((ak) => {
                    const active = customAllergies.includes(ak);
                    return (
                      <button
                        key={ak}
                        type="button"
                        onClick={() => toggle(customAllergies, ak, setCustomAllergies)}
                        className={`min-h-[38px] rounded-full px-3 py-1 text-xs font-bold cursor-pointer ${
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

              <div className="space-y-1.5">
                <p className="text-sm font-semibold" style={{ color: "var(--text)" }}>
                  {t("engine.customDrugsLabel")}
                </p>
                <div className="flex flex-wrap gap-2">
                  {catalog.drug_classes.map((dc) => {
                    const active = customDrugs.includes(dc);
                    return (
                      <button
                        key={dc}
                        type="button"
                        onClick={() => toggle(customDrugs, dc, setCustomDrugs)}
                        className={`min-h-[38px] rounded-full px-3 py-1 text-xs font-bold cursor-pointer font-mono ${
                          active ? "skeu-button" : "neu-raised-sm"
                        }`}
                        style={active ? undefined : { color: "var(--text)" }}
                      >
                        {dc}
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          )}

          <Button
            variant="primary"
            onClick={handleRun}
            disabled={running}
            data-testid="engine-run-btn"
          >
            <Play className="h-4 w-4" aria-hidden="true" />
            <span>{running ? t("common.loading") : t("engine.runCheckBtn")}</span>
          </Button>
        </Card>
      ) : null}

      {result && (
        <Card variant="raised" className="space-y-5" data-testid="engine-result-card">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <Cpu className="h-5 w-5" style={{ color: "var(--accent)" }} aria-hidden="true" />
              <div>
                <h2 className="text-lg font-extrabold" style={{ color: "var(--text)" }}>
                  {pickLocalized(result.recipe_name_bn, result.recipe_name_en)} — {result.member_name}
                </h2>
                <p className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                  {t("engine.resultTitle")}
                </p>
              </div>
            </div>
            <Badge variant={mapStatusVariant(result.status)} />
          </div>

          {result.split_step_bn && (
            <div className="neu-inset p-3.5 text-sm font-semibold" style={{ color: "var(--saffron-text)" }}>
              {result.split_step_bn}
            </div>
          )}

          {result.reasons.length > 0 && (
            <div className="space-y-1.5">
              <h3 className="text-sm font-bold" style={{ color: "var(--text)" }}>
                {t("engine.reasonsTitle")}
              </h3>
              <div className="flex flex-wrap gap-2">
                {result.reasons.map((r, i) => (
                  <span key={i} className="neu-inset px-3 py-1 font-mono text-xs" style={{ color: "var(--text)" }}>
                    {r}
                  </span>
                ))}
              </div>
            </div>
          )}

          <div className="space-y-2">
            <h3 className="text-sm font-bold" style={{ color: "var(--text)" }}>
              {t("engine.traceTitle")}
            </h3>
            <ol className="neu-inset p-4 space-y-1.5 font-mono text-xs" style={{ color: "var(--text)" }}>
              {result.trace.map((line, i) => (
                <li key={i}>{line}</li>
              ))}
            </ol>
          </div>

          <div tabIndex={0} className="space-y-2 overflow-x-auto">
            <h3 className="text-sm font-bold" style={{ color: "var(--text)" }}>
              {t("engine.ingredientsTitle")}
            </h3>
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-[var(--border-strong)]" style={{ color: "var(--text-muted)" }}>
                  <th className="py-2 pr-3">{t("engine.colIngredient")}</th>
                  <th className="py-2 pr-3">{t("engine.colPotassium")}</th>
                  <th className="py-2 pr-3">{t("engine.colPurine")}</th>
                  <th className="py-2 pr-3">{t("engine.colSodium")}</th>
                  <th className="py-2 pr-3">{t("engine.colGi")}</th>
                  <th className="py-2">{t("engine.colAllergens")}</th>
                </tr>
              </thead>
              <tbody>
                {result.ingredients.map((ing) => (
                  <tr key={ing.key} className="border-b border-[var(--border-subtle)]" style={{ color: "var(--text)" }}>
                    <td className="py-2 pr-3 font-semibold">{pickLocalized(ing.name_bn, ing.name_en)}</td>
                    <td className="py-2 pr-3 font-mono">{ing.potassium_level || "-"}</td>
                    <td className="py-2 pr-3 font-mono">{ing.purine_level || "-"}</td>
                    <td className="py-2 pr-3 font-mono">{ing.sodium_level || "-"}</td>
                    <td className="py-2 pr-3 font-mono">{ing.gi_level || "-"}</td>
                    <td className="py-2 font-mono">{ing.allergen_tags.join(", ") || "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}

