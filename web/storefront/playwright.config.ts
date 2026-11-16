import { defineConfig, devices } from "@playwright/test";

// Run against any deployed site: BASE_URL=https://staging.example pnpm --filter @sk/storefront e2e
const baseURL = process.env.BASE_URL ?? "http://localhost:3000";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/*.e2e.ts",
  timeout: 60_000,
  retries: 1,
  reporter: [["list"]],
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "android", use: { ...devices["Pixel 5"] } },
    { name: "iphone", use: { ...devices["iPhone 13"] } },
  ],
});
