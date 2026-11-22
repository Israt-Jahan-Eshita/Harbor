import fs from "node:fs";
import path from "node:path";
import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import StyleguidePage from "@/app/styleguide/page";
import { AppShell } from "@/components/layout/AppShell";
import { computeContrastRatio, DARK_CHECKS, LIGHT_CHECKS } from "@/lib/contrast";
import { Providers } from "@/lib/providers";

vi.mock("next/navigation", () => ({
  usePathname: () => "/styleguide",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));

describe("Design system, EN/BN switcher, Theme switcher and Warm Palette", () => {
  it("contains zero blue, purple, or green hues in tokens.css", () => {
    const css = fs.readFileSync(
      path.resolve(__dirname, "../styles/tokens.css"),
      "utf-8",
    );
    const hexMatches = css.match(/#[0-9a-fA-F]{6}\b/g) || [];
    expect(hexMatches.length).toBeGreaterThan(10);

    for (const hex of hexMatches) {
      const r = parseInt(hex.slice(1, 3), 16);
      const g = parseInt(hex.slice(3, 5), 16);
      const b = parseInt(hex.slice(5, 7), 16);
      // Warm neutral/terracotta/gold/brick palette: red channel is always >= green and >= blue
      expect(r).toBeGreaterThanOrEqual(g);
      expect(r).toBeGreaterThanOrEqual(b);
    }
  });

  it("passes WCAG AA (>= 4.5:1) contrast checks in both light and dark modes", () => {
    for (const row of [...LIGHT_CHECKS, ...DARK_CHECKS]) {
      const ratio = computeContrastRatio(row.fg, row.bg);
      expect(ratio, `${row.pair} (${row.fg} on ${row.bg})`).toBeGreaterThanOrEqual(
        row.minExpected,
      );
    }
  });

  it("toggles entire UI between Bangla and English and Light/Dark modes", () => {
    window.localStorage.clear();
    render(
      <Providers>
        <AppShell>
          <StyleguidePage />
        </AppShell>
      </Providers>,
    );

    // Starts in Bangla & Light mode
    expect(screen.getByText("ডিজাইন সিস্টেম ও স্টাইলগাইড")).toBeInTheDocument();
    expect(document.documentElement.dataset.theme).toBe("light");

    // Toggle to English
    fireEvent.click(screen.getByTestId("lang-toggle"));
    expect(screen.getByText("Design System & Styleguide")).toBeInTheDocument();
    expect(document.documentElement.lang).toBe("en");

    // Toggle back to Bangla
    fireEvent.click(screen.getByTestId("lang-toggle"));
    expect(screen.getByText("ডিজাইন সিস্টেম ও স্টাইলগাইড")).toBeInTheDocument();

    // Toggle Light -> Dark -> Light
    fireEvent.click(screen.getByTestId("theme-toggle"));
    expect(document.documentElement.dataset.theme).toBe("dark");
    fireEvent.click(screen.getByTestId("theme-toggle"));
    expect(document.documentElement.dataset.theme).toBe("light");
  });
});

