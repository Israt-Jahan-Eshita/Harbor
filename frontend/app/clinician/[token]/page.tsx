"use client";

import React, { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import {
  CheckCircle2,
  ChefHat,
  Languages,
  Moon,
  Pill,
  ShieldCheck,
  Stethoscope,
  Sun,
  XCircle,
} from "lucide-react";
import { Badge, Button, Card, Input, Skeleton, useToast } from "@/components/ui";
import { ApiError, ClinicianPortalResponse, harborApi } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useTheme } from "@/lib/theme";

const KNOWN_PRESETS = ["low_potassium", "low_sodium", "low_gi", "low_purine"];

export default function ClinicianPortalPage() {
  const params = useParams<{ token: string }>();
  const reviewToken = params?.token || "";
  const { locale, toggleLocale, formatNumber, pickLocalized, t } = useI18n();
  const { resolvedTheme, toggleTheme } = useTheme();
  const { showToast } = useToast();

  const [portal, setPortal] = useState<ClinicianPortalResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const [regNo, setRegNo] = useState("");
  const [selectedPresets, setSelectedPresets] = useState<string[]>([]);
  const [applyToMember, setApplyToMember] = useState(true);
  const [clinicianNote, setClinicianNote] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!reviewToken) return;
    let cancelled = false;
    harborApi
      .getClinicianPortal(reviewToken, locale)
      .then((res) => {
        if (cancelled) return;
        setPortal(res);
        setRegNo(res.clinician_reg_no || "");
        setSelectedPresets(
          res.approved_diet_presets?.length
            ? res.approved_diet_presets
            : res.member_current_diet_presets || [],
        );
        setApplyToMember(res.apply_presets_on_approve ?? true);
        setClinicianNote(res.clinician_note || "");
        setErrorMsg(null);
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        const msg =
          err instanceof ApiError && err.status === 404
            ? t("clinician.invalidToken")
            : err instanceof ApiError
              ? err.message
              : t("common.errorUnexpected");
        setErrorMsg(msg);
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [reviewToken, locale, t]);

  function togglePreset(pk: string) {
    setSelectedPresets((prev) =>
      prev.includes(pk) ? prev.filter((x) => x !== pk) : [...prev, pk],
    );
  }

  async function handleSubmitDecision(decision: "approved" | "changes_requested") {
    if (!reviewToken || !clinicianNote.trim()) {
      showToast(t("clinician.noteRequiredHint"), "info");
      return;
    }
    setSubmitting(true);
    try {
      const updated = await harborApi.submitClinicianDecision(
        reviewToken,
        {
          decision,
          clinician_reg_no: regNo.trim() || null,
          clinician_note: clinicianNote.trim(),
          approved_diet_presets: selectedPresets,
          apply_presets_to_member: applyToMember,
        },
        locale,
      );
      setPortal(updated);
      showToast(t("clinician.decisionSuccess"), "success");
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("common.errorUnexpected"), "error");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen px-4 py-6 sm:py-8 mx-auto max-w-4xl space-y-6">
      {/* Standalone Top Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <span className="skeu-button flex h-9 w-9 items-center justify-center rounded-[11px]" aria-hidden="true">
            <ChefHat className="h-4.5 w-4.5" />
          </span>
          <div>
            <span className="block font-display text-base font-bold" style={{ color: "var(--text)" }}>
              {t("app.name")} · {t("clinician.portalBadge")}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={toggleLocale}
            className="neu-raised-sm inline-flex h-10 items-center gap-1.5 px-3 text-xs font-semibold cursor-pointer"
            style={{ color: "var(--text)" }}
          >
            <Languages className="h-3.5 w-3.5" style={{ color: "var(--accent)" }} aria-hidden="true" />
            <span>{locale === "bn" ? "বাং → EN" : "EN → বাং"}</span>
          </button>
          <button
            type="button"
            onClick={toggleTheme}
            aria-label={t("common.themeLabel")}
            className="neu-raised-sm inline-flex h-10 w-10 items-center justify-center cursor-pointer"
            style={{ color: "var(--text)" }}
          >
            {resolvedTheme === "dark" ? (
              <Sun className="h-4 w-4" style={{ color: "var(--saffron)" }} aria-hidden="true" />
            ) : (
              <Moon className="h-4 w-4" style={{ color: "var(--accent)" }} aria-hidden="true" />
            )}
          </button>
        </div>
      </div>

      {loading ? (
        <div className="space-y-4">
          <Skeleton className="h-28 rounded-[18px]" />
          <Skeleton className="h-64 rounded-[20px]" />
        </div>
      ) : errorMsg || !portal ? (
        <Card variant="raised" className="py-10 text-center space-y-3">
          <p className="text-base font-bold" style={{ color: "var(--danger)" }}>
            {errorMsg || t("clinician.invalidToken")}
          </p>
        </Card>
      ) : (
        <div className="space-y-6">
          {/* Header Banner */}
          <Card variant="glass" className="space-y-3">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="space-y-1">
                <h1 className="text-xl sm:text-2xl font-extrabold flex items-center gap-2" style={{ color: "var(--text)" }}>
                  <Stethoscope className="h-6 w-6 shrink-0" style={{ color: "var(--accent)" }} aria-hidden="true" />
                  <span>{t("clinician.portalTitle")}</span>
                </h1>
                <p className="text-xs sm:text-sm" style={{ color: "var(--text-muted)" }}>
                  {t("clinician.householdLabel")}:{" "}
                  <strong style={{ color: "var(--text)" }}>{portal.household_name}</strong> ·{" "}
                  {t("clinician.patientLabel")}:{" "}
                  <strong style={{ color: "var(--text)" }}>{portal.member_name}</strong> (
                  {t(`members.ageGroups.${portal.clinical_snapshot.age_group}`)})
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                {portal.status === "approved" ? (
                  <Badge variant="SAFE_DIRECT" label={t("reviews.statusApproved")} />
                ) : portal.status === "changes_requested" ? (
                  <Badge variant="BLOCKED" label={t("reviews.statusChangesRequested")} />
                ) : (
                  <Badge variant="SAFE_WITH_SPLIT" label={t("reviews.statusPending")} />
                )}
                <Badge
                  variant={portal.payment_status === "paid" ? "SAFE_DIRECT" : "ESTIMATED"}
                  label={`${t("clinician.feeLabel")}: ${formatNumber(portal.fee_bdt)} ${t("common.bdt")} (${t(
                    portal.payment_status === "paid"
                      ? "reviews.payPaid"
                      : portal.payment_status === "waived"
                        ? "reviews.payWaived"
                        : "reviews.payUnpaid",
                  )})`}
                />
              </div>
            </div>

            {portal.status === "approved" && (
              <div className="neu-inset p-3 flex items-center gap-2 text-xs font-bold" style={{ color: "var(--ok)" }}>
                <CheckCircle2 className="h-4 w-4 shrink-0" aria-hidden="true" />
                <span>{t("clinician.completedBannerApproved")}</span>
              </div>
            )}
            {portal.status === "changes_requested" && (
              <div className="neu-inset p-3 flex items-center gap-2 text-xs font-bold" style={{ color: "var(--danger)" }}>
                <XCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
                <span>{t("clinician.completedBannerChanges")}</span>
              </div>
            )}
            {portal.request_note && (
              <div className="neu-inset p-3 space-y-1">
                <p className="text-xs font-bold" style={{ color: "var(--saffron-text)" }}>
                  {t("clinician.requestedNoteLabel")}
                </p>
                <p className="text-sm" style={{ color: "var(--text)" }}>
                  {portal.request_note}
                </p>
              </div>
            )}
          </Card>

          {/* 30-Day Clinical Summary */}
          <Card variant="raised" className="space-y-4">
            <h2 className="text-lg font-extrabold flex items-center gap-2" style={{ color: "var(--text)" }}>
              <ShieldCheck className="h-5 w-5" style={{ color: "var(--accent)" }} aria-hidden="true" />
              <span>{t("clinician.snapshotTitle")}</span>
            </h2>

            <div className="grid gap-3 sm:grid-cols-2">
              <div className="neu-inset p-3.5 space-y-1.5">
                <p className="text-xs font-bold" style={{ color: "var(--text-muted)" }}>
                  {t("clinician.conditionsLabel")}
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {portal.clinical_snapshot.conditions.length > 0 ? (
                    portal.clinical_snapshot.conditions.map((c) => (
                      <Badge key={c} variant="SAFE_WITH_SPLIT" label={c} />
                    ))
                  ) : (
                    <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                      {t("common.none")}
                    </span>
                  )}
                </div>
              </div>

              <div className="neu-inset p-3.5 space-y-1.5">
                <p className="text-xs font-bold" style={{ color: "var(--text-muted)" }}>
                  {t("clinician.allergiesLabel")}
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {portal.clinical_snapshot.allergies.length > 0 ? (
                    portal.clinical_snapshot.allergies.map((a) => (
                      <Badge key={a} variant="BLOCKED" label={a} />
                    ))
                  ) : (
                    <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                      {t("common.none")}
                    </span>
                  )}
                </div>
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <div className="neu-inset p-3.5 space-y-2">
                <p className="text-xs font-bold flex items-center gap-1.5" style={{ color: "var(--text-muted)" }}>
                  <Pill className="h-3.5 w-3.5" style={{ color: "var(--accent)" }} aria-hidden="true" />
                  <span>{t("clinician.medicinesLabel")}</span>
                </p>
                {portal.clinical_snapshot.medicines.length === 0 ? (
                  <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                    {t("clinician.noMedicines")}
                  </p>
                ) : (
                  <div className="space-y-1.5">
                    {portal.clinical_snapshot.medicines.map((m, idx) => (
                      <div key={idx} className="text-xs flex flex-wrap justify-between gap-2">
                        <span className="font-bold" style={{ color: "var(--text)" }}>
                          {m.name_as_written}
                        </span>
                        <span className="font-mono" style={{ color: "var(--text-muted)" }}>
                          {m.drug_class} · {m.timing}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="neu-inset p-3.5 space-y-2">
                <p className="text-xs font-bold" style={{ color: "var(--text-muted)" }}>
                  {t("clinician.adherenceTitle")}
                </p>
                {portal.clinical_snapshot.adherence_30d.total === 0 ? (
                  <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                    {t("clinician.noDoseData")}
                  </p>
                ) : (
                  <div className="space-y-1">
                    {portal.clinical_snapshot.adherence_30d.adherence_pct !== null && (
                      <p className="text-xl font-extrabold font-mono" style={{ color: "var(--accent)" }}>
                        {t("clinician.adherencePct", {
                          pct: portal.clinical_snapshot.adherence_30d.adherence_pct,
                        })}
                      </p>
                    )}
                    <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                      {t("clinician.adherenceCounts", {
                        taken: portal.clinical_snapshot.adherence_30d.taken,
                        late: portal.clinical_snapshot.adherence_30d.taken_late,
                        missed:
                          portal.clinical_snapshot.adherence_30d.missed +
                          portal.clinical_snapshot.adherence_30d.escalated,
                      })}
                    </p>
                  </div>
                )}
              </div>
            </div>

            {portal.clinical_snapshot.recent_meals.length > 0 && (
              <div className="neu-inset p-3.5 space-y-2">
                <p className="text-xs font-bold" style={{ color: "var(--text-muted)" }}>
                  {t("clinician.recentMealsTitle")}
                </p>
                <div className="flex flex-wrap gap-2">
                  {portal.clinical_snapshot.recent_meals.map((rm, idx) => (
                    <span
                      key={idx}
                      className="rounded-full border border-[var(--border-subtle)] px-2.5 py-1 text-xs font-semibold"
                      style={{ color: "var(--text)" }}
                    >
                      {rm.for_date} · {pickLocalized(rm.dish_bn, rm.dish_en)}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </Card>

          {/* Approval Decision Form */}
          <Card variant="raised" className="space-y-4">
            <h2 className="text-lg font-extrabold" style={{ color: "var(--text)" }}>
              {t("clinician.decisionTitle")}
            </h2>

            <Input
              label={t("clinician.regNoLabel")}
              placeholder={t("clinician.regNoPlaceholder")}
              value={regNo}
              onChange={(e) => setRegNo(e.target.value)}
              data-testid="clinician-reg-no"
            />

            <div className="space-y-2">
              <p className="text-sm font-semibold" style={{ color: "var(--text)" }}>
                {t("clinician.presetsLabel")}
              </p>
              <div className="flex flex-wrap gap-2">
                {portal.available_presets.map((pk) => {
                  const active = selectedPresets.includes(pk);
                  return (
                    <button
                      key={pk}
                      type="button"
                      onClick={() => togglePreset(pk)}
                      className={`min-h-[40px] rounded-full px-3.5 py-1.5 text-xs font-bold cursor-pointer ${
                        active ? "skeu-button" : "neu-raised-sm"
                      }`}
                      style={active ? undefined : { color: "var(--text)" }}
                      data-testid={`clinician-preset-${pk}`}
                    >
                      {KNOWN_PRESETS.includes(pk) ? t(`members.presets.${pk}`) : pk}
                    </button>
                  );
                })}
              </div>
            </div>

            <label className="flex items-start gap-2.5 text-xs sm:text-sm font-medium cursor-pointer">
              <input
                type="checkbox"
                checked={applyToMember}
                onChange={(e) => setApplyToMember(e.target.checked)}
                className="mt-0.5 h-4 w-4 accent-[var(--accent)]"
              />
              <span style={{ color: "var(--text)" }}>{t("clinician.applyPresetsCheckbox")}</span>
            </label>

            <div className="space-y-1.5">
              <label htmlFor="clinician-note" className="block text-sm font-semibold" style={{ color: "var(--text)" }}>
                {t("clinician.noteLabel")}
              </label>
              <textarea
                id="clinician-note"
                rows={3}
                value={clinicianNote}
                onChange={(e) => setClinicianNote(e.target.value)}
                placeholder={t("clinician.notePlaceholder")}
                className="neu-inset w-full p-3.5 text-sm placeholder:text-[var(--text-muted)]"
                style={{ color: "var(--text)" }}
                data-testid="clinician-note-input"
              />
            </div>

            <div className="flex flex-wrap gap-3 pt-1">
              <Button
                variant="primary"
                disabled={submitting || !clinicianNote.trim()}
                onClick={() => void handleSubmitDecision("approved")}
                data-testid="clinician-approve-btn"
              >
                <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
                <span>{submitting ? t("common.loading") : t("clinician.approveBtn")}</span>
              </Button>
              <Button
                variant="danger"
                disabled={submitting || !clinicianNote.trim()}
                onClick={() => void handleSubmitDecision("changes_requested")}
                data-testid="clinician-changes-btn"
              >
                <XCircle className="h-4 w-4" aria-hidden="true" />
                <span>{t("clinician.requestChangesBtn")}</span>
              </Button>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}

