"use client";

import { createContext, useContext } from "react";

import type { Formats } from "@xcode/shared/format";

export type Appearance = {
  organizationName: string;
  settingsVersion: number;
  businessDate?: string;
  branding: {
    displayName: string;
    logoAlt: string;
    primary: string;
    secondary: string;
    accent: string;
    logo: string | null;
  };
  formats: Formats & {
    firstDayOfWeek: number;
    weekNumbering: string;
    direction: string;
  };
  themeMode: string;
  reducedMotion: boolean;
  fontScale: number;
};

type AppearanceState = {
  appearance: Appearance | null;
  loading: boolean;
  refresh: () => void;
};

const AppearanceContext = createContext<AppearanceState>({
  appearance: null,
  loading: false,
  refresh: () => {},
});

export const AppearanceProvider = AppearanceContext.Provider;

// The organization's branding and formats and the person's display preferences.
// Screens that save any of them call refresh() so the change shows straight away.
export function useAppearance() {
  return useContext(AppearanceContext);
}

const mix = (colour: string, amount: number, towards: string) =>
  `color-mix(in srgb, ${colour} ${amount}%, ${towards})`;

// The person's Theme preference, already resolved by the API: "light", "dark", or "system" to follow the device.
// An organization that locks the theme is sent "light", so the device is never consulted for it.
const DEVICE_DARK = "(prefers-color-scheme: dark)";
const THEME_KEY = "xcode.theme";

const deviceIsDark = () => typeof window !== "undefined" && window.matchMedia?.(DEVICE_DARK).matches === true;

export function resolveTheme(mode: string | null | undefined, device = deviceIsDark()): "light" | "dark" {
  if (mode === "dark") return "dark";
  if (mode === "light") return "light";
  return device ? "dark" : "light";
}

// The appearance the page was last painted with, so a device that switches to dark while the app is open can be
// repainted with the same organization colours mixed for the other surface.
let painted: Appearance | null = null;
let watchingDevice = false;

function watchDevice() {
  if (watchingDevice || typeof window === "undefined" || !window.matchMedia) return;
  watchingDevice = true;
  window.matchMedia(DEVICE_DARK).addEventListener("change", () => applyAppearance(painted));
}

// Writes the theme onto the document, where the tokens in globals.css pick it up, and remembers it so the next
// first paint is already in it (app/layout.tsx reads it before React runs).
function applyTheme(mode: string | null | undefined) {
  const theme = resolveTheme(mode);
  document.documentElement.dataset.theme = theme;
  try {
    window.localStorage.setItem(THEME_KEY, theme);
  } catch {
    // A private window can refuse to store anything. The theme still applies to this page.
  }
  return theme;
}

// Paints the organization's colours into the design tokens and applies the theme, text size, motion and language.
// Called with null (signed out) it restores the design defaults, keeping the theme, which is the person's own
// display choice rather than the organization's data.
// Formats are configured separately, during render, because the screens format values in that same render.
export function applyAppearance(appearance: Appearance | null) {
  if (typeof document === "undefined") return;
  painted = appearance;
  const root = document.documentElement;
  const branding = appearance?.branding;
  const dark = applyTheme(appearance ? appearance.themeMode : root.dataset.theme) === "dark";
  // A brand colour has to be read against the surface it sits on. On a dark surface the organization's primary
  // is lightened, because the ink on a filled button goes dark there (--color-on-fill), and its tints are mixed
  // towards that surface instead of towards white. The pressed shade lightens for the same reason.
  const surface = "var(--color-paper)";
  const lighter = (colour: string, amount: number) => mix(colour, amount, "white");
  const tint = (colour: string, light: number, deep: number) =>
    dark ? mix(colour, deep, surface) : mix(colour, light, "white");
  const tokens: Record<string, string | undefined> = {
    "--color-blue": branding && (dark ? lighter(branding.primary, 60) : branding.primary),
    "--color-blue-dark": branding && (dark ? lighter(branding.primary, 40) : mix(branding.primary, 80, "black")),
    "--color-blue-busy": branding && (dark ? lighter(branding.primary, 80) : mix(branding.primary, 80, "white")),
    "--color-blue-soft": branding && tint(branding.primary, 10, 28),
    "--color-blue-tint": branding && tint(branding.primary, 7, 18),
    "--color-blue-wash": branding && tint(branding.primary, 4, 10),
    "--color-brand": branding?.secondary,
    "--color-green": branding && (dark ? lighter(branding.accent, 55) : branding.accent),
    "--color-green-bg": branding && tint(branding.accent, 12, 22),
    "--color-green-line": branding && tint(branding.accent, 30, 40),
  };
  for (const [name, value] of Object.entries(tokens)) {
    if (value) root.style.setProperty(name, value);
    else root.style.removeProperty(name);
  }
  root.style.setProperty(
    "zoom",
    appearance && appearance.fontScale !== 1
      ? String(appearance.fontScale)
      : "",
  );
  if (appearance?.reducedMotion) root.dataset.reducedMotion = "true";
  else delete root.dataset.reducedMotion;
  root.lang = appearance?.formats.locale ?? "en-GB";
  document.title = branding?.displayName || "XCODE";
  watchDevice();
}
