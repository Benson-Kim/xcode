import { defineConfig } from "vitest/config";
export default defineConfig({ test: { environment: "jsdom", setupFiles: ["./tests/setup.ts"], restoreMocks: true, testTimeout: 20000 }, oxc: { jsx: { runtime: "automatic" } } });
