import { afterEach, expect, it, vi } from "vitest";

import {
  applyAppearance,
  resolveTheme,
  type Appearance,
} from "../lib/appearance";

const appearance = (themeMode: string): Appearance => ({
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
    useGroupping: true,
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

it("keeps the theme when signed out, because it is the person's own display choice", () => {
  deviceSays(false);
  applyAppearance(appearance("dark"));
  applyAppearance(null);
  expect(document.documentElement.dataset.theme).toBe("dark");
  // The organization's colours do go, so nothing of it is left on the sign-in screen.
  expect(token("--color-blue")).toBe("");
  expect(token("--color-brand")).toBe("");
});
