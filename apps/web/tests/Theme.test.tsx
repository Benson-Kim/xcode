import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, expect, it, vi } from "vitest";

import {
  BRAND_TOKEN_NAMES,
  deriveBrandTokens,
  resolveTheme,
  type ThemeMode,
} from "@xcode/shared/appearance";

import { applyAppearance, type Appearance } from "../lib/appearance";

const appearance = (themeMode: ThemeMode): Appearance => ({
  organizationName: "Demo Fleet",
  settingsVersion: 3,
  branding: {
    displayName: "North Star",
    logoAlt: "North Star",
    primary: "#0B5CAD",
    secondary: "#1B2A4A",
    accent: "#1E6B3A",
    logo: null,
  },
  formats: {
    locale: "en-GB",
    timeZone: "UTC",
    datePattern: "medium",
    hour12: false,
    firstDayOfWeek: 1,
    weekNumbering: "iso8601",
    currency: "KES",
    useGrouping: true,
    numberDecimals: 2,
    direction: "ltr",
  },
  themeMode,
  reducedMotion: false,
  fontScale: 1,
});

// The device's own setting, which the browser reports through a media query.
const deviceSays = (dark: boolean) =>
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: dark && query.includes("dark"),
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));

const token = (name: string) =>
  document.documentElement.style.getPropertyValue(name);

afterEach(() => {
  vi.unstubAllGlobals();
  delete document.documentElement.dataset.theme;
  window.localStorage.clear();
});

it("paints the theme the person chose and remembers it for the next first paint", () => {
  deviceSays(false);
  applyAppearance(appearance("dark"));
  expect(document.documentElement.dataset.theme).toBe("dark");
  expect(window.localStorage.getItem("xcode.theme")).toBe("dark");

  applyAppearance(appearance("light"));
  expect(document.documentElement.dataset.theme).toBe("light");
  expect(window.localStorage.getItem("xcode.theme")).toBe("light");
});

it("follows the device only when the preference says to", () => {
  expect(resolveTheme("system", true)).toBe("dark");
  expect(resolveTheme("system", false)).toBe("light");
  // An organization that locks the theme is sent as "light", so the device is not consulted at all.
  expect(resolveTheme("light", true)).toBe("light");
  expect(resolveTheme("dark", false)).toBe("dark");
  // An appearance from an older API, or a value we do not know, follows the device.
  expect(resolveTheme(undefined, true)).toBe("dark");
  expect(resolveTheme("midnight", false)).toBe("light");

  deviceSays(true);
  applyAppearance(appearance("system"));
  expect(document.documentElement.dataset.theme).toBe("dark");
});

it("mixes the organization's colours for the surface they will sit on", () => {
  deviceSays(false);
  applyAppearance(appearance("light"));
  // In the light theme the primary is used as it was given, and its pressed shade is darker.
  expect(token("--color-blue")).toBe("#0B5CAD");
  expect(token("--color-blue-dark")).toBe(
    "color-mix(in srgb, #0B5CAD 80%, black)",
  );
  expect(token("--color-blue-tint")).toBe(
    "color-mix(in srgb, #0B5CAD 7%, white)",
  );

  applyAppearance(appearance("dark"));
  // In the dark one it is lightened, because the ink on a filled button is dark there, and the pressed shade
  // lightens further. A tint is mixed towards the surface it sits on rather than towards white.
  expect(token("--color-blue")).toBe("color-mix(in srgb, #0B5CAD 60%, white)");
  expect(token("--color-blue-dark")).toBe(
    "color-mix(in srgb, #0B5CAD 40%, white)",
  );
  expect(token("--color-blue-tint")).toBe(
    "color-mix(in srgb, #0B5CAD 18%, var(--color-paper))",
  );
  // The secondary colour is the brand mark's own, and that fill stays dark in both themes.
  expect(token("--color-brand")).toBe("#1B2A4A");
});

