import { defineConfig } from "vitest/config";

// The browser tests in e2e/ are run by Playwright, not Vitest.
export default defineConfig({
  test: {
    exclude: ["e2e/**", "node_modules/**", ".next/**"],
  },
});
