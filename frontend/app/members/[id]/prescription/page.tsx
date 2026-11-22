"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, CheckCircle2, FileUp, ShieldAlert, ShieldCheck } from "lucide-react";
import { AuthGuardNotice } from "@/components/AuthGuardNotice";
import { Badge, Button, Card, Input, useToast } from "@/components/ui";
import {
  ApiError,
  DrugClass,
  DrugClassOption,
  harborApi,
  MealSlot,
  MedTiming,
  PrescriptionConfirmRowPayload,
  PrescriptionDraftResponse,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useSession } from "@/lib/session";

const TIMING_OPTIONS: MedTiming[] = ["before_food", "after_food", "with_food", "any", "unknown"];
const SLOT_OPTIONS: MealSlot[] = ["breakfast", "lunch", "dinner"];

interface EditableRxRow extends PrescriptionConfirmRowPayload {
  lowConfidence: boolean;
  confidence: number;
}

export default function PrescriptionUploadPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const memberId = params?.id || "";
  const { locale, formatNumber, pickLocalized, t } = useI18n();
  const { session, setSession } = useSession();
  const { showToast } = useToast();

  const [drugClasses, setDrugClasses] = useState<DrugClassOption[]>([
    { value: "ace_inhibitor", label_bn: "ACE ইনহিবিটর", label_en: "ACE Inhibitor" },
    { value: "arb", label_bn: "ARB", label_en: "ARB" },
    { value: "k_sparing_diuretic", label_bn: "পটাশিয়াম-স্পেয়ারিং ডাইইউরেটিক", label_en: "Potassium-Sparing Diuretic" },
    { value: "statin_cyp3a4", label_bn: "CYP3A4 স্ট্যাটিন", label_en: "CYP3A4 Statin" },
    { value: "none_modelled", label_bn: "মডেল করা নেই", label_en: "Not modelled" },
  ]);

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [extracting, setExtracting] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [grantingConsent, setGrantingConsent] = useState(false);
  const [draft, setDraft] = useState<PrescriptionDraftResponse | null>(null);
  const [rows, setRows] = useState<EditableRxRow[]>([]);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    harborApi
      .getDrugClasses(locale)
      .then((res) => {
        if (!cancelled && res.drug_classes.length > 0) {
          setDrugClasses(res.drug_classes);
        }
      })
      .catch(() => {
        /* fallback list already populated */
      });
    return () => {
      cancelled = true;
    };
  }, [locale]);

  async function handleGrantConsent() {
    if (!session) return;
    setGrantingConsent(true);
    try {
      await harborApi.updateHouseholdSettings(
        session.householdId,
        { consent_given: true },
        session.token,
        locale,
      );
      setSession({ ...session, consentGiven: true });
      showToast(t("settings.savedToast"), "success");
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("common.errorUnexpected"), "error");
    } finally {
      setGrantingConsent(false);
    }
  }

  async function handleExtract(e: React.FormEvent) {
    e.preventDefault();
    if (!session || !selectedFile || !memberId) return;
    setExtracting(true);
    setErrorMsg(null);
    try {
      const res = await harborApi.uploadPrescription(memberId, selectedFile, session.token, locale);
      setDraft(res);
      setRows(
        res.medicines.map((m) => ({
          name_as_written: m.name_as_written,
          generic_name: m.generic_guess || "",
          drug_class: m.suggested_drug_class || "none_modelled",
          timing: m.timing || "after_food",
          meal_slots:
            m.times_per_day && m.times_per_day >= 2
              ? ["breakfast", "dinner"]
              : ["dinner"],
          confirmed: !m.low_confidence,
          lowConfidence: m.low_confidence,
          confidence: m.confidence,
        })),
      );
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : t("common.errorUnexpected");
      setErrorMsg(msg);
      showToast(msg, "error");
    } finally {
      setExtracting(false);
    }
  }

  function updateRow(idx: number, patch: Partial<EditableRxRow>) {
    setRows((prev) => prev.map((r, i) => (i === idx ? { ...r, ...patch } : r)));
  }

  function toggleRowSlot(idx: number, slot: MealSlot) {
    setRows((prev) =>
      prev.map((r, i) => {
        if (i !== idx) return r;
        const has = r.meal_slots.includes(slot);
        const nextSlots = has
          ? r.meal_slots.filter((s) => s !== slot)
          : [...r.meal_slots, slot];
        return { ...r, meal_slots: nextSlots.length > 0 ? nextSlots : [slot] };
      }),
    );
  }

  async function handleConfirm() {
    if (!session || !draft) return;
    setConfirming(true);
    setErrorMsg(null);
    try {
      const payloadRows: PrescriptionConfirmRowPayload[] = rows.map((r) => ({
        name_as_written: r.name_as_written,
        generic_name: r.generic_name || null,
        drug_class: r.drug_class,
        timing: r.timing,
        meal_slots: r.meal_slots,
        confirmed: r.confirmed,
      }));
      const res = await harborApi.confirmPrescription(
        draft.prescription_id,
        payloadRows,
        session.token,
        locale,
      );
      showToast(
        t("prescription.confirmSuccess", { count: res.scheduled_doses_count }),
        "success",
      );
      router.push(`/members/${memberId}`);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : t("common.errorUnexpected");
      setErrorMsg(msg);
      showToast(msg, "error");
    } finally {
      setConfirming(false);
    }
  }

  if (!session) return <AuthGuardNotice />;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link
          href={`/members/${memberId}`}
          className="neu-raised-sm inline-flex min-h-[44px] items-center gap-2 px-4 py-2 text-sm font-bold"
          style={{ color: "var(--text)" }}
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          <span>{t("common.back")}</span>
        </Link>
      </div>

      <div className="space-y-1">
        <h1 className="text-2xl sm:text-3xl font-extrabold" style={{ color: "var(--text)" }}>
          {t("prescription.title")}
        </h1>
        <p className="text-sm sm:text-base" style={{ color: "var(--text-muted)" }}>
          {t("prescription.subtitle")}
        </p>
      </div>

      {/* Zero Image & Zero Dose Storage Banner */}
      <Card variant="glass" className="flex items-start gap-3">
        <ShieldCheck className="h-5 w-5 shrink-0 mt-0.5" style={{ color: "var(--accent)" }} aria-hidden="true" />
        <p className="text-xs sm:text-sm font-semibold" style={{ color: "var(--text)" }}>
          {t("prescription.privacyBanner")}
        </p>
      </Card>

      {/* Consent Gate */}
      {!session.consentGiven ? (
        <Card variant="raised" className="space-y-4" data-testid="rx-consent-gate">
          <div className="flex items-start gap-3">
            <ShieldAlert className="h-6 w-6 shrink-0 mt-0.5" style={{ color: "var(--danger)" }} aria-hidden="true" />
            <div className="space-y-1">
              <h2 className="text-lg font-bold" style={{ color: "var(--text)" }}>
                {t("prescription.consentBlockedTitle")}
              </h2>
              <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                {t("prescription.consentBlockedDesc")}
              </p>
            </div>
          </div>
          <Button
            variant="primary"
            onClick={handleGrantConsent}
            disabled={grantingConsent}
            data-testid="rx-grant-consent"
          >
            {grantingConsent ? t("common.loading") : t("prescription.grantConsentBtn")}
          </Button>
        </Card>
      ) : (
        <Card variant="raised">
          <form onSubmit={handleExtract} className="space-y-4">
            <div className="space-y-2">
              <label className="block text-sm font-bold" style={{ color: "var(--text)" }}>
                {t("prescription.fileLabel")}
              </label>
              <input
                type="file"
                accept="image/*"
                onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
                className="neu-inset w-full p-3 text-sm cursor-pointer"
                style={{ color: "var(--text)" }}
                data-testid="rx-file-input"
              />
            </div>

            {selectedFile && (
              <p className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                {selectedFile.name} ({formatNumber(Math.round(selectedFile.size / 1024))} KB)
              </p>
            )}

            {errorMsg && (
              <p className="text-sm font-semibold" style={{ color: "var(--danger)" }} role="alert">
                {errorMsg}
              </p>
            )}

            <Button
              type="submit"
              variant="primary"
              disabled={!selectedFile || extracting}
              data-testid="rx-extract-submit"
            >
              <FileUp className="h-4 w-4" aria-hidden="true" />
              <span>{extracting ? t("prescription.extracting") : t("prescription.extractBtn")}</span>
            </Button>
          </form>
        </Card>
      )}

      {/* Draft Confirmation Table */}
      {draft && (
        <Card variant="raised" className="space-y-4" data-testid="rx-draft-table">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-lg font-extrabold" style={{ color: "var(--text)" }}>
              {t("prescription.draftTitle")}
            </h2>
            <Badge
              variant="ESTIMATED"
              label={`${t("prescription.confidenceLabel")}: ${formatNumber(Math.round(draft.overall_confidence * 100))}%`}
            />
          </div>

          <p className="text-xs font-semibold" style={{ color: "var(--text-muted)" }}>
            {pickLocalized(draft.scope_note_bn, draft.scope_note_en)}
          </p>

          {draft.extraction_failed && (
            <div className="neu-inset p-3 text-sm font-semibold" style={{ color: "var(--danger)" }}>
              {t("prescription.extractionFailed")}
            </div>
          )}

          {draft.diet_notes.length > 0 && (
            <div className="neu-inset p-3 space-y-1">
              <p className="text-xs font-bold" style={{ color: "var(--text)" }}>
                {t("prescription.dietNotesLabel")}:
              </p>
              <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                {draft.diet_notes.join(" • ")}
              </p>
            </div>
          )}

          <div className="space-y-3">
            {rows.map((row, idx) => (
              <div
                key={idx}
                className="neu-inset p-4 space-y-3"
                style={
                  row.lowConfidence
                    ? { borderColor: "var(--saffron-text)" }
                    : undefined
                }
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <label className="flex items-center gap-2 cursor-pointer text-sm font-bold">
                    <input
                      type="checkbox"
                      checked={row.confirmed}
                      onChange={(e) => updateRow(idx, { confirmed: e.target.checked })}
                      className="h-5 w-5 accent-[var(--accent)]"
                      data-testid={`rx-row-confirm-${idx}`}
                    />
                    <span style={{ color: "var(--text)" }}>{t("prescription.colConfirm")}</span>
                  </label>
                  {row.lowConfidence && (
                    <Badge variant="SAFE_WITH_SPLIT" label={t("prescription.lowConfidenceFlag")} />
                  )}
                </div>

                <div className="grid gap-3 sm:grid-cols-2">
                  <Input
                    label={t("prescription.colName")}
                    value={row.name_as_written}
                    onChange={(e) => updateRow(idx, { name_as_written: e.target.value })}
                  />
                  <Input
                    label={t("prescription.colGeneric")}
                    value={row.generic_name || ""}
                    onChange={(e) => updateRow(idx, { generic_name: e.target.value })}
                  />
                </div>

                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="space-y-1.5">
                    <label className="block text-sm font-semibold" style={{ color: "var(--text)" }}>
                      {t("prescription.colClass")}
                    </label>
                    <select
                      value={row.drug_class}
                      onChange={(e) => updateRow(idx, { drug_class: e.target.value as DrugClass })}
                      className="neu-inset w-full min-h-[48px] px-3 py-2 text-sm"
                      style={{ color: "var(--text)" }}
                      data-testid={`rx-row-class-${idx}`}
                    >
                      {drugClasses.map((dc) => (
                        <option key={dc.value} value={dc.value}>
                          {pickLocalized(dc.label_bn, dc.label_en)}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="space-y-1.5">
                    <label className="block text-sm font-semibold" style={{ color: "var(--text)" }}>
                      {t("prescription.colTiming")}
                    </label>
                    <select
                      value={row.timing}
                      onChange={(e) => updateRow(idx, { timing: e.target.value as MedTiming })}
                      className="neu-inset w-full min-h-[48px] px-3 py-2 text-sm"
                      style={{ color: "var(--text)" }}
                    >
                      {TIMING_OPTIONS.map((tm) => (
                        <option key={tm} value={tm}>
                          {t(`memberDetail.timings.${tm}`)}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs font-semibold mr-1" style={{ color: "var(--text-muted)" }}>
                    {t("prescription.colSlots")}:
                  </span>
                  {SLOT_OPTIONS.map((slot) => {
                    const active = row.meal_slots.includes(slot);
                    return (
                      <button
                        key={slot}
                        type="button"
                        onClick={() => toggleRowSlot(idx, slot)}
                        className={`min-h-[38px] rounded-[12px] px-3 py-1 text-xs font-bold cursor-pointer ${
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
            ))}
          </div>

          <Button
            variant="primary"
            fullWidth
            onClick={handleConfirm}
            disabled={confirming || rows.every((r) => !r.confirmed)}
            data-testid="rx-confirm-submit"
          >
            <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
            <span>{confirming ? t("common.loading") : t("prescription.confirmSubmit")}</span>
          </Button>
        </Card>
      )}
    </div>
  );
}

