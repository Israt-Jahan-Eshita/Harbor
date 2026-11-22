import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test.describe("Harbor Full Accessibility, Keyboard & 200% Zoom Audit", () => {
  test("axe-core WCAG audit on all routes (Light & Dark), keyboard walkthrough, and 200% zoom", async ({
    page,
  }) => {
    const consoleErrors: string[] = [];
    page.on("pageerror", (err) => consoleErrors.push(err.message));

    // 1. Establish demo caregiver session and capture dynamic member ID + patient token
    await page.goto("/welcome");
    await page.getByTestId("welcome-quick-demo").click();
    await page.waitForURL("**/dashboard");

    await page.goto("/members");
    const memberLink = page.locator('a[href^="/members/"]').first();
    await expect(memberLink).toBeVisible();
    const memberHref = await memberLink.getAttribute("href");
    expect(memberHref).toBeTruthy();

    await page.goto("/reminders");
    const patientLink = page.locator('a[href^="/patient/"]').first();
    await expect(patientLink).toBeVisible();
    const patientHref = await patientLink.getAttribute("href");
    expect(patientHref).toBeTruthy();

    const routes = [
      "/",
      "/welcome",
      "/dashboard",
      "/members",
      memberHref!,
      `${memberHref!}/prescription`,
      "/menu",
      "/log",
      "/stock",
      "/bazar",
      "/reminders",
      "/settings",
      "/engine",
      "/eval",
      "/how-it-works",
      "/styleguide",
      patientHref!,
    ];

    const summary: Array<{ route: string; theme: string; seriousOrCritical: number; total: number }> = [];

    for (const theme of ["light", "dark"] as const) {
      for (const route of routes) {
        await page.goto(route);
        await page.waitForLoadState("networkidle");
        await page.evaluate((targetTheme) => {
          localStorage.setItem("harbor_theme", targetTheme);
          document.documentElement.dataset.theme = targetTheme;
          window.dispatchEvent(new StorageEvent("storage", { key: "harbor_theme", newValue: targetTheme }));
        }, theme);
        await expect(page.locator("html")).toHaveAttribute("data-theme", theme);

        // Wait for async page content if loading skeleton is present
        await page.waitForTimeout(350);

        const axeResults = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
          .analyze();

        const severe = axeResults.violations.filter(
          (v) => v.impact === "serious" || v.impact === "critical",
        );
        summary.push({
          route,
          theme,
          seriousOrCritical: severe.length,
          total: axeResults.violations.length,
        });
        if (severe.length > 0) {
          console.log(
            `AXE_VIOLATION [${theme}] ${route}:`,
            JSON.stringify(
              severe.map((s) => ({
                id: s.id,
                impact: s.impact,
                help: s.help,
                nodes: s.nodes.slice(0, 2).map((n) => n.html),
              })),
            ),
          );
        }
        expect(
          severe,
          `Serious/Critical Axe violations on ${route} (${theme})`,
        ).toEqual([]);
      }
    }

    console.log("AXE_SUMMARY_COUNT:", summary.length, "ROUTES_CLEAN:", summary.filter((s) => s.seriousOrCritical === 0).length);

    // Reset theme to light
    await page.evaluate(() => {
      localStorage.setItem("harbor_theme", "light");
      document.documentElement.dataset.theme = "light";
    });

    // 2. Keyboard-only walkthrough (Tab + Enter without mouse clicks)
    await page.goto("/welcome");
    await page.waitForLoadState("networkidle");
    let reachedQuickDemo = false;
    for (let i = 0; i < 30; i++) {
      await page.keyboard.press("Tab");
      const testId = await page.evaluate(
        () => document.activeElement?.getAttribute("data-testid") || "",
      );
      if (testId === "welcome-quick-demo") {
        reachedQuickDemo = true;
        break;
      }
    }
    expect(reachedQuickDemo).toBe(true);
    await page.keyboard.press("Enter");
    await page.waitForURL("**/dashboard");

    // Keyboard tab onto lang-toggle & nav on /menu
    await page.goto("/menu");
    await page.waitForLoadState("networkidle");
    let reachedSuggest = false;
    for (let i = 0; i < 35; i++) {
      await page.keyboard.press("Tab");
      const testId = await page.evaluate(
        () => document.activeElement?.getAttribute("data-testid") || "",
      );
      if (testId === "menu-suggest-btn") {
        reachedSuggest = true;
        break;
      }
    }
    expect(reachedSuggest).toBe(true);

    // Patient screen keyboard reachability to dome button
    await page.goto(patientHref!);
    await page.waitForLoadState("networkidle");
    let reachedPatientInteractive = false;
    for (let i = 0; i < 15; i++) {
      await page.keyboard.press("Tab");
      const tag = await page.evaluate(() => document.activeElement?.tagName || "");
      if (tag === "BUTTON" || tag === "A") {
        reachedPatientInteractive = true;
        break;
      }
    }
    expect(reachedPatientInteractive).toBe(true);

    // 3. 200% Zoom check at standard desktop viewport (1280x800 zoomed 200% -> 640px CSS width)
    await page.setViewportSize({ width: 1280, height: 800 });
    for (const zRoute of ["/", "/dashboard", "/menu", patientHref!]) {
      await page.goto(zRoute);
      await page.waitForLoadState("networkidle");
      await page.evaluate(() => {
        document.documentElement.style.zoom = "2";
      });
      await page.waitForTimeout(200);
      const fits = await page.evaluate(
        () => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 4,
      );
      console.log(`ZOOM_200 [${zRoute}] fits_without_horizontal_overflow=${fits}`);
      expect(fits, `Horizontal overflow at 200% zoom on ${zRoute}`).toBe(true);
    }

    expect(consoleErrors).toEqual([]);
  });
});

