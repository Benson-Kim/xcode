import { defineConfig } from "vitest/config";
export default defineConfig({ test: { environment: "jsdom", setupFiles: ["./tests/setup.ts"], restoreMocks: true }, oxc: { jsx: { runtime: "automatic" } } });
