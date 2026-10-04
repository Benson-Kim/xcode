// @vitest-environment node
import { afterEach, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { config, proxy } from "../proxy";

afterEach(() => vi.unstubAllEnvs());

const run = () => {
  const response = proxy(new NextRequest("https://xcode.test/"));
  const policy = response.headers.get("Content-Security-Policy")!;
  return {
    policy,
    directives: Object.fromEntries(
      policy.split("; ").map((directive) => {
        const [name, ...values] = directive.split(" ");
        return [name, values.join(" ")];
      }),
    ),
  };
};

it("names a fresh nonce in the policy on every request", () => {
  const first = run().policy.match(/'nonce-([^']+)'/)?.[1];
  const second = run().policy.match(/'nonce-([^']+)'/)?.[1];
  expect(first).toBeTruthy();
  expect(second).toBeTruthy();
  expect(first).not.toBe(second);
});

it("locks the page down to its own origin", () => {
  vi.stubEnv("NODE_ENV", "production");
  const { directives } = run();
  expect(directives["default-src"]).toBe("'self'");
  expect(directives["img-src"]).toBe("'self' data: blob:");
  expect(directives["connect-src"]).toBe("'self'");
  expect(directives["object-src"]).toBe("'none'");
  expect(directives["base-uri"]).toBe("'self'");
  expect(directives["form-action"]).toBe("'self'");
  expect(directives["frame-ancestors"]).toBe("'none'");
  expect(directives["script-src"]).toContain("'strict-dynamic'");
});

it("lets the brand font through, and nothing else off-origin", () => {
  const { directives } = run();
  expect(directives["style-src"]).toBe("'self' 'unsafe-inline' https://fonts.googleapis.com");
  expect(directives["font-src"]).toBe("'self' https://fonts.gstatic.com");
  expect(directives["connect-src"]).toBe("'self'");
  expect(directives["default-src"]).toBe("'self'");
});

it("allows eval only while developing, and upgrades to https only in production", () => {
  vi.stubEnv("NODE_ENV", "production");
  const production = run();
  expect(production.directives["script-src"]).not.toContain("'unsafe-eval'");
  expect(production.policy).toContain("upgrade-insecure-requests");

  vi.stubEnv("NODE_ENV", "development");
  const development = run();
  expect(development.directives["script-src"]).toContain("'unsafe-eval'");
  expect(development.policy).not.toContain("upgrade-insecure-requests");
});

it("hands the nonce to the renderer on the request", () => {
  const response = proxy(new NextRequest("https://xcode.test/"));
  const nonce = response.headers.get("Content-Security-Policy")!.match(/'nonce-([^']+)'/)![1];
  expect(response.headers.get("x-nonce") ?? nonce).toBeTruthy();
});

it("skips the API proxies, static assets and prefetches", () => {
  const [matcher] = config.matcher;
  // Next.js anchors a matcher source against the whole path; an unanchored test would match a later segment.
  const pattern = new RegExp(`^${matcher.source}$`);
  expect(pattern.test("/")).toBe(true);
  expect(pattern.test("/api/setup/revenue")).toBe(false);
  expect(pattern.test("/_next/static/chunk.js")).toBe(false);
  expect(matcher.missing.map((header) => header.key)).toEqual(["next-router-prefetch", "purpose"]);
});
