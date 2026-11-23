"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Copy, ExternalLink, FileText, Pill, Trash2 } from "lucide-react";
import { AuthGuardNotice } from "@/components/AuthGuardNotice";
import { Badge, Button, Card, Input, Skeleton, useToast } from "@/components/ui";
import {
  AgeGroup,
  ApiError,
  DrugClass,
  DrugClassOption,
  harborApi,
  MealSlot,
  MedTiming,
  MemberDetailResponse,
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
const TIMINGS: MedTiming[] = ["before_food", "after_food", "with_food", "any", "unknown"];
const SLOTS: MealSlot[] = ["breakfast", "lunch", "dinner"];

export default function MemberDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const memberId = params?.id || "";
  const { locale, pickLocalized, t } = useI18n();
  const { session } = useSession();
  const { showToast } = useToast();

  const [member, setMember] = useState<MemberDetailResponse | null>(null);
  const [drugClasses, setDrugClasses] = useState<DrugClassOption[]>([]);
  const [allergenKeys, setAllergenKeys] = useState<string[]>(DEFAULT_ALLERGEN_KEYS);
  const [presetKeys, setPresetKeys] = useState<string[]>(DEFAULT_PRESET_KEYS);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Edit profile state
  const [name, setName] = useState("");
  const [role, setRole] = useState<MemberRole>("other");
  const [ageGroup, setAgeGroup] = useState<AgeGroup>("adult");
  const [conditionsRaw, setConditionsRaw] = useState("");
  const [allergies, setAllergies] = useState<string[]>([]);
  const [presets, setPresets] = useState<string[]>([]);
  const [savingProfile, setSavingProfile] = useState(false);

  // Manual add medicine state (ZERO dose fields)
  const [medName, setMedName] = useState("");
  const [medGeneric, setMedGeneric] = useState("");
  const [medClass, setMedClass] = useState<DrugClass>("none_modelled");
  const [medTiming, setMedTiming] = useState<MedTiming>("after_food");
  const [medSlots, setMedSlots] = useState<MealSlot[]>(["dinner"]);
  const [addingMed, setAddingMed] = useState(false);

  useEffect(() => {
    if (!session || !memberId) return;
    let cancelled = false;
    Promise.all([
      harborApi.getMember(memberId, session.token, locale),
      harborApi.getDrugClasses(locale),
    ])
      .then(([mData, dcData]) => {
        if (cancelled) return;
        setMember(mData);
        setName(mData.name);
        setRole((mData.role as MemberRole) || "other");
        setAgeGroup((mData.age_group as AgeGroup) || "adult");
        setConditionsRaw(mData.conditions.join(", "));
        setAllergies(mData.allergies);
        setPresets(mData.diet_presets);
        setDrugClasses(dcData.drug_classes);
        setErrorMsg(null);
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setErrorMsg(err instanceof ApiError ? err.message : t("common.errorUnexpected"));
        setLoading(false);
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
  }, [session, memberId, locale, t]);

  async function handleSaveProfile(e: React.FormEvent) {
    e.preventDefault();
    if (!session || !member) return;
    setSavingProfile(true);
    try {
      const updated = await harborApi.updateMember(
        member.id,
        {
          name: name.trim(),
          role,
          age_group: ageGroup,
          conditions: conditionsRaw
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean),
          allergies,
          diet_presets: presets,
        },
        session.token,
        locale,
      );
      setMember((prev) => (prev ? { ...prev, ...updated } : prev));
      showToast(t("common.saveChanges"), "success");
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("common.errorUnexpected"), "error");
    } finally {
      setSavingProfile(false);
    }
  }

  async function handleAddMedicine(e: React.FormEvent) {
    e.preventDefault();
    if (!session || !member || !medName.trim()) return;
    setAddingMed(true);
    try {
      const created = await harborApi.addMedicine(
        member.id,
        {
          name_as_written: medName.trim(),
          generic_name: medGeneric.trim() || null,
          drug_class: medClass,
          timing: medTiming,
          meal_slots: medSlots.length > 0 ? medSlots : ["dinner"],
          verified_by_caregiver: true,
        },
        session.token,
        locale,
      );
      setMember((prev) =>
        prev ? { ...prev, medicines: [...prev.medicines, created] } : prev,
      );
      setMedName("");
      setMedGeneric("");
      showToast(t("common.save"), "success");
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("common.errorUnexpected"), "error");
    } finally {
      setAddingMed(false);
    }
  }

  async function handleDeleteMed(medId: string) {
    if (!session || !member) return;
    try {
      await harborApi.deleteMedicine(member.id, medId, session.token, locale);
      setMember((prev) =>
        prev ? { ...prev, medicines: prev.medicines.filter((x) => x.id !== medId) } : prev,
      );
      showToast(t("common.delete"), "info");
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("common.errorUnexpected"), "error");
    }
  }

  async function handleDeleteMember() {
    if (!session || !member) return;
    if (typeof window !== "undefined" && !window.confirm(t("memberDetail.deleteConfirm"))) {
      return;
    }
    try {
      await harborApi.deleteMember(member.id, session.token, locale);
      router.push("/members");
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("common.errorUnexpected"), "error");
    }
  }

  function toggleList(list: string[], val: string, setter: (v: string[]) => void) {
    setter(list.includes(val) ? list.filter((x) => x !== val) : [...list, val]);
  }

  function toggleSlot(slot: MealSlot) {
    setMedSlots((prev) =>
      prev.includes(slot) ? prev.filter((s) => s !== slot) : [...prev, slot],
    );
  }

  if (!session) return <AuthGuardNotice />;
  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-12 w-48 rounded-[16px]" />
        <Skeleton className="h-64 rounded-[20px]" />
      </div>
    );
  }
  if (errorMsg || !member) {
    return (
      <Card variant="raised" className="space-y-3">
        <p className="text-sm font-semibold" style={{ color: "var(--danger)" }}>
          {errorMsg || t("common.errorUnexpected")}
        </p>
        <Link href="/members" className="neu-raised-sm inline-flex px-4 py-2 text-sm font-bold">
          {t("memberDetail.backToMembers")}
        </Link>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link
          href="/members"
          className="neu-raised-sm inline-flex min-h-[44px] items-center gap-2 px-4 py-2 text-sm font-bold"
          style={{ color: "var(--text)" }}
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          <span>{t("memberDetail.backToMembers")}</span>
        </Link>

        <div className="flex flex-wrap gap-2">
          <Link
            href={`/members/${member.id}/prescription`}
            className="skeu-button inline-flex min-h-[44px] items-center gap-2 px-4 py-2 text-sm font-bold"
          >
            <FileText className="h-4 w-4" aria-hidden="true" />
            <span>{t("members.uploadRx")}</span>
          </Link>
          <Button variant="danger" onClick={handleDeleteMember} className="!min-h-[44px] !px-4 !py-2 !text-sm">
            <Trash2 className="h-4 w-4" aria-hidden="true" />
            <span>{t("memberDetail.deleteMember")}</span>
          </Button>
        </div>
      </div>

      {/* Patient Link Card */}
      <Card variant="glass" className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <p className="text-sm font-bold" style={{ color: "var(--text)" }}>
            {t("memberDetail.patientLinkTitle")}
          </p>
          <p className="font-mono text-xs" style={{ color: "var(--text-muted)" }}>
            /patient/{member.patient_token}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="neu"
            className="!min-h-[44px] !px-3.5 !py-2 !text-xs"
            onClick={() => {
              if (typeof window !== "undefined") {
                const url = `${window.location.origin}/patient/${member.patient_token}`;
                void navigator.clipboard.writeText(url);
                showToast(t("common.copied"), "success");
              }
            }}
          >
            <Copy className="h-3.5 w-3.5" aria-hidden="true" />
            <span>{t("common.copy")}</span>
          </Button>
          <Link
            href={`/patient/${member.patient_token}`}
            className="skeu-button inline-flex min-h-[44px] items-center gap-1.5 px-3.5 py-2 text-xs font-bold"
          >
            <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
            <span>{t("memberDetail.openPatientView")}</span>
          </Link>
        </div>
      </Card>

      {/* Dietary Profile Form */}
      <Card variant="raised">
        <form onSubmit={handleSaveProfile} className="space-y-4">
          <h1 className="text-xl font-extrabold" style={{ color: "var(--text)" }}>
            {t("memberDetail.profileSection")}: {member.name}
          </h1>
          <div className="grid gap-3 sm:grid-cols-3">
            <Input label={t("members.nameLabel")} value={name} onChange={(e) => setName(e.target.value)} required />
            <div className="space-y-1.5">
              <label htmlFor="member-detail-role" className="block text-sm font-semibold" style={{ color: "var(--text)" }}>
                {t("members.roleLabel")}
              </label>
              <select
                id="member-detail-role"
                value={role}
                onChange={(e) => setRole(e.target.value as MemberRole)}
                className="neu-inset w-full min-h-[48px] px-3 py-2 text-sm"
                style={{ color: "var(--text)" }}
              >
                {(["caregiver", "patient", "child", "elder", "other"] as const).map((r) => (
                  <option key={r} value={r}>{t(`members.roles.${r}`)}</option>
                ))}
              </select>
            </div>
            <div className="space-y-1.5">
              <label htmlFor="member-detail-age" className="block text-sm font-semibold" style={{ color: "var(--text)" }}>
                {t("members.ageGroupLabel")}
              </label>
              <select
                id="member-detail-age"
                value={ageGroup}
                onChange={(e) => setAgeGroup(e.target.value as AgeGroup)}
                className="neu-inset w-full min-h-[48px] px-3 py-2 text-sm"
                style={{ color: "var(--text)" }}
              >
                {(["child_under_1", "child_under_5", "child", "adult", "elder"] as const).map((ag) => (
                  <option key={ag} value={ag}>{t(`members.ageGroups.${ag}`)}</option>
                ))}
              </select>
            </div>
          </div>

          <Input
            label={t("members.conditionsLabel")}
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
                    onClick={() => toggleList(presets, pk, setPresets)}
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
                    onClick={() => toggleList(allergies, ak, setAllergies)}
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

          <Button type="submit" variant="primary" disabled={savingProfile}>
            {savingProfile ? t("common.loading") : t("common.saveChanges")}
          </Button>
        </form>
      </Card>

      {/* Medicines List + Add Form */}
      <Card variant="raised" className="space-y-5">
        <div className="flex items-center gap-2">
          <Pill className="h-5 w-5" style={{ color: "var(--accent)" }} aria-hidden="true" />
          <h2 className="text-lg font-bold" style={{ color: "var(--text)" }}>
            {t("memberDetail.medicinesSection")}
          </h2>
        </div>

        {member.medicines.length === 0 ? (
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>
            {t("memberDetail.noMedicines")}
          </p>
        ) : (
          <div className="space-y-2">
            {member.medicines.map((med) => (
              <div
                key={med.id}
                className="neu-inset flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3.5"
              >
                <div className="space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-bold" style={{ color: "var(--text)" }}>
                      {med.name_as_written}
                    </span>
                    {med.generic_name && (
                      <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                        ({med.generic_name})
                      </span>
                    )}
                    <Badge
                      variant={med.verified_by_caregiver ? "SAFE_DIRECT" : "UNVERIFIED"}
                      label={med.verified_by_caregiver ? t("members.verifiedLabel") : t("status.UNVERIFIED")}
                    />
                  </div>
                  <p className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                    {med.drug_class} • {t(`memberDetail.timings.${med.timing}`)} •{" "}
                    {med.meal_slots.map((s) => t(`memberDetail.slots.${s}`)).join(", ")}
                  </p>
                </div>
                <Button
                  variant="ghost"
                  onClick={() => handleDeleteMed(med.id)}
                  className="!min-h-[40px] !px-3 !py-1.5 !text-xs"
                >
                  <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                  <span>{t("common.delete")}</span>
                </Button>
              </div>
            ))}
          </div>
        )}

        <form onSubmit={handleAddMedicine} className="space-y-3 pt-4 border-t border-[var(--border-subtle)]">
          <h3 className="text-sm font-bold" style={{ color: "var(--text)" }}>
            {t("memberDetail.addMedTitle")}
          </h3>
          <div className="grid gap-3 sm:grid-cols-2">
            <Input
              label={t("memberDetail.medNameLabel")}
              placeholder={t("memberDetail.medNamePlaceholder")}
              value={medName}
              onChange={(e) => setMedName(e.target.value)}
              required
              data-testid="input-med-name"
            />
            <Input
              label={t("memberDetail.genericNameLabel")}
              value={medGeneric}
              onChange={(e) => setMedGeneric(e.target.value)}
            />
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <label htmlFor="member-detail-med-class" className="block text-sm font-semibold" style={{ color: "var(--text)" }}>
                {t("memberDetail.drugClassLabel")}
              </label>
              <select
                id="member-detail-med-class"
                value={medClass}
                onChange={(e) => setMedClass(e.target.value as DrugClass)}
                className="neu-inset w-full min-h-[48px] px-3 py-2 text-sm"
                style={{ color: "var(--text)" }}
              >
                {drugClasses.map((dc) => (
                  <option key={dc.value} value={dc.value}>
                    {pickLocalized(dc.label_bn, dc.label_en)}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1.5">
              <label htmlFor="member-detail-med-timing" className="block text-sm font-semibold" style={{ color: "var(--text)" }}>
                {t("memberDetail.timingLabel")}
              </label>
              <select
                id="member-detail-med-timing"
                value={medTiming}
                onChange={(e) => setMedTiming(e.target.value as MedTiming)}
                className="neu-inset w-full min-h-[48px] px-3 py-2 text-sm"
                style={{ color: "var(--text)" }}
              >
                {TIMINGS.map((tm) => (
                  <option key={tm} value={tm}>
                    {t(`memberDetail.timings.${tm}`)}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="space-y-1.5">
            <p className="text-sm font-semibold" style={{ color: "var(--text)" }}>
              {t("memberDetail.mealSlotsLabel")}
            </p>
            <div className="flex flex-wrap gap-2">
              {SLOTS.map((slot) => {
                const active = medSlots.includes(slot);
                return (
                  <button
                    key={slot}
                    type="button"
                    onClick={() => toggleSlot(slot)}
                    className={`min-h-[44px] rounded-[12px] px-4 py-2 text-xs font-bold cursor-pointer ${
                      active ? "skeu-button" : "neu-raised-sm"
                    }`}
                    style={active ? undefined : { color: "var(--text)" }}
                  >
                    {t(`memberDetail.slots.${slot}`)}
                  </button>
                );
              })}
            </div>
          </div>

          <Button type="submit" variant="primary" disabled={addingMed}>
            {addingMed ? t("common.loading") : t("memberDetail.addMedSubmit")}
          </Button>
        </form>
      </Card>

      {/* Dose History */}
      <Card variant="raised" className="space-y-3">
        <h2 className="text-lg font-bold" style={{ color: "var(--text)" }}>
          {t("memberDetail.doseHistoryTitle")}
        </h2>
        {member.dose_history.length === 0 ? (
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>
            {t("memberDetail.noDoseHistory")}
          </p>
        ) : (
          <div className="space-y-2">
            {member.dose_history.map((d) => (
              <div key={d.id} className="neu-inset flex items-center justify-between px-3.5 py-2.5 text-xs">
                <span className="font-mono" style={{ color: "var(--text)" }}>
                  {new Date(d.due_at).toLocaleString()}
                </span>
                <Badge
                  variant={d.status === "taken" || d.status === "taken_late" ? "SAFE_DIRECT" : "ESTIMATED"}
                  label={t(`reminders.doseStatuses.${d.status}`)}
                />
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

