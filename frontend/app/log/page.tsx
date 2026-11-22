"use client";

import React, { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { CheckCircle2, Mic, Send, Square, Trash2, Utensils } from "lucide-react";
import { AuthGuardNotice } from "@/components/AuthGuardNotice";
import { Badge, Button, Card, Input, useToast } from "@/components/ui";
import {
  ApiError,
  ConfirmedEventPayload,
  EventParseResponse,
  EventProposal,
  EventsConfirmResponse,
  harborApi,
  StockItem,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useSession } from "@/lib/session";

export default function LogEventsPage() {
  const { locale, formatNumber, pickLocalized, t } = useI18n();
  const { session } = useSession();
  const { showToast } = useToast();

  const [textInput, setTextInput] = useState("");
  const [parsing, setParsing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [recording, setRecording] = useState(false);
  const [recordSeconds, setRecordSeconds] = useState(0);

  const [stockOptions, setStockOptions] = useState<StockItem[]>([]);
  const [parsedResult, setParsedResult] = useState<EventParseResponse | null>(null);
  const [proposals, setProposals] = useState<EventProposal[]>([]);
  const [commitResult, setCommitResult] = useState<EventsConfirmResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!session) return;
    let cancelled = false;
    harborApi
      .getStock(session.token, locale)
      .then((res) => {
        if (!cancelled) setStockOptions(res.items);
      })
      .catch(() => {
        /* stock options optional fallback */
      });
    return () => {
      cancelled = true;
    };
  }, [session, locale]);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  async function handleParseText(e: React.FormEvent) {
    e.preventDefault();
    if (!session || !textInput.trim()) return;
    setParsing(true);
    setErrorMsg(null);
    setCommitResult(null);
    try {
      const res = await harborApi.parseEventsText(textInput.trim(), session.token, locale);
      setParsedResult(res);
      setProposals(res.proposals);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : t("common.errorUnexpected");
      setErrorMsg(msg);
      showToast(msg, "error");
    } finally {
      setParsing(false);
    }
  }

  async function handleStartVoice() {
    if (!session) return;
    if (
      typeof window === "undefined" ||
      !navigator.mediaDevices?.getUserMedia ||
      typeof MediaRecorder === "undefined"
    ) {
      showToast(t("log.voiceUnsupported"), "info");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const rec = new MediaRecorder(stream);
      chunksRef.current = [];
      rec.ondataavailable = (ev) => {
        if (ev.data.size > 0) chunksRef.current.push(ev.data);
      };
      rec.onstop = async () => {
        stream.getTracks().forEach((tr) => tr.stop());
        if (timerRef.current) clearInterval(timerRef.current);
        setRecording(false);
        setRecordSeconds(0);
        const audioBlob = new Blob(chunksRef.current, { type: "audio/webm" });
        chunksRef.current = [];
        setParsing(true);
        setErrorMsg(null);
        setCommitResult(null);
        try {
          const res = await harborApi.parseEventsAudio(audioBlob, session.token, locale);
          setParsedResult(res);
          setProposals(res.proposals);
        } catch (err) {
          const msg = err instanceof ApiError ? err.message : t("common.errorUnexpected");
          setErrorMsg(msg);
          showToast(msg, "error");
        } finally {
          setParsing(false);
        }
      };
      recorderRef.current = rec;
      rec.start();
      setRecording(true);
      setRecordSeconds(0);
      timerRef.current = setInterval(() => setRecordSeconds((s) => s + 1), 1000);
    } catch {
      showToast(t("log.voiceUnsupported"), "info");
    }
  }

  function handleStopVoice() {
    recorderRef.current?.stop();
  }

  function updateProposal(proposalId: string, patch: Partial<EventProposal>) {
    setProposals((prev) =>
      prev.map((p) => (p.proposal_id === proposalId ? { ...p, ...patch } : p)),
    );
  }

  function removeProposal(proposalId: string) {
    setProposals((prev) => prev.filter((p) => p.proposal_id !== proposalId));
  }

  async function handleConfirmAll() {
    if (!session || !parsedResult || proposals.length === 0) return;
    setConfirming(true);
    setErrorMsg(null);
    try {
      const payloadEvents: ConfirmedEventPayload[] = proposals.map((p) => ({
        type: p.type,
        ingredient_key: p.ingredient_key || undefined,
        qty_base: p.qty_base ?? undefined,
        source: parsedResult.source === "voice" ? "voice" : "text",
        raw_text: parsedResult.raw_text,
        guest_count: p.guest_count ?? undefined,
        for_date: p.for_date || undefined,
        guest_restrictions: p.guest_restrictions,
      }));
      const res = await harborApi.confirmEvents(
        parsedResult.confirmation_token,
        payloadEvents,
        session.token,
        locale,
      );
      setCommitResult(res);
      setProposals([]);
      setParsedResult(null);
      setTextInput("");
      showToast(t("common.confirm"), "success");
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
      <div className="space-y-1">
        <h1 className="text-2xl sm:text-3xl font-extrabold" style={{ color: "var(--text)" }}>
          {t("log.title")}
        </h1>
        <p className="text-sm sm:text-base" style={{ color: "var(--text-muted)" }}>
          {t("log.subtitle")}
        </p>
      </div>

      {/* Input Card */}
      <Card variant="raised" className="space-y-4">
        <form onSubmit={handleParseText} className="space-y-4">
          <div className="space-y-1.5">
            <label className="block text-sm font-bold" style={{ color: "var(--text)" }}>
              {t("log.textLabel")}
            </label>
            <textarea
              rows={3}
              value={textInput}
              onChange={(e) => setTextInput(e.target.value)}
              placeholder={t("log.textPlaceholder")}
              className="neu-inset w-full p-4 text-base placeholder:text-[var(--text-muted)]"
              style={{ color: "var(--text)" }}
              data-testid="log-text-input"
            />
          </div>

          <div className="space-y-2">
            <p className="text-xs font-semibold" style={{ color: "var(--text-muted)" }}>
              {t("log.quickSamplesLabel")}
            </p>
            <div className="flex flex-wrap gap-2">
              {[t("log.sample1"), t("log.sample2"), t("log.sample3")].map((sample, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => setTextInput(sample)}
                  className="neu-raised-sm px-3 py-1.5 text-xs font-semibold cursor-pointer"
                  style={{ color: "var(--text)" }}
                >
                  {sample}
                </button>
              ))}
            </div>
          </div>

          <div className="flex flex-wrap gap-3">
            <Button
              type="submit"
              variant="primary"
              disabled={parsing || !textInput.trim()}
              data-testid="log-parse-submit"
            >
              <Send className="h-4 w-4" aria-hidden="true" />
              <span>{parsing ? t("common.loading") : t("log.parseTextBtn")}</span>
            </Button>
            {!recording && (
              <Button
                variant="neu"
                onClick={handleStartVoice}
                disabled={parsing}
                data-testid="log-voice-start"
              >
                <Mic className="h-4 w-4" style={{ color: "var(--accent)" }} aria-hidden="true" />
                <span>{t("log.recordVoiceBtn")}</span>
              </Button>
            )}
          </div>
        </form>
      </Card>

      {/* Glass Recording Overlay */}
      {recording && (
        <Card variant="glass" className="flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="space-y-1">
            <p className="text-base font-bold" style={{ color: "var(--accent)" }}>
              {t("log.recordingHint")}
            </p>
            <p className="font-mono text-lg font-extrabold" style={{ color: "var(--text)" }}>
              00:{String(recordSeconds).padStart(2, "0")}
            </p>
          </div>
          <Button variant="danger" onClick={handleStopVoice}>
            <Square className="h-4 w-4" aria-hidden="true" />
            <span>{t("log.stopVoiceBtn")}</span>
          </Button>
        </Card>
      )}

      {errorMsg && (
        <Card variant="glass">
          <p className="text-sm font-semibold" style={{ color: "var(--danger)" }}>
            {errorMsg}
          </p>
        </Card>
      )}

      {/* Proposal Confirmation Chips */}
      {parsedResult && (
        <Card variant="raised" className="space-y-4" data-testid="log-proposals-card">
          <div className="space-y-1">
            <h2 className="text-lg font-extrabold" style={{ color: "var(--text)" }}>
              {t("log.proposalsTitle")}
            </h2>
            <p className="text-xs" style={{ color: "var(--text-muted)" }}>
              {t("log.rawTranscriptLabel")}: &ldquo;{parsedResult.raw_text}&rdquo;
            </p>
          </div>

          <div className="space-y-3">
            {proposals.map((p) => {
              const isHouseholdEvent =
                p.type === "GUESTS" || p.type === "GUESTS_CANCELLED" || p.type === "MEMBER_AWAY";
              return (
                <div
                  key={p.proposal_id}
                  className="neu-inset p-4 space-y-3"
                  style={p.needs_review ? { borderColor: "var(--saffron-text)" } : undefined}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant={p.needs_review ? "SAFE_WITH_SPLIT" : "SAFE_DIRECT"} label={p.type} />
                      {p.item_raw && (
                        <span className="text-sm font-bold" style={{ color: "var(--text)" }}>
                          {p.item_raw} ({p.qty_phrase || ""})
                        </span>
                      )}
                    </div>
                    <Button
                      variant="ghost"
                      onClick={() => removeProposal(p.proposal_id)}
                      className="!min-h-[38px] !px-2.5 !py-1 !text-xs"
                    >
                      <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                      <span>{t("log.discardChip")}</span>
                    </Button>
                  </div>

                  {p.needs_review && (
                    <p className="text-xs font-bold" style={{ color: "var(--saffron-text)" }}>
                      {t("log.needsReviewFlag")}
                    </p>
                  )}

                  {isHouseholdEvent ? (
                    <Input
                      label={t("log.guestsCountLabel")}
                      type="number"
                      min={0}
                      value={p.guest_count ?? 0}
                      onChange={(e) =>
                        updateProposal(p.proposal_id, { guest_count: Number(e.target.value) })
                      }
                    />
                  ) : (
                    <div className="grid gap-3 sm:grid-cols-2">
                      <div className="space-y-1.5">
                        <label className="block text-xs font-semibold" style={{ color: "var(--text)" }}>
                          {t("log.selectIngredient")}
                        </label>
                        <select
                          value={p.ingredient_key || ""}
                          onChange={(e) => {
                            const nextKey = e.target.value;
                            const found = stockOptions.find((s) => s.ingredient_key === nextKey);
                            updateProposal(p.proposal_id, {
                              ingredient_key: nextKey || null,
                              unit_base: found?.base_unit || p.unit_base,
                              needs_review: !nextKey || p.qty_base === null,
                            });
                          }}
                          className="neu-inset w-full min-h-[44px] px-3 py-2 text-sm"
                          style={{ color: "var(--text)" }}
                        >
                          <option value="">-- {t("log.selectIngredient")} --</option>
                          {stockOptions.map((item) => (
                            <option key={item.ingredient_key} value={item.ingredient_key}>
                              {pickLocalized(item.name_bn, item.name_en)} ({item.base_unit})
                            </option>
                          ))}
                        </select>
                      </div>
                      <Input
                        label={`${t("log.qtyLabel")} (${p.unit_base || "g/ml"})`}
                        type="number"
                        step="any"
                        value={p.qty_base ?? ""}
                        onChange={(e) => {
                          const val = e.target.value === "" ? null : Number(e.target.value);
                          updateProposal(p.proposal_id, {
                            qty_base: val,
                            needs_review: !p.ingredient_key || val === null,
                          });
                        }}
                      />
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {proposals.length > 0 && (
            <Button
              variant="primary"
              fullWidth
              onClick={handleConfirmAll}
              disabled={confirming}
              data-testid="log-confirm-all"
            >
              <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
              <span>{confirming ? t("common.loading") : t("log.confirmAllBtn")}</span>
            </Button>
          )}
        </Card>
      )}

      {/* Commit Result & Stock Deltas */}
      {commitResult && (
        <Card variant="glass" className="space-y-4">
          {commitResult.stock_deltas.length > 0 && (
            <div className="space-y-2">
              <h2 className="text-base font-bold" style={{ color: "var(--text)" }}>
                {t("log.deltasTitle")}
              </h2>
              {commitResult.stock_deltas.map((d) => (
                <div key={d.ingredient_key} className="neu-inset flex justify-between px-3.5 py-2 text-sm">
                  <span className="font-semibold" style={{ color: "var(--text)" }}>
                    {pickLocalized(d.name_bn, d.name_en)}
                  </span>
                  <span className="font-mono" style={{ color: "var(--accent)" }}>
                    {formatNumber(d.before_qty)} → {formatNumber(d.after_qty)} {d.unit}
                  </span>
                </div>
              ))}
            </div>
          )}

          {commitResult.menu_stale && (
            <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-[var(--border-subtle)]">
              <div>
                <p className="font-bold text-sm" style={{ color: "var(--saffron-text)" }}>
                  {t("log.menuStaleTitle")}
                </p>
                <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                  {t("log.menuStaleDesc")}
                </p>
              </div>
              <Link
                href="/menu"
                className="skeu-button inline-flex min-h-[44px] items-center gap-2 px-4 py-2 text-xs font-bold"
              >
                <Utensils className="h-3.5 w-3.5" aria-hidden="true" />
                <span>{t("log.refreshMenuLink")}</span>
              </Link>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}

