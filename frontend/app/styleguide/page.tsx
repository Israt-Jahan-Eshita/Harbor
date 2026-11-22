"use client";

import React, { useMemo, useState } from "react";
import {
  Badge,
  Button,
  Card,
  Input,
  PatientDomeButton,
  Sheet,
  Skeleton,
  Tabs,
  Toggle,
  useToast,
} from "@/components/ui";
import { useI18n } from "@/lib/i18n";
import { computeContrastRatio, DARK_CHECKS, LIGHT_CHECKS } from "@/lib/contrast";
import { useTheme } from "@/lib/theme";

export default function StyleguidePage() {
  const { locale, setLocale, formatNumber, t } = useI18n();
  const { resolvedTheme, setThemeMode } = useTheme();
  const { showToast } = useToast();

  const [sampleInput, setSampleInput] = useState("");
  const [toggleVal, setToggleVal] = useState(true);
  const [tabVal, setTabVal] = useState("neu");
  const [sheetOpen, setSheetOpen] = useState(false);
  const [doseTaken, setDoseTaken] = useState(false);

  const contrastRows = useMemo(() => {
    const activeSet = resolvedTheme === "dark" ? DARK_CHECKS : LIGHT_CHECKS;
    return activeSet.map((row) => {
      const ratio = computeContrastRatio(row.fg, row.bg);
      return { ...row, ratio, pass: ratio >= row.minExpected };
    });
  }, [resolvedTheme]);

  return (
    <div className="space-y-8 py-2">
      {/* Header & Quick Mode Controls */}
      <Card variant="raised" className="space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="space-y-1 max-w-2xl">
            <h1 className="text-2xl sm:text-3xl font-extrabold" style={{ color: "var(--text)" }}>
              {t("styleguide.title")}
            </h1>
            <p className="text-sm sm:text-base" style={{ color: "var(--text-muted)" }}>
              {t("styleguide.subtitle")}
            </p>
          </div>
          <Badge variant="INFO" label={t("styleguide.paletteRule")} />
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <Tabs
            value={locale}
            onChange={(val) => setLocale(val as "bn" | "en")}
            ariaLabel={t("common.languageLabel")}
            options={[
              { id: "bn", label: "বাংলা (BN)" },
              { id: "en", label: "English (EN)" },
            ]}
          />
          <Tabs
            value={resolvedTheme}
            onChange={(val) => setThemeMode(val as "light" | "dark")}
            ariaLabel={t("common.themeLabel")}
            options={[
              { id: "light", label: t("common.lightMode") },
              { id: "dark", label: t("common.darkMode") },
            ]}
          />
        </div>
      </Card>

      {/* Three Material Layers */}
      <section className="space-y-4">
        <h2 className="text-xl font-bold" style={{ color: "var(--text)" }}>
          {t("styleguide.surfacesTitle")}
        </h2>
        <div className="grid gap-5 md:grid-cols-3">
          <Card variant="raised" className="space-y-2">
            <h3 className="font-bold" style={{ color: "var(--text)" }}>
              {t("styleguide.neuRaisedTitle")}
            </h3>
            <p className="text-sm" style={{ color: "var(--text-muted)" }}>
              {t("styleguide.neuRaisedDesc")}
            </p>
          </Card>

          <Card variant="inset" className="space-y-2">
            <h3 className="font-bold" style={{ color: "var(--text)" }}>
              {t("styleguide.neuInsetTitle")}
            </h3>
            <p className="text-sm" style={{ color: "var(--text-muted)" }}>
              {t("styleguide.neuInsetDesc")}
            </p>
          </Card>

          <Card variant="glass" className="space-y-2">
            <h3 className="font-bold" style={{ color: "var(--text)" }}>
              {t("styleguide.glassTitle")}
            </h3>
            <p className="text-sm" style={{ color: "var(--text-muted)" }}>
              {t("styleguide.glassDesc")}
            </p>
          </Card>
        </div>
      </section>

      {/* Status Badges */}
      <Card variant="raised" className="space-y-4">
        <h2 className="text-lg font-bold" style={{ color: "var(--text)" }}>
          {t("styleguide.badgesTitle")}
        </h2>
        <div className="flex flex-wrap gap-3">
          <Badge variant="SAFE_DIRECT" />
          <Badge variant="SAFE_WITH_SPLIT" />
          <Badge variant="BLOCKED" ruleId="PRAWN_ALLERGY" />
          <Badge variant="BLOCKED" ruleId="ACE_INHIBITOR_HIGH_POTASSIUM" />
          <Badge variant="UNVERIFIED" />
          <Badge variant="ESTIMATED" label={`${formatNumber(175)} ৳ (${t("common.estimated")})`} />
        </div>
      </Card>

      {/* Skeuomorphic Hero Dome & Pill Row */}
      <Card variant="plate" className="space-y-5 text-center">
        <h2 className="text-lg font-bold" style={{ color: "var(--text)" }}>
          {t("styleguide.patientHeroTitle")}
        </h2>
        <PatientDomeButton
          label={t("styleguide.patientHeroButton")}
          confirmedLabel={t("styleguide.patientHeroTaken")}
          confirmed={doseTaken}
          onClick={() => setDoseTaken((p) => !p)}
          data-testid="styleguide-dome-btn"
        />
        {doseTaken && (
          <div>
            <Button variant="ghost" onClick={() => setDoseTaken(false)}>
              {t("common.retry")}
            </Button>
          </div>
        )}
      </Card>

      {/* Interactive Controls */}
      <Card variant="raised" className="space-y-5">
        <h2 className="text-lg font-bold" style={{ color: "var(--text)" }}>
          {t("styleguide.controlsTitle")}
        </h2>
        <div className="flex flex-wrap gap-3">
          <Button variant="primary">{t("common.confirm")}</Button>
          <Button variant="neu">{t("common.save")}</Button>
          <Button variant="ghost">{t("common.cancel")}</Button>
          <Button variant="danger">{t("status.BLOCKED")}</Button>
          <Button variant="neu" onClick={() => setSheetOpen(true)} data-testid="open-sample-sheet">
            {t("styleguide.openSheetBtn")}
          </Button>
          <Button
            variant="neu"
            onClick={() => showToast(t("styleguide.toastSample"), "success")}
            data-testid="trigger-sample-toast"
          >
            {t("styleguide.triggerToastBtn")}
          </Button>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <Input
            label={t("styleguide.sampleInputLabel")}
            placeholder={t("styleguide.sampleInputPlaceholder")}
            value={sampleInput}
            onChange={(e) => setSampleInput(e.target.value)}
          />
          <div className="skeu-pill-row p-4 flex flex-col justify-center">
            <Toggle
              checked={toggleVal}
              onChange={setToggleVal}
              label={t("styleguide.sampleToggleLabel")}
            />
          </div>
        </div>

        <Tabs
          value={tabVal}
          onChange={setTabVal}
          options={[
            { id: "neu", label: "Neumorphic" },
            { id: "skeu", label: "Skeuomorphic" },
            { id: "glass", label: "Glass" },
          ]}
        />

        <div className="space-y-2">
          <Skeleton className="h-5 w-1/3" />
          <Skeleton className="h-12 w-full" />
        </div>
      </Card>

      {/* Typography & Conjuncts */}
      <Card variant="raised" className="space-y-2">
        <h2 className="text-lg font-bold" style={{ color: "var(--text)" }}>
          {t("styleguide.typographyTitle")}
        </h2>
        <p className="text-base leading-relaxed" style={{ color: "var(--text)" }}>
          {t("styleguide.typographySample")}
        </p>
      </Card>

      {/* Live WCAG Contrast Audit Table */}
      <Card variant="raised" className="space-y-3">
        <h2 className="text-lg font-bold" style={{ color: "var(--text)" }}>
          {t("styleguide.contrastTitle")} ({resolvedTheme})
        </h2>
        <div tabIndex={0} className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr style={{ color: "var(--text-muted)" }}>
              <th className="py-2 pr-3">{t("styleguide.contrastColPair")}</th>
              <th className="py-2 pr-3">{t("styleguide.contrastColHex")}</th>
              <th className="py-2 pr-3">{t("styleguide.contrastColRatio")}</th>
              <th className="py-2">{t("styleguide.contrastColStatus")}</th>
            </tr>
          </thead>
          <tbody>
            {contrastRows.map((row) => (
              <tr key={row.pair} className="border-t">
                <td className="py-2.5 pr-3 font-semibold">{row.pair}</td>
                <td className="py-2.5 pr-3 font-mono text-xs">
                  <span
                    className="inline-block rounded px-2 py-0.5 font-bold"
                    style={{ backgroundColor: row.bg, color: row.fg, border: "1px solid var(--border-strong)" }}
                  >
                    {row.fg} / {row.bg}
                  </span>
                </td>
                <td className="py-2.5 pr-3 font-mono font-bold">
                  {formatNumber(row.ratio)}:1
                </td>
                <td className="py-2.5 font-bold" style={{ color: row.pass ? "var(--ok)" : "var(--danger)" }}>
                  {row.pass ? "WCAG AA PASS" : "FAIL"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      </Card>

      <Sheet open={sheetOpen} onClose={() => setSheetOpen(false)} title={t("styleguide.sheetTitle")}>
        <p className="text-sm leading-relaxed" style={{ color: "var(--text)" }}>
          {t("styleguide.sheetBody")}
        </p>
      </Sheet>
    </div>
  );
}
