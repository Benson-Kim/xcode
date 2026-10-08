import type { Formats } from "./format";
import type { TokenName } from "./tokens";

export type ThemeMode = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

export type EffectiveFormats = Formats & {
  weekNumbering: string;
  direction: string;
};

export type AppearanceBranding = {
  displayName: string;
  logoAlt: string;
  primary: string;
  secondary: string;
  accent: string;
  logo: string | null;
};

export type Appearance = {
  organizationName: string;
  settingsVersion: number;
  businessDate?: string;
  branding: AppearanceBranding;
  formats: EffectiveFormats;
  themeMode: ThemeMode;
  reducedMotion: boolean;
  fontScale: number;
  lockoutThreshold?: number;
  lockoutMinutes?: number;
};

// "system" and anything unrecognised follow the device.
export function resolveTheme(
  mode: string | null | undefined,
  deviceDark: boolean,
): ResolvedTheme {
  if (mode === "dark") return "dark";
  if (mode === "light") return "light";
  return deviceDark ? "dark" : "light";
}

export const BRAND_TOKEN_NAMES = [
  "blue",
  "blueDark",
  "blueBusy",
  "blueSoft",
  "blueTint",
  "blueWash",
  "brand",
  "green",
  "greenBg",
  "greenLine",
] as const satisfies readonly TokenName[];

export type BrandTokenName = (typeof BRAND_TOKEN_NAMES)[number];
export type BrandTowards = "white" | "black" | "surface";

// amount is the percentage of colour mixed into `towards`; 100 means the colour as given.
export type BrandTokenSpec = {
  token: BrandTokenName;
  colour: string;
  amount: number;
  towards: BrandTowards;
};

const HEX = /^#[0-9a-fA-F]{6}$/;

// A brand colour is read against the surface it sits on. On a dark surface the primary is lightened, because
// the ink on a filled button goes dark there, and its tints are mixed towards that surface instead of white.
export function deriveBrandTokens(
  branding: Pick<AppearanceBranding, "primary" | "secondary" | "accent">,
  dark: boolean,
): BrandTokenSpec[] {
  const specs: BrandTokenSpec[] = [];
  const add = (
    token: BrandTokenName,
    colour: string,
    amount: number,
    towards: BrandTowards,
  ) => specs.push({ token, colour, amount, towards });
  const tint = (
    token: BrandTokenName,
    colour: string,
    light: number,
    deep: number,
  ) =>
    dark
      ? add(token, colour, deep, "surface")
      : add(token, colour, light, "white");

  const { primary, secondary, accent } = branding;
  if (HEX.test(primary)) {
    if (dark) {
      add("blue", primary, 60, "white");
      add("blueDark", primary, 40, "white");
      add("blueBusy", primary, 80, "white");
    } else {
      add("blue", primary, 100, "white");
      add("blueDark", primary, 80, "black");
      add("blueBusy", primary, 80, "white");
    }
    tint("blueSoft", primary, 10, 28);
    tint("blueTint", primary, 7, 18);
    tint("blueWash", primary, 4, 10);
  }
  if (HEX.test(secondary)) add("brand", secondary, 100, "white");
  if (HEX.test(accent)) {
    if (dark) add("green", accent, 55, "white");
    else add("green", accent, 100, "white");
    tint("greenBg", accent, 12, 22);
    tint("greenLine", accent, 30, 40);
  }
  return specs;
}
