import { apiGet } from "./lib/api";
import type { Formats } from "./lib/format";
import { vault } from "./lib/vault";
import { defaultTheme, mix, type Theme } from "./ui";

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
  formats: Formats;
  themeMode: string;
  reducedMotion: boolean;
  fontScale: number;
};

const KEY = "xcode.appearance";

// The last appearance this phone saw, so the unlock screen shows the organization's brand even offline.
export async function loadSavedAppearance(): Promise<Appearance | null> {
  try {
    const saved = JSON.parse(
      (await vault.get(KEY)) || "null",
    ) as Appearance | null;
    return saved?.branding ? saved : null;
  } catch {
    return null;
  }
}

export async function fetchAppearance(): Promise<Appearance> {
  const appearance = await apiGet<Appearance>("setup/appearance");
  await vault.set(KEY, JSON.stringify(appearance));
  return appearance;
}

export async function forgetAppearance() {
  await vault.remove(KEY);
}

const hex = (value: string | undefined): value is string =>
  /^#[0-9a-fA-F]{6}$/.test(value ?? "");

// The organization's colours
export function themeFor(appearance: Appearance | null): Theme {
  if (!appearance) return defaultTheme;
  const { primary, secondary, accent } = appearance.branding;
  const colors = { ...defaultTheme.colors };
  if (hex(primary))
    Object.assign(colors, {
      blue: primary,
      blueDark: mix(primary, 80, "#000000"),
      blueBusy: mix(primary, 80, "#FFFFFF"),
      blueTint: mix(primary, 10, "#FFFFFF"),
      blueWash: mix(primary, 4, "#FFFFFF"),
    });
  if (hex(secondary)) colors.brand = secondary;
  if (hex(accent))
    Object.assign(colors, {
      green: accent,
      greenBg: mix(accent, 12, "#FFFFFF"),
    });
  return {
    colors,
    reducedMotion: appearance.reducedMotion,
    fontScale: appearance.fontScale > 0 ? appearance.fontScale : 1,
  };
}
