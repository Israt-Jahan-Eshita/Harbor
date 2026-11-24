"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import {
  CheckCircle2,
  Copy,
  CreditCard,
  ExternalLink,
  Mail,
  Send,
  Stethoscope,
} from "lucide-react";
import { AuthGuardNotice } from "@/components/AuthGuardNotice";
import { Badge, Button, Card, Input, Sheet, Skeleton, Tabs, useToast } from "@/components/ui";
import {
  ApiError,
  ClinicianContactMode,
  ClinicianPaymentMethod,
  ClinicianPaymentSummary,
  ClinicianReviewRecord,
  harborApi,
  MemberRecord,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useSession } from "@/lib/session";

const EMPTY_SUMMARY: ClinicianPaymentSummary = {
  total_paid_bdt: 0,
  total_unpaid_bdt: 0,
  paid_count: 0,
  unpaid_count: 0,
  approved_count: 0,
  pending_count: 0,
  changes_requested_count: 0,
};

const KNOWN_PRESETS = ["low_potassium", "low_sodium", "low_gi", "low_purine"];
const PAYMENT_METHODS: ClinicianPaymentMethod[] = ["bkash", "nagad", "card", "cash_clinic"];

export default function ReviewsPage() {
  const { locale, formatNumber, t } = useI18n();
  const { session } = useSession();
  const { showToast } = useToast();

  const [members, setMembers] = useState<MemberRecord[]>([]);
  const [reviews, setReviews] = useState<ClinicianReviewRecord[]>([]);
  const [summary, setSummary] = useState<ClinicianPaymentSummary>(EMPTY_SUMMARY);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const [activeTab, setActiveTab] = useState<"approvals" | "payments">("approvals");

  // Create review form state
  const [memberId, setMemberId] = useState("");
  const [doctorName, setDoctorName] = useState("");
  const [doctorEmail, setDoctorEmail] = useState("");
  const [contactMode, setContactMode] = useState<ClinicianContactMode>("email_invite");
  const [feeBdt, setFeeBdt] = useState("500");
  const [requestNote, setRequestNote] = useState("");
  const [submitting, setSubmitting] = useState(false);

  // Payment sheet state
  const [payTarget, setPayTarget] = useState<ClinicianReviewRecord | null>(null);
  const [payMethod, setPayMethod] = useState<ClinicianPaymentMethod>("bkash");
  const [payRef, setPayRef] = useState("");
  const [paying, setPaying] = useState(false);

  useEffect(() => {
    if (!session) return;
    let cancelled = false;
    Promise.all([
      harborApi.listMembers(session.token, locale),
      harborApi.listClinicianReviews(session.token, locale),
    ])
      .then(([mRes, rRes]) => {
        if (cancelled) return;
        const mList = mRes.members || [];
        setMembers(mList);
        const queryMemberId =
          typeof window !== "undefined"
            ? new URLSearchParams(window.location.search).get("memberId") || ""
            : "";
        const validPreferred = mList.find((m) => m.id === queryMemberId)?.id;
        setMemberId((prev) => prev || validPreferred || mList[0]?.id || "");
        setReviews(rRes.reviews || []);
        setSummary(rRes.payment_summary || EMPTY_SUMMARY);
        setErrorMsg(null);
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setErrorMsg(err instanceof ApiError ? err.message : t("common.errorUnexpected"));
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [session, locale, t]);

  async function refreshReviews(token: string) {
    const res = await harborApi.listClinicianReviews(token, locale);
    setReviews(res.reviews || []);
    setSummary(res.payment_summary || EMPTY_SUMMARY);
  }

  async function handleCreateReview(e: React.FormEvent) {
    e.preventDefault();
    if (!session || !memberId || !doctorName.trim()) return;
    setSubmitting(true);
    try {
      const origin = typeof window !== "undefined" ? window.location.origin : null;
      await harborApi.createClinicianReview(
        {
          member_id: memberId,
          doctor_name: doctorName.trim(),
          doctor_email: doctorEmail.trim() || null,
          contact_mode: contactMode,
          fee_bdt: Math.max(0, Number(feeBdt) || 0),
          request_note: requestNote.trim() || null,
          frontend_origin: origin,
        },
        session.token,
        locale,
      );
      await refreshReviews(session.token);
      setDoctorName("");
      setDoctorEmail("");
      setRequestNote("");
      showToast(t("reviews.createSuccess"), "success");
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("common.errorUnexpected"), "error");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleConfirmPayment(e: React.FormEvent) {
    e.preventDefault();
    if (!session || !payTarget) return;
    setPaying(true);
    try {
      await harborApi.payClinicianReview(
        payTarget.id,
        {
          payment_method: payMethod,
          payment_ref: payRef.trim() || null,
        },
        session.token,
        locale,
      );
      await refreshReviews(session.token);
      setPayTarget(null);
      setPayRef("");
      showToast(t("reviews.paySuccess"), "success");
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("common.errorUnexpected"), "error");
    } finally {
      setPaying(false);
    }
  }

  function fullPortalUrl(urlPath: string): string {
    if (typeof window !== "undefined") {
      return `${window.location.origin}${urlPath}`;
    }
    return urlPath;
  }

  function buildMailtoHref(r: ClinicianReviewRecord): string {
    const recipient = r.doctor_email || "";
    const subject = encodeURIComponent(
      `Harbor Care Plan Review — ${r.member_name}`,
    );
    const body = encodeURIComponent(
      `Dear ${r.doctor_name},\n\n` +
        `Please review ${r.member_name}'s 30-day dietary and medication summary and submit your approval:\n` +
        `${fullPortalUrl(r.review_url_path)}\n\n` +
        (r.request_note ? `Family Note: ${r.request_note}\n\n` : "") +
        `Consultation Fee: BDT ${r.fee_bdt} (${r.payment_status})\n`,
    );
    return `mailto:${recipient}?subject=${subject}&body=${body}`;
  }

  function renderStatusBadge(status: string) {
    if (status === "approved") {
      return <Badge variant="SAFE_DIRECT" label={t("reviews.statusApproved")} />;
    }
    if (status === "changes_requested") {
      return <Badge variant="BLOCKED" label={t("reviews.statusChangesRequested")} />;
    }
    return <Badge variant="SAFE_WITH_SPLIT" label={t("reviews.statusPending")} />;
  }

  function renderPaymentBadge(paymentStatus: string) {
    if (paymentStatus === "paid") {
      return <Badge variant="SAFE_DIRECT" label={t("reviews.payPaid")} />;
    }
    if (paymentStatus === "waived") {
      return <Badge variant="INFO" label={t("reviews.payWaived")} />;
    }
    return <Badge variant="ESTIMATED" label={t("reviews.payUnpaid")} />;
  }

  function emailStatusLabel(status: string): string {
    if (status === "sent") return t("reviews.emailSent");
    if (status === "link_ready") return t("reviews.emailLinkReady");
    if (status === "failed") return t("reviews.emailFailed");
    return t("reviews.emailNotRequested");
  }

  if (!session) return <AuthGuardNotice />;

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl sm:text-3xl font-extrabold flex items-center gap-2.5" style={{ color: "var(--text)" }}>
          <Stethoscope className="h-7 w-7 shrink-0" style={{ color: "var(--accent)" }} aria-hidden="true" />
          <span>{t("reviews.title")}</span>
        </h1>
        <p className="text-sm sm:text-base" style={{ color: "var(--text-muted)" }}>
          {t("reviews.subtitle")}
        </p>
      </div>

      {/* Summary Cards */}
      <div className="grid gap-3 grid-cols-2 lg:grid-cols-4">
        <Card variant="raised" className="space-y-1">
          <p className="text-xs font-semibold" style={{ color: "var(--text-muted)" }}>
            {t("reviews.statApproved")}
          </p>
          <p className="text-2xl font-extrabold font-mono" style={{ color: "var(--ok)" }}>
            {formatNumber(summary.approved_count)}
          </p>
        </Card>
        <Card variant="raised" className="space-y-1">
          <p className="text-xs font-semibold" style={{ color: "var(--text-muted)" }}>
            {t("reviews.statPending")}
          </p>
          <p className="text-2xl font-extrabold font-mono" style={{ color: "var(--saffron-text)" }}>
            {formatNumber(summary.pending_count)}
          </p>
        </Card>
        <Card variant="raised" className="space-y-1">
          <p className="text-xs font-semibold" style={{ color: "var(--text-muted)" }}>
            {t("reviews.statPaidTotal")}
          </p>
          <p className="text-2xl font-extrabold font-mono" style={{ color: "var(--accent)" }}>
            {formatNumber(summary.total_paid_bdt)} {t("common.bdt")}
          </p>
        </Card>
        <Card variant="raised" className="space-y-1">
          <p className="text-xs font-semibold" style={{ color: "var(--text-muted)" }}>
            {t("reviews.statUnpaidTotal")}
          </p>
          <p className="text-2xl font-extrabold font-mono" style={{ color: "var(--text)" }}>
            {formatNumber(summary.total_unpaid_bdt)} {t("common.bdt")}
          </p>
        </Card>
      </div>

      {/* Create Request Form */}
      <Card variant="raised" className="space-y-4">
        <div className="space-y-1">
          <h2 className="text-lg font-extrabold" style={{ color: "var(--text)" }}>
            {t("reviews.formTitle")}
          </h2>
          <p className="text-xs sm:text-sm" style={{ color: "var(--text-muted)" }}>
            {t("reviews.formDesc")}
          </p>
        </div>

        <form onSubmit={handleCreateReview} className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <label htmlFor="review-member" className="block text-sm font-semibold" style={{ color: "var(--text)" }}>
                {t("reviews.memberLabel")}
              </label>
              <select
                id="review-member"
                value={memberId}
                onChange={(e) => setMemberId(e.target.value)}
                required
                className="neu-inset w-full min-h-[46px] px-3 py-2 text-sm"
                style={{ color: "var(--text)" }}
                data-testid="review-member-select"
              >
                {members.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name} ({t(`members.roles.${m.role}`)})
                  </option>
                ))}
              </select>
            </div>

            <div className="space-y-1.5">
              <span className="block text-sm font-semibold" style={{ color: "var(--text)" }}>
                {t("reviews.contactModeLabel")}
              </span>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => setContactMode("email_invite")}
                  className={`min-h-[46px] rounded-[12px] px-3 py-2 text-xs font-bold cursor-pointer ${
                    contactMode === "email_invite" ? "skeu-button" : "neu-raised-sm"
                  }`}
                  style={contactMode === "email_invite" ? undefined : { color: "var(--text)" }}
                >
                  {t("reviews.modeEmailInvite")}
                </button>
                <button
                  type="button"
                  onClick={() => setContactMode("family_direct")}
                  className={`min-h-[46px] rounded-[12px] px-3 py-2 text-xs font-bold cursor-pointer ${
                    contactMode === "family_direct" ? "skeu-button" : "neu-raised-sm"
                  }`}
                  style={contactMode === "family_direct" ? undefined : { color: "var(--text)" }}
                >
                  {t("reviews.modeFamilyDirect")}
                </button>
              </div>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-3">
            <Input
              label={t("reviews.doctorNameLabel")}
              placeholder={t("reviews.doctorNamePlaceholder")}
              value={doctorName}
              onChange={(e) => setDoctorName(e.target.value)}
              required
              data-testid="review-doctor-name"
            />
            <Input
              label={t("reviews.doctorEmailLabel")}
              placeholder={t("reviews.doctorEmailPlaceholder")}
              type="email"
              value={doctorEmail}
              onChange={(e) => setDoctorEmail(e.target.value)}
              required={contactMode === "email_invite"}
              data-testid="review-doctor-email"
            />
            <Input
              label={t("reviews.feeLabel")}
              type="number"
              min={0}
              max={50000}
              value={feeBdt}
              onChange={(e) => setFeeBdt(e.target.value)}
              required
              data-testid="review-fee-input"
            />
          </div>

          <div className="space-y-1.5">
            <label htmlFor="review-note" className="block text-sm font-semibold" style={{ color: "var(--text)" }}>
              {t("reviews.requestNoteLabel")}
            </label>
            <textarea
              id="review-note"
              rows={2}
              value={requestNote}
              onChange={(e) => setRequestNote(e.target.value)}
              placeholder={t("reviews.requestNotePlaceholder")}
              className="neu-inset w-full p-3 text-sm placeholder:text-[var(--text-muted)]"
              style={{ color: "var(--text)" }}
            />
          </div>

          <Button
            type="submit"
            variant="primary"
            disabled={submitting || !memberId || !doctorName.trim()}
            data-testid="review-submit-btn"
          >
            <Send className="h-4 w-4" aria-hidden="true" />
            <span>{submitting ? t("common.loading") : t("reviews.submitBtn")}</span>
          </Button>
        </form>
      </Card>

      {errorMsg && (
        <Card variant="glass">
          <p className="text-sm font-semibold" style={{ color: "var(--danger)" }}>
            {errorMsg}
          </p>
        </Card>
      )}

      {/* History Tabs */}
      <Tabs
        value={activeTab}
        onChange={(id) => setActiveTab(id as "approvals" | "payments")}
        options={[
          { id: "approvals", label: t("reviews.tabApprovals"), "data-testid": "tab-approvals" },
          { id: "payments", label: t("reviews.tabPayments"), "data-testid": "tab-payments" },
        ]}
      />

      {loading ? (
        <Skeleton className="h-44 rounded-[18px]" />
      ) : activeTab === "approvals" ? (
        reviews.length === 0 ? (
          <Card variant="inset" className="py-10 text-center">
            <p className="text-sm" style={{ color: "var(--text-muted)" }}>
              {t("reviews.emptyApprovals")}
            </p>
          </Card>
        ) : (
          <div className="space-y-4">
            {reviews.map((r) => (
              <Card key={r.id} variant="raised" className="space-y-4" data-testid="review-history-card">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="text-base font-extrabold" style={{ color: "var(--text)" }}>
                        {r.member_name} — {r.doctor_name}
                      </h3>
                      {renderStatusBadge(r.status)}
                      {renderPaymentBadge(r.payment_status)}
                    </div>
                    <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                      {emailStatusLabel(r.email_status)}
                      {r.doctor_email ? ` · ${r.doctor_email}` : ""} ·{" "}
                      {t("reviews.requestedAtLabel")}: {new Date(r.created_at).toLocaleString()}
                    </p>
                  </div>

                  <span className="font-mono text-base font-extrabold" style={{ color: "var(--accent)" }}>
                    {formatNumber(r.fee_bdt)} {t("common.bdt")}
                  </span>
                </div>

                {r.request_note && (
                  <p className="text-xs neu-inset p-3" style={{ color: "var(--text)" }}>
                    {r.request_note}
                  </p>
                )}

                {r.status !== "pending" && (
                  <div className="neu-inset p-3.5 space-y-2">
                    <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                      <span className="font-bold" style={{ color: "var(--ok)" }}>
                        {t("reviews.regNoLabel")}: {r.clinician_reg_no || "—"}
                      </span>
                      {r.reviewed_at && (
                        <span style={{ color: "var(--text-muted)" }}>
                          {t("reviews.reviewedAtLabel")}: {new Date(r.reviewed_at).toLocaleString()}
                        </span>
                      )}
                    </div>
                    {r.clinician_note && (
                      <p className="text-sm font-medium" style={{ color: "var(--text)" }}>
                        {t("reviews.doctorNoteLabel")}: {r.clinician_note}
                      </p>
                    )}
                    {r.approved_diet_presets.length > 0 && (
                      <div className="flex flex-wrap items-center gap-1.5 pt-1">
                        <span className="text-xs font-semibold" style={{ color: "var(--text-muted)" }}>
                          {t("reviews.approvedPresetsLabel")}:
                        </span>
                        {r.approved_diet_presets.map((pk) => (
                          <Badge
                            key={pk}
                            variant="INFO"
                            label={KNOWN_PRESETS.includes(pk) ? t(`members.presets.${pk}`) : pk}
                          />
                        ))}
                      </div>
                    )}
                  </div>
                )}

                <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-[var(--border-subtle)]">
                  {r.payment_status === "unpaid" && (
                    <Button
                      variant="primary"
                      className="!min-h-[40px] !px-3.5 !py-1.5 !text-xs"
                      onClick={() => {
                        setPayTarget(r);
                        setPayMethod("bkash");
                        setPayRef("");
                      }}
                      data-testid="review-pay-btn"
                    >
                      <CreditCard className="h-3.5 w-3.5" aria-hidden="true" />
                      <span>{t("reviews.payFeeBtn")}</span>
                    </Button>
                  )}

                  <Button
                    variant="neu"
                    className="!min-h-[40px] !px-3.5 !py-1.5 !text-xs"
                    onClick={() => {
                      if (typeof window !== "undefined") {
                        void navigator.clipboard.writeText(fullPortalUrl(r.review_url_path));
                        showToast(t("common.copied"), "success");
                      }
                    }}
                  >
                    <Copy className="h-3.5 w-3.5" aria-hidden="true" />
                    <span>{t("reviews.copyLinkBtn")}</span>
                  </Button>

                  {r.doctor_email && (
                    <a
                      href={buildMailtoHref(r)}
                      className="neu-raised-sm inline-flex min-h-[40px] items-center gap-1.5 px-3.5 py-1.5 text-xs font-bold"
                      style={{ color: "var(--text)" }}
                    >
                      <Mail className="h-3.5 w-3.5" style={{ color: "var(--accent)" }} aria-hidden="true" />
                      <span>{t("reviews.emailDraftBtn")}</span>
                    </a>
                  )}

                  <Link
                    href={r.review_url_path}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="neu-raised-sm inline-flex min-h-[40px] items-center gap-1.5 px-3.5 py-1.5 text-xs font-bold"
                    style={{ color: "var(--accent)" }}
                  >
                    <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                    <span>{t("reviews.openPortalBtn")}</span>
                  </Link>
                </div>
              </Card>
            ))}
          </div>
        )
      ) : reviews.length === 0 ? (
        <Card variant="inset" className="py-10 text-center">
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>
            {t("reviews.emptyPayments")}
          </p>
        </Card>
      ) : (
        <div className="space-y-3">
          {reviews.map((r) => (
            <Card key={r.id} variant="raised" className="flex flex-wrap items-center justify-between gap-3">
              <div className="space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-bold text-sm" style={{ color: "var(--text)" }}>
                    {r.member_name} · {r.doctor_name}
                  </span>
                  {renderPaymentBadge(r.payment_status)}
                </div>
                <p className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                  {r.payment_method ? t(`reviews.methods.${r.payment_method}`) : "—"} •{" "}
                  {t("reviews.refLabel")}: {r.payment_ref || "—"} •{" "}
                  {r.paid_at
                    ? `${t("reviews.paidAtLabel")}: ${new Date(r.paid_at).toLocaleString()}`
                    : `${t("reviews.requestedAtLabel")}: ${new Date(r.created_at).toLocaleDateString()}`}
                </p>
              </div>
              <div className="flex items-center gap-3">
                <span className="font-mono text-base font-extrabold" style={{ color: "var(--accent)" }}>
                  {formatNumber(r.fee_bdt)} {t("common.bdt")}
                </span>
                {r.payment_status === "unpaid" && (
                  <Button
                    variant="primary"
                    className="!min-h-[38px] !px-3 !py-1 !text-xs"
                    onClick={() => {
                      setPayTarget(r);
                      setPayMethod("bkash");
                      setPayRef("");
                    }}
                  >
                    {t("reviews.payFeeBtn")}
                  </Button>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Payment Modal */}
      <Sheet
        open={Boolean(payTarget)}
        onClose={() => setPayTarget(null)}
        title={t("reviews.paySheetTitle")}
      >
        {payTarget && (
          <form onSubmit={handleConfirmPayment} className="space-y-4">
            <div className="neu-inset p-3 space-y-1 text-sm">
              <p className="font-bold" style={{ color: "var(--text)" }}>
                {payTarget.member_name} — {payTarget.doctor_name}
              </p>
              <p className="font-mono font-extrabold" style={{ color: "var(--accent)" }}>
                {formatNumber(payTarget.fee_bdt)} {t("common.bdt")}
              </p>
            </div>

            <div className="space-y-1.5">
              <p className="text-sm font-semibold" style={{ color: "var(--text)" }}>
                {t("reviews.payMethodLabel")}
              </p>
              <div className="grid grid-cols-2 gap-2">
                {PAYMENT_METHODS.map((pm) => {
                  const active = pm === payMethod;
                  return (
                    <button
                      key={pm}
                      type="button"
                      onClick={() => setPayMethod(pm)}
                      className={`min-h-[42px] rounded-[12px] px-3 py-2 text-xs font-bold cursor-pointer ${
                        active ? "skeu-button" : "neu-raised-sm"
                      }`}
                      style={active ? undefined : { color: "var(--text)" }}
                    >
                      {t(`reviews.methods.${pm}`)}
                    </button>
                  );
                })}
              </div>
            </div>

            <Input
              label={t("reviews.payRefLabel")}
              placeholder={t("reviews.payRefPlaceholder")}
              value={payRef}
              onChange={(e) => setPayRef(e.target.value)}
            />

            <div className="flex justify-end gap-3 pt-1">
              <Button variant="ghost" onClick={() => setPayTarget(null)}>
                {t("common.cancel")}
              </Button>
              <Button type="submit" variant="primary" disabled={paying} data-testid="review-pay-confirm">
                <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
                <span>{paying ? t("common.loading") : t("reviews.payConfirmBtn")}</span>
              </Button>
            </div>
          </form>
        )}
      </Sheet>
    </div>
  );
}

