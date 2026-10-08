import {
  deriveBrandTokens,
  resolveTheme,
  type Appearance,
} from "@xcode/shared/appearance";
import { currentFormats } from "@xcode/shared/format";

import { apiGet } from "./lib/api";
import { savePinPolicy, validPinPolicy, type PinPolicy } from "./lib/storage";
import { vault } from "./lib/vault";
import { darkPalette, defaultTheme, mix, palette, type Theme } from "./ui";

export type { Appearance } from "@xcode/shared/appearance";

export const pinPolicyOf = (appearance: Appearance): PinPolicy | null =>
  validPinPolicy(appearance)
    ? {
        lockoutThreshold: appearance.lockoutThreshold!,
        lockoutMinutes: appearance.lockoutMinutes!,
      }
    : null;

const KEY = "xcode.appearance";

function withCurrentNames(appearance: Appearance): Appearance {
  return {
    ...appearance,
    formats: currentFormats(appearance.formats ?? {}) as Appearance["formats"],
  };
}

export async function loadSavedAppearance(): Promise<Appearance | null> {
  try {
    const saved = JSON.parse(
      (await vault.get(KEY)) || "null",
    ) as Appearance | null;
    return saved?.branding ? withCurrentNames(saved) : null;
  } catch {
    return null;
  }
}

export async function fetchAppearance(): Promise<Appearance> {
  const appearance = withCurrentNames(
    await apiGet<Appearance>("setup/appearance"),
  );
  await vault.set(KEY, JSON.stringify(appearance));
  const policy = pinPolicyOf(appearance);
  if (policy) await savePinPolicy(policy);
  return appearance;
}

export async function forgetAppearance() {
  await vault.remove(KEY);
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
  const colors = { ...base };
  const towards = { white: "#FFFFFF", black: "#000000", surface: base.field };
  for (const { token, colour, amount, towards: to } of deriveBrandTokens(
    appearance.branding,
    dark,
  ))
    colors[token] = amount >= 100 ? colour : mix(colour, amount, towards[to]);
  return {
    colors,
    dark,
    reducedMotion: appearance.reducedMotion,
    fontScale: appearance.fontScale > 0 ? appearance.fontScale : 1,
  };
}
