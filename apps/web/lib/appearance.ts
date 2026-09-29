"use client";

import { createContext, useContext } from "react";
import type { Formats } from "./format";

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

// Paints the organization's colours into the design tokens and applies text size, motion and language.
// Called with null (signed out) it restores the design defaults.
// Formats are configured separately, during render, because the screens format values in that same render.
export function applyAppearance(appearance: Appearance | null) {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  const branding = appearance?.branding;
  const tokens: Record<string, string | undefined> = {
    "--color-blue": branding?.primary,
    "--color-blue-dark": branding && mix(branding.primary, 80, "black"),
    "--color-blue-busy": branding && mix(branding.primary, 80, "white"),
    "--color-blue-soft": branding && mix(branding.primary, 10, "white"),
    "--color-blue-tint": branding && mix(branding.primary, 7, "white"),
    "--color-blue-wash": branding && mix(branding.primary, 4, "white"),
    "--color-brand": branding?.secondary,
    "--color-green": branding?.accent,
    "--color-green-bg": branding && mix(branding.accent, 12, "white"),
    "--color-green-line": branding && mix(branding.accent, 30, "white"),
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
}
