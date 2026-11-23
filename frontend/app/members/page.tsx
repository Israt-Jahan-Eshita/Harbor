"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Check, Copy, FileText, Pill, Plus, ShieldAlert, UserPlus, Users } from "lucide-react";
import { AuthGuardNotice } from "@/components/AuthGuardNotice";
import { Badge, Button, Card, Input, Sheet, Skeleton, useToast } from "@/components/ui";
import {
  AgeGroup,
  ApiError,
  harborApi,
  MemberRecord,
  MemberRole,
} from "@/lib/api";
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

const DEFAULT_PRESET_KEYS: string[] = ["low_potassium", "low_sodium", "low_gi", "low_purine"];

const ROLE_OPTIONS: MemberRole[] = ["caregiver", "patient", "child", "elder", "other"];
const AGE_OPTIONS: AgeGroup[] = ["child_under_1", "child_under_5", "child", "adult", "elder"];

export default function MembersPage() {
  const { locale, formatNumber, t } = useI18n();
  const { session } = useSession();
  const { showToast } = useToast();

  const [members, setMembers] = useState<MemberRecord[]>([]);
  const [allergenKeys, setAllergenKeys] = useState<string[]>(DEFAULT_ALLERGEN_KEYS);
  const [presetKeys, setPresetKeys] = useState<string[]>(DEFAULT_PRESET_KEYS);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const [addOpen, setAddOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [name, setName] = useState("");
  const [role, setRole] = useState<MemberRole>("other");
  const [ageGroup, setAgeGroup] = useState<AgeGroup>("adult");
  const [conditionsRaw, setConditionsRaw] = useState("");
  const [allergies, setAllergies] = useState<string[]>([]);
  const [presets, setPresets] = useState<string[]>([]);
  const [notifyEmail, setNotifyEmail] = useState("");

  const fetchMembers = useCallback(async () => {
    if (!session) return;
    try {
      const res = await harborApi.listMembers(session.token, locale);
      setMembers(res.members);
      setErrorMsg(null);
    } catch (err) {
      setErrorMsg(err instanceof ApiError ? err.message : t("common.errorUnexpected"));
    } finally {
      setLoading(false);
    }
  }, [session, locale, t]);

  useEffect(() => {
    if (!session) return;
    let cancelled = false;
    harborApi
      .listMembers(session.token, locale)
      .then((res) => {
        if (!cancelled) {
          setMembers(res.members);
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
    Promise.resolve(harborApi.getEngineCatalog(session.token, locale))
      .then((cat) => {
        if (!cancelled && cat) {
          if (cat.allergens?.length) setAllergenKeys(cat.allergens);
          if (cat.presets?.length) setPresetKeys(cat.presets);
        }
      })
      .catch(() => {
        /* fallback selector keys stay active */
      });
    return () => {
      cancelled = true;
    };
  }, [session, locale, t]);

  function toggleValue(list: string[], value: string, setter: (next: string[]) => void) {
    setter(list.includes(value) ? list.filter((x) => x !== value) : [...list, value]);
  }

  async function handleCopyPatientLink(m: MemberRecord) {
    if (typeof window === "undefined") return;
    const url = `${window.location.origin}/patient/${m.patient_token}`;
    try {
      await navigator.clipboard.writeText(url);
      setCopiedId(m.id);
      showToast(t("common.copied"), "success");
      setTimeout(() => setCopiedId(null), 2000);
    } catch {
      showToast(url, "info");
    }
  }

  async function handleCreateMember(e: React.FormEvent) {
    e.preventDefault();
    if (!session || !name.trim()) return;
    setSaving(true);
    try {
      const conditions = conditionsRaw
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      const created = await harborApi.createMember(
        {
          name: name.trim(),
          role,
          age_group: ageGroup,
          conditions,
          allergies,
          diet_presets: presets,
          notify_email: notifyEmail.trim() || null,
        },
        session.token,
        locale,
      );
      setMembers((prev) => [...prev, created]);
      setName("");
      setConditionsRaw("");
      setAllergies([]);
      setPresets([]);
      setNotifyEmail("");
      setAddOpen(false);
      showToast(`${created.name} — ${t("common.save")}`, "success");
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("common.errorUnexpected"), "error");
    } finally {
      setSaving(false);
    }
  }

  if (!session) {
    return <AuthGuardNotice />;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-2xl sm:text-3xl font-extrabold" style={{ color: "var(--text)" }}>
            {t("members.title")}
          </h1>
          <p className="text-sm sm:text-base" style={{ color: "var(--text-muted)" }}>
            {t("members.subtitle")}
          </p>
        </div>
        <Button
          variant="primary"
          onClick={() => setAddOpen(true)}
          data-testid="open-add-member"
          className="shrink-0"
        >
          <UserPlus className="h-4 w-4" aria-hidden="true" />
          <span>{t("members.addButton")}</span>
        </Button>
      </div>

      {errorMsg && (
        <Card variant="glass" className="flex items-center justify-between gap-3">
          <p className="text-sm font-semibold" style={{ color: "var(--danger)" }}>
            {errorMsg}
          </p>
          <Button variant="neu" onClick={() => { setLoading(true); void fetchMembers(); }}>
            {t("common.retry")}
          </Button>
        </Card>
      )}

      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2">
          <Skeleton className="h-44 rounded-[20px]" />
          <Skeleton className="h-44 rounded-[20px]" />
        </div>
      ) : members.length === 0 ? (
        <Card variant="raised" className="text-center py-10 space-y-3">
          <Users className="h-10 w-10 mx-auto" style={{ color: "var(--accent)" }} aria-hidden="true" />
          <p className="text-base font-semibold" style={{ color: "var(--text)" }}>
            {t("members.emptyState")}
          </p>
          <Button variant="primary" onClick={() => setAddOpen(true)}>
            <Plus className="h-4 w-4" aria-hidden="true" />
            <span>{t("members.addButton")}</span>
          </Button>
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {members.map((m) => {
            const verifiedCount = m.medicines.filter((med) => med.verified_by_caregiver && med.active).length;
            return (
              <Card key={m.id} variant="raised" className="flex flex-col justify-between gap-4" data-testid={`member-card-${m.id}`}>
                <div className="space-y-3">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <h2 className="text-xl font-extrabold" style={{ color: "var(--text)" }}>
                        {m.name}
                      </h2>
                      <p className="text-xs font-semibold" style={{ color: "var(--text-muted)" }}>
                        {t(`members.roles.${m.role}`)} • {t(`members.ageGroups.${m.age_group}`)}
                      </p>
                    </div>
                    <Badge
                      variant={verifiedCount > 0 ? "SAFE_DIRECT" : "INFO"}
                      label={`${formatNumber(verifiedCount)} ${t("members.medicinesCount")}`}
                    />
                  </div>

                  {m.diet_presets.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {m.diet_presets.map((p) => (
                        <Badge key={p} variant="ESTIMATED" label={t(`members.presets.${p}`)} />
                      ))}
                    </div>
                  )}

                  {m.allergies.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {m.allergies.map((a) => (
                        <Badge key={a} variant="BLOCKED" label={t(`members.allergens.${a}`)} />
                      ))}
                    </div>
                  )}

                  {m.conditions.length > 0 && (
                    <p className="text-xs flex items-center gap-1.5" style={{ color: "var(--text-muted)" }}>
                      <ShieldAlert className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                      <span>{m.conditions.join(", ")}</span>
                    </p>
                  )}

                  {m.medicines.length > 0 && (
                    <div className="neu-inset px-3 py-2 space-y-1">
                      {m.medicines.map((med) => (
                        <div key={med.id} className="flex items-center justify-between text-xs">
                          <span className="font-semibold flex items-center gap-1" style={{ color: "var(--text)" }}>
                            <Pill className="h-3 w-3" style={{ color: "var(--accent)" }} aria-hidden="true" />
                            {med.name_as_written}
                          </span>
                          <span className="font-mono" style={{ color: "var(--text-muted)" }}>
                            {med.drug_class}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div className="flex flex-wrap gap-2 pt-2 border-t border-[var(--border-subtle)]">
                  <Link
                    href={`/members/${m.id}`}
                    className="skeu-button inline-flex min-h-[44px] items-center gap-1.5 px-3.5 py-2 text-xs font-bold"
                  >
                    <span>{t("members.openDetail")}</span>
                  </Link>
                  <Link
                    href={`/members/${m.id}/prescription`}
                    className="neu-raised-sm inline-flex min-h-[44px] items-center gap-1.5 px-3.5 py-2 text-xs font-bold"
                    style={{ color: "var(--text)" }}
                  >
                    <FileText className="h-3.5 w-3.5" style={{ color: "var(--accent)" }} aria-hidden="true" />
                    <span>{t("members.uploadRx")}</span>
                  </Link>
                  <Button
                    variant="ghost"
                    onClick={() => handleCopyPatientLink(m)}
                    className="!min-h-[44px] !px-3 !py-2 !text-xs"
                  >
                    {copiedId === m.id ? (
                      <Check className="h-3.5 w-3.5" aria-hidden="true" />
                    ) : (
                      <Copy className="h-3.5 w-3.5" aria-hidden="true" />
                    )}
                    <span>{t("members.copyPatientLink")}</span>
                  </Button>
                </div>
              </Card>
            );
          })}
        </div>
      )}

      {/* Add Member Sheet */}
      <Sheet open={addOpen} onClose={() => setAddOpen(false)} title={t("members.sheetTitle")}>
        <form onSubmit={handleCreateMember} className="space-y-4">
          <Input
            label={t("members.nameLabel")}
            placeholder={t("members.namePlaceholder")}
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            data-testid="input-member-name"
          />

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <label htmlFor="member-create-role" className="block text-sm font-semibold" style={{ color: "var(--text)" }}>
                {t("members.roleLabel")}
              </label>
              <select
                id="member-create-role"
                value={role}
                onChange={(e) => setRole(e.target.value as MemberRole)}
                className="neu-inset w-full min-h-[48px] px-3 py-2 text-sm"
                style={{ color: "var(--text)" }}
              >
                {ROLE_OPTIONS.map((r) => (
                  <option key={r} value={r}>
                    {t(`members.roles.${r}`)}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1.5">
              <label htmlFor="member-create-age" className="block text-sm font-semibold" style={{ color: "var(--text)" }}>
                {t("members.ageGroupLabel")}
              </label>
              <select
                id="member-create-age"
                value={ageGroup}
                onChange={(e) => setAgeGroup(e.target.value as AgeGroup)}
                className="neu-inset w-full min-h-[48px] px-3 py-2 text-sm"
                style={{ color: "var(--text)" }}
              >
                {AGE_OPTIONS.map((ag) => (
                  <option key={ag} value={ag}>
                    {t(`members.ageGroups.${ag}`)}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <Input
            label={t("members.conditionsLabel")}
            placeholder={t("members.conditionsPlaceholder")}
            value={conditionsRaw}
            onChange={(e) => setConditionsRaw(e.target.value)}
          />

          <div className="space-y-2">
            <p className="text-sm font-semibold" style={{ color: "var(--text)" }}>
              {t("members.presetsLabel")}
            </p>
            <div className="flex flex-wrap gap-2">
              {presetKeys.map((pk) => {
                const active = presets.includes(pk);
                return (
                  <button
                    key={pk}
                    type="button"
                    onClick={() => toggleValue(presets, pk, setPresets)}
                    className={`min-h-[40px] rounded-full px-3 py-1.5 text-xs font-bold cursor-pointer ${
                      active ? "skeu-button" : "neu-raised-sm"
                    }`}
                    style={active ? undefined : { color: "var(--text)" }}
                  >
                    {DEFAULT_PRESET_KEYS.includes(pk) ? t(`members.presets.${pk}`) : pk}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="space-y-2">
            <p className="text-sm font-semibold" style={{ color: "var(--text)" }}>
              {t("members.allergiesLabel")}
            </p>
            <div className="flex flex-wrap gap-2">
              {allergenKeys.map((ak) => {
                const active = allergies.includes(ak);
                return (
                  <button
                    key={ak}
                    type="button"
                    onClick={() => toggleValue(allergies, ak, setAllergies)}
                    className={`min-h-[40px] rounded-full px-3 py-1.5 text-xs font-bold cursor-pointer ${
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

          <Input
            label={t("members.notifyEmailLabel")}
            type="email"
            placeholder="caregiver@example.com"
            value={notifyEmail}
            onChange={(e) => setNotifyEmail(e.target.value)}
          />

          <div className="flex justify-end gap-3 pt-2">
            <Button variant="ghost" onClick={() => setAddOpen(false)}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" variant="primary" disabled={saving} data-testid="submit-create-member">
              {saving ? t("common.loading") : t("common.save")}
            </Button>
          </div>
        </form>
      </Sheet>
    </div>
  );
}

