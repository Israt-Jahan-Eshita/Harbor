import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  use: {
    baseURL: "http://localhost:3000",
    channel: "chrome",
    headless: true,
    viewport: { width: 390, height: 844 },
    locale: "bn-BD",
  },
});

