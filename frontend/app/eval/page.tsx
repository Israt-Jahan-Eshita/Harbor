"use client";

import React, { useEffect, useState } from "react";
import { Award, Clock } from "lucide-react";
import { Badge, Card, Skeleton } from "@/components/ui";
import { ApiError, EvalResultsResponse, harborApi } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

export default function EvalPage() {
  const { locale, pickLocalized, t } = useI18n();
  const [data, setData] = useState<EvalResultsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    harborApi
      .getEvalResults(locale)
      .then((res) => {
        if (!cancelled) {
          setData(res);
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
  }, [locale, t]);

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl sm:text-3xl font-extrabold" style={{ color: "var(--text)" }}>
          {t("eval.title")}
        </h1>
        <p className="text-sm sm:text-base" style={{ color: "var(--text-muted)" }}>
          {t("eval.subtitle")}
        </p>
      </div>

      {errorMsg && (
        <Card variant="glass">
          <p className="text-sm font-semibold" style={{ color: "var(--danger)" }}>
            {errorMsg}
          </p>
        </Card>
      )}

      {loading ? (
        <Skeleton className="h-48 rounded-[20px]" />
      ) : data ? (
        data.status === "not_run_yet" ? (
          <Card variant="glass" className="space-y-3" data-testid="eval-not-run">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Clock className="h-5 w-5" style={{ color: "var(--saffron-text)" }} aria-hidden="true" />
                <h2 className="text-lg font-extrabold" style={{ color: "var(--text)" }}>
                  {t("eval.notRunTitle")}
                </h2>
              </div>
              <Badge variant="ESTIMATED" label={t("eval.statusLabel")} />
            </div>
            <p className="text-sm" style={{ color: "var(--text)" }}>
              {pickLocalized(data.note_bn, data.note_en) || t("eval.notRunBody")}
            </p>
            <p className="text-xs" style={{ color: "var(--text-muted)" }}>
              {t("eval.notRunBody")}
            </p>
          </Card>
        ) : (
          <div className="space-y-6" data-testid="eval-available">
            <Card variant="glass" className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <Award className="h-5 w-5" style={{ color: "var(--accent)" }} aria-hidden="true" />
                <h2 className="text-lg font-extrabold" style={{ color: "var(--text)" }}>
                  {t("eval.availableLabel")}
                </h2>
              </div>
              <Badge variant="SAFE_DIRECT" label={t("eval.availableLabel")} />
            </Card>

            {data.results && (
              <Card variant="raised" className="space-y-2">
                <h3 className="text-base font-bold" style={{ color: "var(--text)" }}>
                  {t("eval.rawSummaryTitle")}
                </h3>
                <pre className="neu-inset p-4 overflow-x-auto text-xs font-mono" style={{ color: "var(--text)" }}>
                  {JSON.stringify(data.results, null, 2)}
                </pre>
              </Card>
            )}

            {data.markdown && (
              <Card variant="raised" className="space-y-2">
                <h3 className="text-base font-bold" style={{ color: "var(--text)" }}>
                  {t("eval.markdownTitle")}
                </h3>
                <pre className="neu-inset p-4 overflow-x-auto text-xs font-mono whitespace-pre-wrap" style={{ color: "var(--text)" }}>
                  {data.markdown}
                </pre>
              </Card>
            )}
          </div>
        )
      ) : null}
    </div>
  );
}

