/// <reference types="node" />
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { BRAND_TOKEN_NAMES, type Appearance } from "@xcode/shared/appearance";
import {
  MOBILE_ALIASES,
  NATIVE_ONLY_TOKENS,
  TOKEN_NAMES,
  WEB_ONLY_TOKENS,
  darkTokens,
  lightTokens,
  nativePalette,
} from "@xcode/shared/tokens";

import { themeFor } from "../src/appearance";
import { darkPalette, palette } from "../src/ui";

const css = readFileSync(join(__dirname, "../../web/app/tokens.css"), "utf8");

const blockAfter = (opening: string) => {
  const start = css.indexOf(opening);
  expect(start).toBeGreaterThan(-1);
  return css.slice(start, css.indexOf("\n}", start));
};

const kebab = (name: string) =>
  name.replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`);

const tokens = (block: string) =>
  Object.fromEntries(
    [...block.matchAll(/--color-([a-z-]+):\s*(#[0-9a-f]{6})\s*;/g)].map(
      ([, name, value]) => [name, value],
    ),
  );

const webLight = tokens(blockAfter("@theme {"));
const webDark = tokens(blockAfter(':root[data-theme="dark"] {'));

const brandedWith = (
  primary: string,
  secondary: string,
  accent: string,
): Appearance => ({
  organizationName: "Parity",
  settingsVersion: 1,
  branding: {
    displayName: "Parity",
    logoAlt: "",
    primary,
    secondary,
    accent,
    logo: null,
  },
  formats: {
    locale: "en-GB",
    timeZone: "Africa/Nairobi",
    datePattern: "medium",
    hour12: false,
    currency: "KES",
    useGrouping: true,
    numberDecimals: 2,
    firstDayOfWeek: 1,
    weekNumbering: "iso8601",
    direction: "ltr",
  },
  themeMode: "system",
  reducedMotion: false,
  fontScale: 1,
});

// The web test (Theme.test.tsx) asserts these same literals from the CSS the browser would compute.
const LIGHT = {
  blue: "#0B5CAD",
  blueDark: "#094A8A",
  blueBusy: "#3C7DBD",
  blueSoft: "#E7EFF7",
  blueTint: "#EEF4F9",
  blueWash: "#F5F8FC",
  green: "#1E6B3A",
  greenBg: "#E4EDE7",
  greenLine: "#BCD3C4",
};

const DARK = {
  blue: "#6D9DCE",
  blueDark: "#9DBEDE",
  blueBusy: "#3C7DBD",
  blueSoft: "#122E4D",
  blueTint: "#13283F",
  blueWash: "#142234",
  green: "#83AE93",
  greenBg: "#172D2B",
  greenLine: "#193C2F",
};

describe.each([
  ["light", palette, webLight, lightTokens],
  ["dark", darkPalette, webDark, darkTokens],
] as const)("the %s palette", (_name, mobile, web, canonical) => {
  it("is the shared tokens, renamed only through the aliases", () => {
    expect(mobile).toEqual(nativePalette(canonical));
  });

  it("holds the colour tokens.css holds for every token the two share", () => {
    const shared = TOKEN_NAMES.filter(
      (name) =>
        !(NATIVE_ONLY_TOKENS as readonly string[]).includes(name) &&
        !(WEB_ONLY_TOKENS as readonly string[]).includes(name),
    );
    const phoneKey = (name: string) =>
      (MOBILE_ALIASES as Record<string, string>)[name] ?? name;
    const actual = Object.fromEntries(
      shared.map((name) => [
        kebab(name),
        (mobile as Record<string, string>)[phoneKey(name)].toLowerCase(),
      ]),
    );
    const expected = Object.fromEntries(
      shared.map((name) => [kebab(name), web[kebab(name)]]),
    );
    expect(actual).toEqual(expected);
  });

  it("has every brand token, as the web has", () => {
    for (const token of BRAND_TOKEN_NAMES) {
      expect(Object.keys(mobile)).toContain(token);
      expect(web[kebab(token)]).toBeDefined();
    }
  });
});

it.each([
  ["light", false, LIGHT],
  ["dark", true, DARK],
] as const)(
  "mixes the same %s tokens from the same brand colours as XCODE Web",
  (_name, dark, pinned) => {
    const colors = themeFor(brandedWith("#0B5CAD", "#1B2A4A", "#1E6B3A"), dark)
      .colors as Record<string, string>;
    expect(
      Object.fromEntries(Object.keys(pinned).map((key) => [key, colors[key]])),
    ).toEqual(pinned);
    expect(colors.brand).toBe("#1B2A4A");
  },
);
