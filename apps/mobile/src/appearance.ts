import { apiGet } from "./lib/api";
import type { Formats } from "./lib/format";
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
  // The organization's wrong-PIN policy, which the phone enforces when it unlocks offline.
  lockoutThreshold?: number;
  lockoutMinutes?: number;
};

// The policy an appearance carries, or null when it has none (an older API) or it is out of bounds.
export const pinPolicyOf = (appearance: Appearance): PinPolicy | null =>
  validPinPolicy(appearance) ? { lockoutThreshold: appearance.lockoutThreshold!, lockoutMinutes: appearance.lockoutMinutes! } : null;

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
  const policy = pinPolicyOf(appearance);
  if (policy) await savePinPolicy(policy);
  return appearance;
}

export async function forgetAppearance() {
  await vault.remove(KEY);
}

const hex = (value: string | undefined): value is string =>
  /^#[0-9a-fA-F]{6}$/.test(value ?? "");

// The person's Theme preference, already resolved by the API: "light", "dark", or "system" to follow the phone.
// An organization that locks the theme is sent "light", so the phone's own setting is never consulted for it.
export function resolveTheme(mode: string | null | undefined, deviceDark: boolean): "light" | "dark" {
  if (mode === "dark") return "dark";
  if (mode === "light") return "light";
  return deviceDark ? "dark" : "light";
}

// The organization's colours on the theme the person asked for. A brand colour has to be read against the surface
// it sits on: on a dark one the primary is lightened, because the ink on a filled button goes dark there
// (colors.onFill), and its tints are mixed towards that surface instead of towards white.
export function themeFor(appearance: Appearance | null, deviceDark = false): Theme {
  const dark = resolveTheme(appearance?.themeMode, deviceDark) === "dark";
  const base = dark ? darkPalette : palette;
  if (!appearance) return { ...defaultTheme, colors: base, dark };
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
