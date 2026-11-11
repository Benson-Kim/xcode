import type { ExpoConfig } from "expo/config";

import {
  INVITE_PATH,
  refuseSelfUpdate,
  webOrigin,
  withInviteLinks,
} from "../app.config";
import appJson from "../app.json";

const base = appJson.expo as ExpoConfig;
const store = (url?: string) =>
  withInviteLinks(base, {
    EXPO_PUBLIC_DISTRIBUTION: "store",
    EXPO_PUBLIC_WEB_URL: url,
  });

test("both stores get the one app id", () => {
  const config = store("https://xcode.example.co.ke");
  expect(config.ios?.bundleIdentifier).toBe("ke.co.priori.xcode");
  expect(config.android?.package).toBe("ke.co.priori.xcode");
});

test("app data never leaves the phone in a backup", () => {
  expect(store("https://xcode.example.co.ke").android?.allowBackup).toBe(false);
});

test("the app declares only exempt encryption", () => {
  expect(
    store("https://xcode.example.co.ke").ios?.config?.usesNonExemptEncryption,
  ).toBe(false);
});

test("a store build links only the invitation page over verified HTTPS", () => {
  const config = store("https://xcode.example.co.ke");
  expect(config.ios?.associatedDomains).toEqual([
    "applinks:xcode.example.co.ke",
  ]);
  expect(config.android?.intentFilters).toEqual([
    {
      action: "VIEW",
      autoVerify: true,
      category: ["BROWSABLE", "DEFAULT"],
      data: [
        {
          scheme: "https",
          host: "xcode.example.co.ke",
          pathPrefix: INVITE_PATH,
        },
      ],
    },
  ]);
});

test("no custom scheme can open the app with a token", () => {
  const config = store("https://xcode.example.co.ke");
  expect(config.scheme).toBeUndefined();
  for (const filter of config.android?.intentFilters ?? [])
    for (const data of [filter.data ?? []].flat())
      expect(data.scheme).toBe("https");
});

test.each([
  [undefined, "must be set"],
  ["http://xcode.example.co.ke", "HTTPS origin with no port"],
  ["https://xcode.example.co.ke:8443", "HTTPS origin with no port"],
  ["https://xcode.example.co.ke/invite", "no path"],
  ["https://xcode.example.co.ke/?next=x", "no path"],
  ["https://evil.example#xcode.example.co.ke", "no path"],
  ["https://user@xcode.example.co.ke", "no path"],
  ["javascript:alert(1)", "no path"],
])("a store build refuses the web origin %p", (url, message) => {
  expect(() => store(url)).toThrow(message);
});

test("a development build without HTTPS gets no app links", () => {
  for (const url of [
    undefined,
    "http://localhost:3000",
    "https://localhost:3000",
  ]) {
    const config = withInviteLinks(base, { EXPO_PUBLIC_WEB_URL: url });
    expect(config.ios?.associatedDomains).toBeUndefined();
    expect(config.android?.intentFilters).toBeUndefined();
    expect(config.android?.allowBackup).toBe(false);
  }
});

test("a store build refuses an update address; a direct build keeps it", () => {
  const updateUrl = "https://example.com/version.json";
  expect(() =>
    refuseSelfUpdate({
      EXPO_PUBLIC_DISTRIBUTION: "store",
      EXPO_PUBLIC_UPDATE_URL: updateUrl,
    }),
  ).toThrow("must not be set for store builds");
  expect(() =>
    refuseSelfUpdate({ EXPO_PUBLIC_DISTRIBUTION: "store" }),
  ).not.toThrow();
  expect(() =>
    refuseSelfUpdate({
      EXPO_PUBLIC_DISTRIBUTION: "direct",
      EXPO_PUBLIC_UPDATE_URL: updateUrl,
    }),
  ).not.toThrow();
});

test("the web origin keeps only the host", () => {
  expect(webOrigin("https://xcode.example.co.ke/", true)).toEqual({
    secure: true,
    host: "xcode.example.co.ke",
  });
});
