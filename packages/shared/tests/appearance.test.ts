import { describe, expect, it } from "vitest";

import {
  BRAND_TOKEN_NAMES,
  deriveBrandTokens,
  resolveTheme,
  sundayWeekNotice,
  sundayWeekNoticeDetail,
  targetsOn,
  type Appearance,
} from "@xcode/shared/appearance";

const branding = {
  primary: "#0B5CAD",
  secondary: "#1B2A4A",
  accent: "#1E6B3A",
};

describe("resolveTheme", () => {
  it.each([
    ["system", true, "dark"],
    ["system", false, "light"],
    ["light", true, "light"],
    ["dark", false, "dark"],
    [undefined, true, "dark"],
    [null, false, "light"],
    ["midnight", false, "light"],
    ["midnight", true, "dark"],
  ] as const)(
    "resolves %s on a device that is dark=%s to %s",
    (mode, deviceDark, expected) => {
      expect(resolveTheme(mode, deviceDark)).toBe(expected);
    },
  );
});

describe("deriveBrandTokens", () => {
  it("mixes the light tokens towards white and black", () => {
    expect(deriveBrandTokens(branding, false)).toEqual([
      { token: "blue", colour: "#0B5CAD", amount: 100, towards: "white" },
      { token: "blueDark", colour: "#0B5CAD", amount: 80, towards: "black" },
      { token: "blueBusy", colour: "#0B5CAD", amount: 80, towards: "white" },
      { token: "blueSoft", colour: "#0B5CAD", amount: 10, towards: "white" },
      { token: "blueTint", colour: "#0B5CAD", amount: 7, towards: "white" },
      { token: "blueWash", colour: "#0B5CAD", amount: 4, towards: "white" },
      { token: "brand", colour: "#1B2A4A", amount: 100, towards: "white" },
      { token: "green", colour: "#1E6B3A", amount: 100, towards: "white" },
      { token: "greenBg", colour: "#1E6B3A", amount: 12, towards: "white" },
      { token: "greenLine", colour: "#1E6B3A", amount: 30, towards: "white" },
    ]);
  });

  it("lightens the colours and mixes the tints towards the surface in the dark", () => {
    expect(deriveBrandTokens(branding, true)).toEqual([
      { token: "blue", colour: "#0B5CAD", amount: 60, towards: "white" },
      { token: "blueDark", colour: "#0B5CAD", amount: 40, towards: "white" },
      { token: "blueBusy", colour: "#0B5CAD", amount: 80, towards: "white" },
      { token: "blueSoft", colour: "#0B5CAD", amount: 28, towards: "surface" },
      { token: "blueTint", colour: "#0B5CAD", amount: 18, towards: "surface" },
      { token: "blueWash", colour: "#0B5CAD", amount: 10, towards: "surface" },
      { token: "brand", colour: "#1B2A4A", amount: 100, towards: "white" },
      { token: "green", colour: "#1E6B3A", amount: 55, towards: "white" },
      { token: "greenBg", colour: "#1E6B3A", amount: 22, towards: "surface" },
      { token: "greenLine", colour: "#1E6B3A", amount: 40, towards: "surface" },
    ]);
  });

  it.each([false, true])(
    "covers every brand token name once (dark=%s)",
    (dark) => {
      const names = deriveBrandTokens(branding, dark).map((spec) => spec.token);
      expect([...names].sort()).toEqual([...BRAND_TOKEN_NAMES].sort());
    },
  );

  it("skips the tokens of a colour that is not a six digit hex", () => {
    const names = deriveBrandTokens(
      { ...branding, primary: "blue" },
      false,
    ).map((spec) => spec.token);
    expect(names).toEqual(["brand", "green", "greenBg", "greenLine"]);
    expect(
      deriveBrandTokens(
        { primary: "", secondary: "#fff", accent: "#12345" },
        true,
      ),
    ).toEqual([]);
  });
});

it("accepts a cached appearance without the fields older versions never stored", () => {
  const cached: Appearance = {
    organizationName: "Mombasa Coach",
    settingsVersion: 3,
    branding: { displayName: "XCODE", logoAlt: "", ...branding, logo: null },
    formats: {
      locale: "en-GB",
      timeZone: "Africa/Nairobi",
      datePattern: "medium",
      hour12: false,
      currency: "KES",
      useGrouping: true,
      numberDecimals: 2,
      firstDayOfWeek: 1,
      weekNumbering: "iso8601",
      direction: "ltr",
    },
    themeMode: "system",
    reducedMotion: false,
    fontScale: 1,
  };
  expect(cached.lockoutThreshold).toBeUndefined();
});

describe("sundayWeekNotice", () => {
  const since = "2026-11-25";
  const on = (businessDate: string | undefined) => ({
    sundayWeekSince: since,
    businessDate,
  });

  it("runs for seven days from the change date, by the business date", () => {
    expect(sundayWeekNotice(on("2026-11-24"), null)).toBeNull();
    expect(sundayWeekNotice(on("2026-11-25"), null)).toBe(since);
    expect(sundayWeekNotice(on("2026-12-01"), null)).toBe(since);
    expect(sundayWeekNotice(on("2026-12-02"), null)).toBeNull();
  });

  it("stays away once this device dismissed it for that change date", () => {
    expect(sundayWeekNotice(on("2026-11-26"), since)).toBeNull();
    expect(sundayWeekNotice(on("2026-11-26"), "2026-01-04")).toBe(since);
  });

  it("is never shown without a change date, a business date or an appearance", () => {
    expect(sundayWeekNotice(null, null)).toBeNull();
    expect(sundayWeekNotice(on(undefined), null)).toBeNull();
    expect(
      sundayWeekNotice({ sundayWeekSince: null, businessDate: since }, null),
    ).toBeNull();
    expect(
      sundayWeekNotice({ businessDate: since } as Appearance, null),
    ).toBeNull();
  });

  it("names the date before which weeks ran Monday to Sunday", () => {
    expect(sundayWeekNoticeDetail("25 Nov 2026")).toBe(
      "Weekly figures from before 25 Nov 2026 were counted Monday to Sunday.",
    );
  });
});

describe("targetsOn", () => {
  it("is off only when the server says Targets is off", () => {
    expect(targetsOn({ targets: false })).toBe(false);
    expect(targetsOn({ targets: true })).toBe(true);
    expect(targetsOn({})).toBe(true);
    expect(targetsOn(null)).toBe(true);
  });
});