const kebab = (name: string) =>
  name.replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`);

it.each([
  ["light", 10, 7, 4],
  ["dark", 28, 18, 10],
] as const)(
  "paints every brand token the shared derivation names in the %s theme",
  (mode, soft, tint, wash) => {
    deviceSays(false);
    const surface = mode === "dark" ? "var(--color-paper)" : "white";
    applyAppearance(appearance(mode));
    const painted = Object.fromEntries(
      BRAND_TOKEN_NAMES.map((name) => [name, token(`--color-${kebab(name)}`)]),
    );
    expect(Object.values(painted).every(Boolean)).toBe(true);
    expect(painted.blueSoft).toBe(
      `color-mix(in srgb, #0B5CAD ${soft}%, ${surface})`,
    );
    expect(painted.blueTint).toBe(
      `color-mix(in srgb, #0B5CAD ${tint}%, ${surface})`,
    );
    expect(painted.blueWash).toBe(
      `color-mix(in srgb, #0B5CAD ${wash}%, ${surface})`,
    );
    expect(painted.greenLine).toBe(
      `color-mix(in srgb, #1E6B3A ${mode === "dark" ? 40 : 30}%, ${surface})`,
    );
    const derived = deriveBrandTokens(
      { primary: "#0B5CAD", secondary: "#1B2A4A", accent: "#1E6B3A" },
      mode === "dark",
    );
    expect(derived.map((spec) => spec.token)).toEqual(BRAND_TOKEN_NAMES);
  },
);

it("removes the tokens of a brand colour that is not a six digit hex rather than painting it", () => {
  deviceSays(false);
  applyAppearance(appearance("light"));
  expect(token("--color-blue-soft")).not.toBe("");
  const broken = appearance("light");
  applyAppearance({
    ...broken,
    branding: { ...broken.branding, primary: "teal" },
  });
  for (const name of [
    "blue",
    "blue-dark",
    "blue-busy",
    "blue-soft",
    "blue-tint",
    "blue-wash",
  ]) {
    expect(token(`--color-${name}`)).toBe("");
  }
  expect(token("--color-green-line")).not.toBe("");
});

const css = readFileSync(join(__dirname, "../app/tokens.css"), "utf8");
const darkSurface = css
  .slice(css.indexOf(':root[data-theme="dark"]'))
  .match(/--color-paper:\s*(#[0-9a-f]{6})/)![1];

// Evaluates what the browser would for color-mix(in srgb, colour amount%, towards).
const evaluate = (value: string) => {
  const found = value.match(
    /^color-mix\(in srgb, (#[0-9A-Fa-f]{6}) (\d+)%, (white|black|var\(--color-paper\))\)$/,
  );
  if (!found) return value.toUpperCase();
  const [, colour, amount, towards] = found;
  const target = {
    white: "#FFFFFF",
    black: "#000000",
    "var(--color-paper)": darkSurface,
  }[towards]!;
  const channels = (hex: string) =>
    [1, 3, 5].map((start) => parseInt(hex.slice(start, start + 2), 16));
  const mixed = channels(colour).map((channel, index) =>
    Math.round(
      (channel * Number(amount) +
        channels(target)[index] * (100 - Number(amount))) /
        100,
    ),
  );
  return `#${mixed.map((channel) => channel.toString(16).padStart(2, "0")).join("")}`.toUpperCase();
};

// The mobile app asserts these same literals from its own palette mixing (tests/themeParity.test.ts).
it.each([
  [
    "light",
    {
      blue: "#0B5CAD",
      blueDark: "#094A8A",
      blueBusy: "#3C7DBD",
      blueSoft: "#E7EFF7",
      blueTint: "#EEF4F9",
      blueWash: "#F5F8FC",
      green: "#1E6B3A",
      greenBg: "#E4EDE7",
      greenLine: "#BCD3C4",
    },
  ],
  [
    "dark",
    {
      blue: "#6D9DCE",
      blueDark: "#9DBEDE",
      blueBusy: "#3C7DBD",
      blueSoft: "#122E4D",
      blueTint: "#13283F",
      blueWash: "#142234",
      green: "#83AE93",
      greenBg: "#172D2B",
      greenLine: "#193C2F",
    },
  ],
] as const)(
  "computes the same %s colours from the brand as the mobile app",
  (mode, expected) => {
    deviceSays(false);
    applyAppearance(appearance(mode));
    const computed = Object.fromEntries(
      Object.keys(expected).map((name) => [
        name,
        evaluate(token(`--color-${kebab(name)}`)),
      ]),
    );
    expect(computed).toEqual(expected);
    expect(token("--color-brand")).toBe("#1B2A4A");
  },
);

it("keeps the theme when signed out, because it is the person's own display choice", () => {
  deviceSays(false);
  applyAppearance(appearance("dark"));
  applyAppearance(null);
  expect(document.documentElement.dataset.theme).toBe("dark");
  // The organization's colours do go, so nothing of it is left on the sign-in screen.
  expect(token("--color-blue")).toBe("");
  expect(token("--color-brand")).toBe("");
});
