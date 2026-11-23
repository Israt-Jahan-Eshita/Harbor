export interface ContrastCheckRow {
  pair: string;
  fg: string;
  bg: string;
  minExpected: number;
}

export const LIGHT_CHECKS: ContrastCheckRow[] = [
  { pair: "Primary Text / Background", fg: "#241F1B", bg: "#F6F2EA", minExpected: 4.5 },
  { pair: "Muted Text / Background", fg: "#5F554B", bg: "#F6F2EA", minExpected: 4.5 },
  { pair: "On-Accent / Terracotta", fg: "#FFFDF9", bg: "#A84925", minExpected: 4.5 },
  { pair: "Terracotta / Background", fg: "#A84925", bg: "#F6F2EA", minExpected: 4.5 },
  { pair: "On-Saffron / Saffron", fg: "#241F1B", bg: "#D9A441", minExpected: 4.5 },
  { pair: "On-Danger / Brick", fg: "#FFFDF9", bg: "#B3402F", minExpected: 4.5 },
  { pair: "On-OK / Deep Gold", fg: "#FFFDF9", bg: "#785B17", minExpected: 4.5 },
];

export const DARK_CHECKS: ContrastCheckRow[] = [
  { pair: "Primary Text / Background", fg: "#F2EBE0", bg: "#181411", minExpected: 4.5 },
  { pair: "Muted Text / Surface", fg: "#BEB3A4", bg: "#211C17", minExpected: 4.5 },
  { pair: "On-Accent / Terracotta", fg: "#181411", bg: "#E07A52", minExpected: 4.5 },
  { pair: "On-Saffron / Saffron", fg: "#181411", bg: "#E8B04E", minExpected: 4.5 },
  { pair: "On-Danger / Brick", fg: "#181411", bg: "#E97866", minExpected: 4.5 },
  { pair: "On-OK / Gold", fg: "#181411", bg: "#D9B25A", minExpected: 4.5 },
];

function linearizeChannel(c: number): number {
  const s = c / 255;
  return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
}

function relativeLuminance(hex: string): number {
  const clean = hex.replace("#", "");
  const r = parseInt(clean.slice(0, 2), 16);
  const g = parseInt(clean.slice(2, 4), 16);
  const b = parseInt(clean.slice(4, 6), 16);
  return (
    0.2126 * linearizeChannel(r) +
    0.7152 * linearizeChannel(g) +
    0.0722 * linearizeChannel(b)
  );
}

export function computeContrastRatio(fgHex: string, bgHex: string): number {
  const l1 = relativeLuminance(fgHex);
  const l2 = relativeLuminance(bgHex);
  const lighter = Math.max(l1, l2);
  const darker = Math.min(l1, l2);
  return Number(((lighter + 0.05) / (darker + 0.05)).toFixed(2));
}

