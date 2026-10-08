export const TOKEN_NAMES = [
  "cream",
  "surface",
  "onFill",
  "navy",
  "brand",
  "grey",
  "blue",
  "blueDark",
  "blueBusy",
  "blueSoft",
  "blueTint",
  "blueWash",
  "line",
  "cardLine",
  "divider",
  "paper",
  "hover",
  "red",
  "redBg",
  "redLine",
  "redText",
  "redHover",
  "amber",
  "amberBg",
  "amberLine",
  "amberText",
  "amberHover",
  "green",
  "greenBg",
  "greenLine",
  "keyLine",
  "onBrand",
  "scrim",
] as const;

export type TokenName = (typeof TOKEN_NAMES)[number];
export type TokenSet = Record<TokenName, string>;

export const lightTokens: TokenSet = {
  cream: "#F6F3EC",
  surface: "#FFFFFF",
  onFill: "#FFFFFF",
  navy: "#14213D",
  brand: "#14213D",
  grey: "#4F5B6B",
  blue: "#1D5FD6",
  blueDark: "#1647A6",
  blueBusy: "#3F6FC9",
  blueSoft: "#E8EFFC",
  blueTint: "#EEF3FD",
  blueWash: "#F7F9FE",
  line: "#CFC8B8",
  cardLine: "#E4DFD3",
  divider: "#EFEBE3",
  paper: "#FBF9F4",
  hover: "#F3F0E8",
  red: "#B42318",
  redBg: "#FDECEA",
  redLine: "#F3C1BB",
  redText: "#8A1C12",
  redHover: "#FBD9D4",
  amber: "#C9861C",
  amberBg: "#FFF4DE",
  amberLine: "#E7C27A",
  amberText: "#6B4200",
  amberHover: "#FBE9C6",
  green: "#1E6B3A",
  greenBg: "#E3F1E8",
  greenLine: "#B8DDC3",
  keyLine: "#DDD6C8",
  onBrand: "#FFFFFF",
  scrim: "rgba(20, 33, 61, 0.4)",
};

export const darkTokens: TokenSet = {
  cream: "#0F1520",
  surface: "#1A222F",
  onFill: "#0F1520",
  navy: "#E9EDF3",
  brand: "#223253",
  grey: "#A3AEBF",
  blue: "#7FA9F5",
  blueDark: "#A9C6F9",
  blueBusy: "#5C7FB8",
  blueSoft: "#1B2942",
  blueTint: "#16202F",
  blueWash: "#131A26",
  line: "#394657",
  cardLine: "#2B3542",
  divider: "#242D3A",
  paper: "#151C27",
  hover: "#202936",
  red: "#F0776B",
  redBg: "#2A1512",
  redLine: "#5E2A23",
  redText: "#FFB4A9",
  redHover: "#351A15",
  amber: "#E4A33C",
  amberBg: "#2A2011",
  amberLine: "#5C4520",
  amberText: "#F6CE86",
  amberHover: "#342714",
  green: "#5FC183",
  greenBg: "#14291C",
  greenLine: "#2B4C36",
  keyLine: "#2F3A48",
  onBrand: "#FFFFFF",
  scrim: "rgba(0, 0, 0, 0.6)",
};

export const NATIVE_ONLY_TOKENS = ["keyLine", "onBrand", "scrim"] as const;
export const WEB_ONLY_TOKENS = ["redHover", "amber", "amberHover"] as const;

// Canonical name -> the key the phone has always used.
export const MOBILE_ALIASES = { paper: "field", hover: "pressed" } as const;

type Aliases = typeof MOBILE_ALIASES;
type NativeCanonical = Exclude<TokenName, (typeof WEB_ONLY_TOKENS)[number]>;
export type NativeTokenName =
  Exclude<NativeCanonical, keyof Aliases> | Aliases[keyof Aliases];
export type NativePalette = Record<NativeTokenName, string>;

export const NATIVE_TOKEN_NAMES: readonly NativeTokenName[] =
  TOKEN_NAMES.filter(
    (name) => !(WEB_ONLY_TOKENS as readonly string[]).includes(name),
  ).map(
    (name) => (MOBILE_ALIASES as Record<string, NativeTokenName>)[name] ?? name,
  ) as NativeTokenName[];

export function nativePalette(set: TokenSet): NativePalette {
  const palette: Record<string, string> = {};
  for (const name of TOKEN_NAMES) {
    if ((WEB_ONLY_TOKENS as readonly string[]).includes(name)) continue;
    palette[(MOBILE_ALIASES as Record<string, string>)[name] ?? name] =
      set[name];
  }
  return palette as NativePalette;
}

export const shadowTokens = {
  light: {
    panel: "0 8px 24px rgb(20 33 61 / 6%)",
    menu: "0 8px 24px rgb(20 33 61 / 12%)",
    drawer: "0 8px 24px rgb(20 33 61 / 18%)",
    toast: "0 8px 24px rgb(20 33 61 / 25%)",
    seg: "0 1px 3px rgb(20 33 61 / 15%)",
  },
  dark: {
    panel: "0 8px 24px rgb(0 0 0 / 45%)",
    menu: "0 8px 24px rgb(0 0 0 / 55%)",
    drawer: "0 8px 24px rgb(0 0 0 / 60%)",
    toast: "0 8px 24px rgb(0 0 0 / 65%)",
    seg: "0 1px 3px rgb(0 0 0 / 50%)",
  },
} as const;

const kebab = (name: string) =>
  name.replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`);

function declarations(
  set: TokenSet,
  shadows: Record<string, string>,
  towards: "black" | "white",
) {
  const lines: string[] = [];
  for (const name of TOKEN_NAMES) {
    if ((NATIVE_ONLY_TOKENS as readonly string[]).includes(name)) continue;
    lines.push(`  --color-${kebab(name)}: ${set[name].toLowerCase()};`);
    if (name === "green") {
      lines.push(
        `  --color-green-dark: color-mix(in srgb, var(--color-green) 80%, ${towards});`,
      );
    }
  }
  for (const [name, value] of Object.entries(shadows)) {
    lines.push(`  --shadow-${name}: ${value};`);
  }
  return lines.join("\n");
}

export function renderTokensCss(): string {
  return [
    "/* Generated from packages/shared/src/tokens.ts. Do not edit by hand: change the tokens, then run `cd apps/web && npx vitest run tests/tokens.test.ts -u`. */",
    "@theme {",
    declarations(lightTokens, shadowTokens.light, "black"),
    "}",
    "",
    ':root[data-theme="dark"] {',
    declarations(darkTokens, shadowTokens.dark, "white"),
    "}",
    "",
  ].join("\n");
}
