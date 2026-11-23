import { expect, test } from "@playwright/test";

test.describe("Harbor Mobile End-to-End Flows (390x844)", () => {
  test("complete caregiver & patient workflows across Light/Dark themes and EN/BN", async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("pageerror", (err) => consoleErrors.push(err.message));

    // 1. Landing -> Welcome -> Quick Demo (DEMO26) -> Dashboard
    await page.goto("/");
    await expect(page.locator("h1")).toBeVisible();
    const landingOverflow = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 4);
    expect(landingOverflow).toBe(true);

    await page.goto("/welcome");
    await page.getByTestId("welcome-quick-demo").click();
    await page.waitForURL("**/dashboard");
    await expect(page.locator("h1")).toBeVisible();
    await expect(page.locator("body")).toContainText("DEMO26");

    // Verify Light <-> Dark mode & EN <-> BN conversion on Dashboard
    await page.getByTestId("theme-toggle").click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await page.getByTestId("theme-toggle").click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");

    await page.getByTestId("lang-toggle").click();
    await expect(page.locator("html")).toHaveAttribute("lang", "en");
    await expect(page.locator("h1")).toContainText("Household Care Overview");
    await page.getByTestId("lang-toggle").click();
    await expect(page.locator("html")).toHaveAttribute("lang", "bn");

    // 2. Daily Menu (/menu): Deterministic suggest (default OFF) + Score breakdown + Excluded panel + Guest Review
    await page.goto("/menu");
    await expect(page.getByTestId("menu-toggle-agent")).toHaveAttribute("aria-checked", "false");
    await page.getByTestId("menu-suggest-btn").click();
    await expect(page.getByTestId("menu-dish-card-0")).toBeVisible();

    await page.getByTestId("menu-score-toggle-0").click();
    await expect(page.getByTestId("menu-score-panel-0")).toBeVisible();

    await page.getByTestId("menu-excluded-panel").getByRole("button").click();
    await expect(page.getByTestId("menu-excluded-panel")).toContainText("লাউ চিংড়ি");

    await page.getByTestId("menu-review-btn").click();
    await page.getByTestId("review-guest-count").fill("2");
    await page.getByTestId("review-apply-btn").click();
    await expect(page.getByTestId("menu-results")).toBeVisible();

    // 3. Stock, Bazar, Engine, Eval, Styleguide, PWA assets
    await page.goto("/stock");
    await expect(page.locator("h1")).toContainText("ভান্ডার");

    await page.goto("/bazar");
    await page.getByTestId("bazar-budget-input").fill("6000");
    await page.getByTestId("bazar-build-btn").click();
    await expect(page.locator("body")).toContainText("আনুমানিক");

    await page.goto("/engine");
    await page.getByTestId("engine-run-btn").click();
    await expect(page.getByTestId("engine-result-card")).toBeVisible();

    await page.goto("/eval");
    await expect(page.getByTestId("eval-available")).toBeVisible();

    await page.goto("/styleguide");
    await expect(page.locator("body")).toContainText("AA PASS");
    await page.getByTestId("theme-toggle").click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await expect(page.locator("body")).toContainText("AA PASS");
    await page.getByTestId("theme-toggle").click();

    // PWA Manifest & Service Worker reachable
    const manifestResp = await page.request.get("/manifest.json");
    expect(manifestResp.status()).toBe(200);
    const swResp = await page.request.get("/sw.js");
    expect(swResp.status()).toBe(200);

    // 4. Reminders Dashboard -> Capture Patient Token Link -> Patient Screen
    await page.goto("/reminders");
    const patientLink = page.locator('a[href^="/patient/"]').first();
    await expect(patientLink).toBeVisible();
    const patientHref = await patientLink.getAttribute("href");
    expect(patientHref).toBeTruthy();

    await page.goto(patientHref!);
    await expect(page.getByTestId("patient-screen")).toBeVisible();
    await expect(page.locator("header")).toHaveCount(0);
    await expect(page.locator("nav")).toHaveCount(0);

    // Assert zero disease or medicine disclosure on Patient View
    const ptTextBn = (await page.getByTestId("patient-screen").innerText()).toLowerCase();
    expect(ptTextBn).not.toMatch(/diabetes|hypertension|enalapril|ckd|kidney/);

    // Check Patient Dark Mode + EN toggle + mobile overflow
    await page.getByTestId("patient-theme-toggle").click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    const patientOverflow = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 4);
    expect(patientOverflow).toBe(true);

    await page.getByTestId("patient-lang-toggle").click();
    const ptTextEn = (await page.getByTestId("patient-screen").innerText()).toLowerCase();
    expect(ptTextEn).not.toMatch(/diabetes|hypertension|enalapril|ckd|kidney/);

    expect(consoleErrors).toEqual([]);
  });
});

