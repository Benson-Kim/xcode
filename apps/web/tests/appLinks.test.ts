import { unstable_doesMiddlewareMatch } from "next/experimental/testing/server";
import { afterEach, expect, it, vi } from "vitest";

import { GET as apple } from "../app/.well-known/apple-app-site-association/route";
import { GET as android } from "../app/.well-known/assetlinks.json/route";
import { config } from "../proxy";

afterEach(() => vi.unstubAllEnvs());

const fingerprint = () =>
  Array.from(crypto.getRandomValues(new Uint8Array(32)), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join(":");

it("serves the iOS association as JSON for the invitation page only", async () => {
  vi.stubEnv("IOS_APP_ID", "ABCDE12345.ke.co.priori.xcode");
  const response = apple();
  expect(response.status).toBe(200);
  expect(response.headers.get("content-type")).toMatch(/^application\/json/);
  expect(response.headers.get("cache-control")).toBe("public, max-age=3600");
  expect(await response.json()).toEqual({
    applinks: {
      details: [
        {
          appIDs: ["ABCDE12345.ke.co.priori.xcode"],
          components: [{ "/": "/invite" }],
        },
      ],
    },
  });
});

it("serves the Android asset links with every signing certificate, in the form Android compares", async () => {
  const upload = fingerprint();
  const store = fingerprint();
  vi.stubEnv("ANDROID_CERT_SHA256", ` ${upload} , ${store}`);
  const response = android();
  expect(response.status).toBe(200);
  expect(response.headers.get("content-type")).toMatch(/^application\/json/);
  expect(await response.json()).toEqual([
    {
      relation: ["delegate_permission/common.handle_all_urls"],
      target: {
        namespace: "android_app",
        package_name: "ke.co.priori.xcode",
        sha256_cert_fingerprints: [upload.toUpperCase(), store.toUpperCase()],
      },
    },
  ]);
});

it("publishes nothing while a setting is missing or malformed", () => {
  for (const appId of [
    undefined,
    "",
    "ke.co.priori.xcode",
    "abc.ke.co.priori.xcode",
  ]) {
    vi.stubEnv("IOS_APP_ID", appId);
    expect(apple().status).toBe(404);
    expect(apple().headers.get("cache-control")).toBe("no-store");
  }
  for (const certs of [
    undefined,
    "",
    "AB:CD",
    `${fingerprint()},not-a-fingerprint`,
  ]) {
    vi.stubEnv("ANDROID_CERT_SHA256", certs);
    expect(android().status).toBe(404);
  }
});

it("keeps the association files out of the page proxy", () => {
  for (const url of [
    "/.well-known/apple-app-site-association",
    "/.well-known/assetlinks.json",
  ])
    expect(unstable_doesMiddlewareMatch({ config, nextConfig: {}, url })).toBe(
      false,
    );
  expect(
    unstable_doesMiddlewareMatch({ config, nextConfig: {}, url: "/invite" }),
  ).toBe(true);
});
