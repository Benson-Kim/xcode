import type { Formats } from "@xcode/shared/format";

import { apiGet } from "./lib/api";
import { savePinPolicy, validPinPolicy, type PinPolicy } from "./lib/storage";
import { vault } from "./lib/vault";
import { darkPalette, defaultTheme, mix, palette, type Theme } from "./ui";

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
  lockoutThreshold?: number;
  lockoutMinutes?: number;
};

export const pinPolicyOf = (appearance: Appearance): PinPolicy | null =>
  validPinPolicy(appearance)
    ? {
        lockoutThreshold: appearance.lockoutThreshold!,
        lockoutMinutes: appearance.lockoutMinutes!,
      }
    : null;

const KEY = "xcode.appearance";

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
  const policy = pinPolicyOf(appearance);
  if (policy) await savePinPolicy(policy);
  return appearance;
}

export async function forgetAppearance() {
  await vault.remove(KEY);
}

const hex = (value: string | undefined): value is string =>
  /^#[0-9a-fA-F]{6}$/.test(value ?? "");

export function resolveTheme(
  mode: string | null | undefined,
  deviceDark: boolean,
): "light" | "dark" {
  if (mode === "dark") return "dark";
  if (mode === "light") return "light";
  return deviceDark ? "dark" : "light";
}

export function themeFor(
  appearance: Appearance | null,
  deviceDark = false,
): Theme {
  const dark = resolveTheme(appearance?.themeMode, deviceDark) === "dark";
  const base = dark ? darkPalette : palette;
  if (!appearance) {
    return {
      ...defaultTheme,
      colors: base,
      dark,
    };
  }
  const { primary, secondary, accent } = appearance.branding;
  const colors = { ...base };
  const tint = (colour: string, light: number, deep: number) =>
    dark ? mix(colour, deep, base.field) : mix(colour, light, "#FFFFFF");
  if (hex(primary))
    Object.assign(colors, {
      blue: dark ? mix(primary, 60, "#FFFFFF") : primary,
      blueDark: mix(primary, dark ? 40 : 80, dark ? "#FFFFFF" : "#000000"),
      blueBusy: mix(primary, 80, "#FFFFFF"),
      blueTint: tint(primary, 10, 18),
      blueWash: tint(primary, 4, 10),
    });
  if (hex(secondary)) colors.brand = secondary;
  if (hex(accent))
    Object.assign(colors, {
      green: dark ? mix(accent, 55, "#FFFFFF") : accent,
      greenBg: tint(accent, 12, 22),
    });
  return {
    colors,
    dark,
    reducedMotion: appearance.reducedMotion,
    fontScale: appearance.fontScale > 0 ? appearance.fontScale : 1,
  };
}
