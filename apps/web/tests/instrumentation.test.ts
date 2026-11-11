import { afterEach, expect, it, vi } from "vitest";

import { register } from "../instrumentation";

afterEach(() => vi.unstubAllEnvs());

const production = (hops: string | undefined) => {
  vi.stubEnv("NODE_ENV", "production");
  vi.stubEnv("NEXT_RUNTIME", "nodejs");
  vi.stubEnv("TRUSTED_PROXY_HOPS", hops);
};

it("refuses to start a production server that does not say how many proxies are in front", async () => {
  for (const hops of [undefined, "", " ", "-1", "abc", "1.5"]) {
    production(hops);
    await expect(register()).rejects.toThrow(/TRUSTED_PROXY_HOPS/);
  }
});

it("starts in production with any whole number, 0 included", async () => {
  for (const hops of ["0", "1", " 2 "]) {
    production(hops);
    await expect(register()).resolves.toBeUndefined();
  }
});

it("leaves the build, the edge runtime and development alone", async () => {
  production(undefined);
  vi.stubEnv("NEXT_PHASE", "phase-production-build");
  await expect(register()).resolves.toBeUndefined();
  vi.unstubAllEnvs();
  production(undefined);
  vi.stubEnv("NEXT_RUNTIME", "edge");
  await expect(register()).resolves.toBeUndefined();
  vi.unstubAllEnvs();
  vi.stubEnv("TRUSTED_PROXY_HOPS", undefined);
  vi.stubEnv("NEXT_RUNTIME", "nodejs");
  await expect(register()).resolves.toBeUndefined();
});
