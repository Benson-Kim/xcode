"use client";

import { createContext, useContext } from "react";

import {
  BRAND_TOKEN_NAMES,
  deriveBrandTokens,
  resolveTheme,
  type Appearance,
  type BrandTowards,
} from "@xcode/shared/appearance";

export type { Appearance } from "@xcode/shared/appearance";

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

// The person's Theme preference, already resolved by the API: "light", "dark", or "system" to follow the device.
// An organization that locks the theme is sent "light", so the device is never consulted for it.
const DEVICE_DARK = "(prefers-color-scheme: dark)";
const THEME_KEY = "xcode.theme";

const deviceIsDark = () =>
  typeof window !== "undefined" &&
  window.matchMedia?.(DEVICE_DARK).matches === true;

const TOWARDS: Record<BrandTowards, string> = {
  white: "white",
  black: "black",
  surface: "var(--color-paper)",
};

const cssVar = (token: string) =>
  `--color-${token.replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`)}`;

// The appearance the page was last painted with, so a device that switches to dark while the app is open can be
// repainted with the same organization colours mixed for the other surface.
let painted: Appearance | null = null;
let watchingDevice = false;

function watchDevice() {
  if (watchingDevice || typeof window === "undefined" || !window.matchMedia)
    return;
  watchingDevice = true;
  window
    .matchMedia(DEVICE_DARK)
    .addEventListener("change", () => applyAppearance(painted));
}

// Writes the theme onto the document, where the tokens in globals.css pick it up, and remembers it so the next
// first paint is already in it (app/layout.tsx reads it before React runs).
function applyTheme(mode: string | null | undefined) {
  const theme = resolveTheme(mode, deviceIsDark());
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
  const dark =
    applyTheme(appearance ? appearance.themeMode : root.dataset.theme) ===
    "dark";
  // The tokens are derived in @xcode/shared/appearance, which reads each brand colour against the surface it sits on.
  const specs = branding ? deriveBrandTokens(branding, dark) : [];
  for (const token of BRAND_TOKEN_NAMES) {
    const spec = specs.find((candidate) => candidate.token === token);
    if (!spec) root.style.removeProperty(cssVar(token));
    else if (spec.amount >= 100)
      root.style.setProperty(cssVar(token), spec.colour);
    else
      root.style.setProperty(
        cssVar(token),
        `color-mix(in srgb, ${spec.colour} ${spec.amount}%, ${TOWARDS[spec.towards]})`,
      );
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
