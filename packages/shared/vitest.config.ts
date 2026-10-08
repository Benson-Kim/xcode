import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["tests/**/*.test.ts"],
    coverage: {
      // Always in CI; locally, pass --coverage.
      enabled: process.env.CI === "true",
      provider: "v8",
      // Every source file counts, including ones no test imports.
      include: ["src/**/*.ts"],
      reporter: ["text-summary", "text"],
      // A little under the measured coverage, so deleting tests fails but small changes do not.
      thresholds: { statements: 97, branches: 95, functions: 97, lines: 97 },
    },
  },
});
