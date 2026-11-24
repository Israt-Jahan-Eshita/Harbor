"use client";

import React, { useEffect, useState } from "react";
import { CheckCircle2, Cpu, Play, Scale, ShieldAlert, Users } from "lucide-react";
import { Badge, Button, Card, Input, Skeleton, Tabs, useToast } from "@/components/ui";
import {
  AgeGroup,
  ApiError,
  DrugClass,
  EngineCatalogResponse,
  EngineCheckResponse,
  EngineConflictCheckResponse,
  harborApi,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useSession } from "@/lib/session";

interface ConflictDraftMember {
  name: string;
  age_group: AgeGroup;
  diet_presets: string[];
  allergies: string[];
  drugs: DrugClass[];
}

export default function EngineExplorerPage() {
  const { locale, pickLocalized, t } = useI18n();
  const { session } = useSession();
  const { showToast } = useToast();

  const [catalog, setCatalog] = useState<EngineCatalogResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);

  const [explorerTab, setExplorerTab] = useState<"single" | "conflict">("single");

  // Single-member mode state
  const [mode, setMode] = useState<"member" | "custom">("custom");
  const [selectedMemberId, setSelectedMemberId] = useState("");
  const [selectedRecipeKey, setSelectedRecipeKey] = useState("");
  const [customName, setCustomName] = useState("Test Profile");
  const [customAge, setCustomAge] = useState<AgeGroup>("adult");
  const [customPresets, setCustomPresets] = useState<string[]>(["low_potassium"]);
  const [customAllergies, setCustomAllergies] = useState<string[]>([]);
  const [customDrugs, setCustomDrugs] = useState<DrugClass[]>(["ace_inhibitor"]);
  const [result, setResult] = useState<EngineCheckResponse | null>(null);

  // Multi-member conflict simulator state
  const [conflictRecipeKey, setConflictRecipeKey] = useState("alu_fulkopi_jhol");
  const [memberA, setMemberA] = useState<ConflictDraftMember>({
    name: "বাবা",
    age_group: "elder",
    diet_presets: ["low_potassium"],
    allergies: [],
    drugs: [],
  });
  const [memberB, setMemberB] = useState<ConflictDraftMember>({
    name: "মা",
    age_group: "adult",
    diet_presets: ["low_gi", "low_sodium"],
    allergies: [],
    drugs: ["ace_inhibitor"],
  });
  const [conflictRunning, setConflictRunning] = useState(false);
  const [conflictResult, setConflictResult] = useState<EngineConflictCheckResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    harborApi
      .getEngineCatalog(session?.token, locale)
      .then((res) => {
        if (cancelled) return;
        setCatalog(res);
        if (res.recipes.length > 0) {
          setSelectedRecipeKey(res.recipes[0].key);
          const alu = res.recipes.find((r) => r.key === "alu_fulkopi_jhol");
          setConflictRecipeKey(alu ? alu.key : res.recipes[0].key);
        }
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

  async function executeConflictCheck(
    targetRecipeKey: string,
    draftA: ConflictDraftMember,
    draftB: ConflictDraftMember,
    useHouseholdMembers = false,
  ) {
    setConflictRunning(true);
    try {
      const res = await harborApi.checkEngineConflicts(
        useHouseholdMembers
          ? { recipe_key: targetRecipeKey }
          : {
              recipe_key: targetRecipeKey,
              custom_members: [draftA, draftB].map((m) => ({
                name: m.name.trim() || "Member",
                role: "patient",
                age_group: m.age_group,
                allergies: m.allergies,
                diet_presets: m.diet_presets,
                medicines: m.drugs.map((dc) => ({
                  name_as_written: dc,
                  drug_class: dc,
                  verified_by_caregiver: true,
                  active: true,
                })),
              })),
            },
        session?.token,
        locale,
      );
      setConflictResult(res);
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("common.errorUnexpected"), "error");
    } finally {
      setConflictRunning(false);
    }
  }

  function applyConflictPreset(presetId: "potato" | "prawn_salt" | "convergent") {
    let rk = "alu_fulkopi_jhol";
    let nextA: ConflictDraftMember = {
      name: "বাবা",
      age_group: "elder",
      diet_presets: ["low_potassium"],
      allergies: [],
      drugs: [],
    };
    let nextB: ConflictDraftMember = {
      name: "মা",
      age_group: "adult",
      diet_presets: ["low_gi", "low_sodium"],
      allergies: [],
      drugs: ["ace_inhibitor"],
    };

    if (presetId === "prawn_salt") {
      rk = "lau_chingri";
      nextA = {
        name: "মা (Low-Na)",
        age_group: "adult",
        diet_presets: ["low_sodium"],
        allergies: [],
        drugs: [],
      };
      nextB = {
        name: "আরিফ (Prawn Allergy)",
        age_group: "child",
        diet_presets: ["low_purine"],
        allergies: ["prawn_shellfish"],
        drugs: [],
      };
    } else if (presetId === "convergent") {
      rk = "lau_masoor_dal";
      nextA = {
        name: "মা (Low-Na)",
        age_group: "adult",
        diet_presets: ["low_sodium"],
        allergies: [],
        drugs: [],
      };
      nextB = {
        name: "বাবা (Low-Na)",
        age_group: "elder",
        diet_presets: ["low_sodium"],
        allergies: [],
        drugs: [],
      };
    }

    setConflictRecipeKey(rk);
    setMemberA(nextA);
    setMemberB(nextB);
    void executeConflictCheck(rk, nextA, nextB, false);
  }

  function mapStatusVariant(status: string) {
    if (status === "SAFE_DIRECT") return "SAFE_DIRECT" as const;
    if (status === "SAFE_WITH_SPLIT") return "SAFE_WITH_SPLIT" as const;
    if (status === "UNVERIFIED") return "UNVERIFIED" as const;
    return "BLOCKED" as const;
  }

  function renderDraftEditor(
    title: string,
    draft: ConflictDraftMember,
    setDraft: React.Dispatch<React.SetStateAction<ConflictDraftMember>>,
  ) {
    if (!catalog) return null;
    return (
      <div className="neu-inset p-4 space-y-3">
        <h3 className="text-sm font-extrabold" style={{ color: "var(--accent)" }}>
          {title}
        </h3>
        <div className="grid gap-3 sm:grid-cols-2">
          <Input
            label={t("engine.conflict.nameLabel")}
            value={draft.name}
            onChange={(e) => setDraft((prev) => ({ ...prev, name: e.target.value }))}
          />
          <div className="space-y-1">
            <label className="block text-xs font-semibold" style={{ color: "var(--text)" }}>
              {t("engine.customAgeLabel")}
            </label>
            <select
              value={draft.age_group}
              onChange={(e) => setDraft((prev) => ({ ...prev, age_group: e.target.value as AgeGroup }))}
              className="neu-inset w-full min-h-[42px] px-2.5 py-1.5 text-xs"
              style={{ color: "var(--text)" }}
            >
              {catalog.age_groups.map((ag) => (
                <option key={ag} value={ag}>
                  {t(`members.ageGroups.${ag}`)}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="space-y-1">
          <p className="text-xs font-semibold" style={{ color: "var(--text)" }}>
            {t("members.presetsLabel")}
          </p>
          <div className="flex flex-wrap gap-1.5">
            {catalog.presets.map((pk) => {
              const active = draft.diet_presets.includes(pk);
              return (
                <button
                  key={pk}
                  type="button"
                  onClick={() =>
                    setDraft((prev) => ({
                      ...prev,
                      diet_presets: prev.diet_presets.includes(pk)
                        ? prev.diet_presets.filter((x) => x !== pk)
                        : [...prev.diet_presets, pk],
                    }))
                  }
                  className={`min-h-[34px] rounded-full px-2.5 py-1 text-[11px] font-bold cursor-pointer ${
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

        <div className="space-y-1">
          <p className="text-xs font-semibold" style={{ color: "var(--text)" }}>
            {t("members.allergiesLabel")}
          </p>
          <div className="flex flex-wrap gap-1.5">
            {catalog.allergens.map((ak) => {
              const active = draft.allergies.includes(ak);
              return (
                <button
                  key={ak}
                  type="button"
                  onClick={() =>
                    setDraft((prev) => ({
                      ...prev,
                      allergies: prev.allergies.includes(ak)
                        ? prev.allergies.filter((x) => x !== ak)
                        : [...prev.allergies, ak],
                    }))
                  }
                  className={`min-h-[34px] rounded-full px-2.5 py-1 text-[11px] font-bold cursor-pointer ${
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

        <div className="space-y-1">
          <p className="text-xs font-semibold" style={{ color: "var(--text)" }}>
            {t("engine.customDrugsLabel")}
          </p>
          <div className="flex flex-wrap gap-1.5">
            {catalog.drug_classes.map((dc) => {
              const active = draft.drugs.includes(dc);
              return (
                <button
                  key={dc}
                  type="button"
                  onClick={() =>
                    setDraft((prev) => ({
                      ...prev,
                      drugs: prev.drugs.includes(dc)
                        ? prev.drugs.filter((x) => x !== dc)
                        : [...prev.drugs, dc],
                    }))
                  }
                  className={`min-h-[34px] rounded-full px-2.5 py-1 text-[11px] font-bold font-mono cursor-pointer ${
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
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-2xl sm:text-3xl font-extrabold" style={{ color: "var(--text)" }}>
            {explorerTab === "conflict" ? t("engine.conflict.title") : t("engine.title")}
          </h1>
          <p className="text-sm sm:text-base" style={{ color: "var(--text-muted)" }}>
            {explorerTab === "conflict" ? t("engine.conflict.subtitle") : t("engine.subtitle")}
          </p>
        </div>

        <Tabs
          value={explorerTab}
          onChange={(v) => setExplorerTab(v as "single" | "conflict")}
          ariaLabel={t("engine.title")}
          options={[
            { id: "single", label: t("engine.tabSingle") },
            { id: "conflict", label: t("engine.tabConflict") },
          ]}
        />
      </div>

      {loading ? (
        <Skeleton className="h-64 rounded-[20px]" />
      ) : catalog && explorerTab === "single" ? (
        <>
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
        </>
      ) : catalog ? (
        /* Multi-Member Ingredient Conflict Simulator */
        <div className="space-y-6" data-testid="engine-conflict-simulator">
          <Card variant="raised" className="space-y-4">
            <div className="space-y-2">
              <p className="text-xs font-extrabold uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
                {t("engine.conflict.presetsLabel")}
              </p>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="neu"
                  onClick={() => applyConflictPreset("potato")}
                  data-testid="conflict-preset-potato"
                >
                  <Scale className="h-3.5 w-3.5" style={{ color: "var(--saffron-text)" }} aria-hidden="true" />
                  <span>{t("engine.conflict.presetPotato")}</span>
                </Button>
                <Button
                  variant="neu"
                  onClick={() => applyConflictPreset("prawn_salt")}
                  data-testid="conflict-preset-prawn-salt"
                >
                  <ShieldAlert className="h-3.5 w-3.5" style={{ color: "var(--danger)" }} aria-hidden="true" />
                  <span>{t("engine.conflict.presetPrawnSalt")}</span>
                </Button>
                <Button
                  variant="neu"
                  onClick={() => applyConflictPreset("convergent")}
                  data-testid="conflict-preset-convergent"
                >
                  <CheckCircle2 className="h-3.5 w-3.5" style={{ color: "var(--ok)" }} aria-hidden="true" />
                  <span>{t("engine.conflict.presetConvergentSplit")}</span>
                </Button>
                {catalog.members.length >= 2 && (
                  <Button
                    variant="neu"
                    onClick={() => void executeConflictCheck(conflictRecipeKey, memberA, memberB, true)}
                    data-testid="conflict-load-household"
                  >
                    <Users className="h-3.5 w-3.5" style={{ color: "var(--accent)" }} aria-hidden="true" />
                    <span>{t("engine.conflict.loadHouseholdBtn")}</span>
                  </Button>
                )}
              </div>
            </div>

            <div className="space-y-1.5">
              <label htmlFor="conflict-recipe-select" className="block text-sm font-semibold" style={{ color: "var(--text)" }}>
                {t("engine.recipeSelectLabel", { count: catalog.recipes.length })}
              </label>
              <select
                id="conflict-recipe-select"
                value={conflictRecipeKey}
                onChange={(e) => setConflictRecipeKey(e.target.value)}
                className="neu-inset w-full min-h-[48px] px-3 py-2 text-sm"
                style={{ color: "var(--text)" }}
                data-testid="conflict-recipe-select"
              >
                {catalog.recipes.map((r) => (
                  <option key={r.key} value={r.key}>
                    {pickLocalized(r.name_bn, r.name_en)}
                  </option>
                ))}
              </select>
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              {renderDraftEditor(t("engine.conflict.memberALabel"), memberA, setMemberA)}
              {renderDraftEditor(t("engine.conflict.memberBLabel"), memberB, setMemberB)}
            </div>

            <Button
              variant="primary"
              onClick={() => void executeConflictCheck(conflictRecipeKey, memberA, memberB, false)}
              disabled={conflictRunning}
              data-testid="conflict-run-btn"
            >
              <Play className="h-4 w-4" aria-hidden="true" />
              <span>{conflictRunning ? t("common.loading") : t("engine.conflict.runBtn")}</span>
            </Button>
          </Card>

          {conflictResult && (
            <Card variant="raised" className="space-y-5" data-testid="conflict-result-card">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="text-xl font-extrabold" style={{ color: "var(--text)" }}>
                    {pickLocalized(conflictResult.recipe_name_bn, conflictResult.recipe_name_en)}
                  </h2>
                  <p className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                    {t("engine.conflict.resultTitle")}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant={mapStatusVariant(conflictResult.household_status)} />
                  {conflictResult.order_invariant && (
                    <Badge
                      variant="SAFE_DIRECT"
                      label={t("engine.conflict.orderInvariantBadge")}
                    />
                  )}
                </div>
              </div>

              {conflictResult.order_invariant && (
                <p className="text-xs font-semibold" style={{ color: "var(--ok)" }}>
                  {t("engine.conflict.orderInvariantDesc")}
                </p>
              )}

              {conflictResult.split_step_bn && (
                <div className="neu-inset p-3.5 text-sm font-semibold" style={{ color: "var(--saffron-text)" }}>
                  {conflictResult.split_step_bn} ({conflictResult.split_for.join(", ")})
                </div>
              )}

              <div className="space-y-3">
                <h3 className="text-base font-extrabold" style={{ color: "var(--text)" }}>
                  {t("engine.conflict.conflictsFoundTitle", {
                    count: conflictResult.ingredient_conflicts.length,
                  })}
                </h3>
                {conflictResult.ingredient_conflicts.length === 0 ? (
                  <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                    {t("engine.conflict.noConflictsMsg")}
                  </p>
                ) : (
                  <div className="grid gap-3 md:grid-cols-2">
                    {conflictResult.ingredient_conflicts.map((conf) => (
                      <div key={conf.ingredient_key} className="neu-inset p-4 space-y-2.5">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <span className="font-extrabold text-sm" style={{ color: "var(--text)" }}>
                            {pickLocalized(conf.ingredient_name_bn, conf.ingredient_name_en)}
                          </span>
                          <Badge
                            variant={mapStatusVariant(conf.winning_status)}
                            label={t(`engine.conflict.resolutionLabels.${conf.resolution}`)}
                          />
                        </div>
                        <p className="text-xs leading-relaxed" style={{ color: "var(--text)" }}>
                          {pickLocalized(conf.explanation_bn, conf.explanation_en)}
                        </p>
                        <div className="space-y-1 text-xs">
                          <p className="font-bold" style={{ color: "var(--text-muted)" }}>
                            {t("engine.conflict.memberPositionsLabel")}:
                          </p>
                          <div className="flex flex-wrap gap-1.5">
                            {conf.positions.map((pos) => (
                              <span
                                key={pos.member_id}
                                className="rounded-full border border-[var(--border-subtle)] px-2.5 py-0.5 text-[11px] font-semibold"
                                style={{ color: "var(--text)" }}
                              >
                                {pos.member_name}: {pos.status} ({pos.reasons.join(", ") || "OK"})
                              </span>
                            ))}
                          </div>
                        </div>
                        <div className="text-[11px] font-mono" style={{ color: "var(--text-muted)" }}>
                          {t("engine.conflict.winningRuleLabel")}: {conf.winning_reasons.join(", ") || "NONE"}
                        </div>
                        {conf.safe_substitutes.length > 0 && (
                          <div className="flex flex-wrap items-center gap-1.5 text-xs pt-1">
                            <span className="font-bold" style={{ color: "var(--text)" }}>
                              {t("engine.conflict.safeSubstitutesLabel")}:
                            </span>
                            {conf.safe_substitutes.map((s) => (
                              <Badge
                                key={s.ingredient_key}
                                variant="INFO"
                                label={pickLocalized(s.name_bn, s.name_en)}
                              />
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="space-y-2">
                <h3 className="text-sm font-bold" style={{ color: "var(--text)" }}>
                  {t("engine.traceTitle")}
                </h3>
                <div className="grid gap-3 md:grid-cols-2">
                  {conflictResult.member_results.map((mr) => (
                    <div key={mr.member_id} className="neu-inset p-3.5 space-y-2">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-sm font-extrabold" style={{ color: "var(--text)" }}>
                          {mr.member_name}
                        </span>
                        <Badge variant={mapStatusVariant(mr.status)} />
                      </div>
                      <ol className="space-y-1 font-mono text-[11px]" style={{ color: "var(--text-muted)" }}>
                        {mr.trace.map((line, idx) => (
                          <li key={idx}>{line}</li>
                        ))}
                      </ol>
                    </div>
                  ))}
                </div>
              </div>
            </Card>
          )}
        </div>
      ) : null}
    </div>
  );
}
