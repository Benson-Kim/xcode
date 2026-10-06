// @vitest-environment node
import { afterEach, expect, it, vi } from "vitest";

import config from "../next.config";

afterEach(() => vi.unstubAllEnvs());

const headers = async () => Object.fromEntries((await config.headers!())[0].headers.map((header) => [header.key, header.value]));

it("sends HSTS only in production, and the permissions policy and existing headers everywhere", async () => {
  vi.stubEnv("NODE_ENV", "production");
  expect(await headers()).toEqual({
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
  });

  vi.stubEnv("NODE_ENV", "development");
  const development = await headers();
  expect(development["Strict-Transport-Security"]).toBeUndefined();
  expect(development["Permissions-Policy"]).toBe("camera=(), microphone=(), geolocation=()");
  expect(development["X-Frame-Options"]).toBe("DENY");
});
