import { describe, expect, it } from "vitest";

import { BRAND_TOKEN_NAMES } from "../src/appearance";
import {
  MOBILE_ALIASES,
  NATIVE_ONLY_TOKENS,
  NATIVE_TOKEN_NAMES,
  TOKEN_NAMES,
  WEB_ONLY_TOKENS,
  darkTokens,
  lightTokens,
  nativePalette,
  renderTokensCss,
  shadowTokens,
} from "../src/tokens";

describe.each([
  ["light", lightTokens],
  ["dark", darkTokens],
] as const)("the %s tokens", (_name, set) => {
  it("define exactly the canonical names", () => {
    expect(Object.keys(set).sort()).toEqual([...TOKEN_NAMES].sort());
  });

  it("hold valid colours", () => {
    for (const name of TOKEN_NAMES) {
      expect(set[name]).toMatch(
        /^(#[0-9A-F]{6}|rgba\(\d+, \d+, \d+, [\d.]+\))$/,
      );
    }
  });
});

it("keeps the names unique", () => {
  expect(new Set(TOKEN_NAMES).size).toBe(TOKEN_NAMES.length);
});

// The phone once called the web's soft blue its tint, and its tint its wash, in the light theme only.
// Each blue tint now means the same level in both apps and both themes, strongest first.
it.each([
  ["light", lightTokens, ["#E8EFFC", "#EEF3FD", "#F7F9FE"]],
  ["dark", darkTokens, ["#1B2942", "#16202F", "#131A26"]],
] as const)(
  "keeps the %s blue tints at one level each",
  (_name, set, levels) => {
    expect([set.blueSoft, set.blueTint, set.blueWash]).toEqual(levels);
    expect(nativePalette(set)).toMatchObject({
      blueSoft: levels[0],
      blueTint: levels[1],
      blueWash: levels[2],
    });
  },
);

it("names real tokens in the alias, native-only, web-only and brand tables", () => {
  for (const name of [
    ...Object.keys(MOBILE_ALIASES),
    ...NATIVE_ONLY_TOKENS,
    ...WEB_ONLY_TOKENS,
    ...BRAND_TOKEN_NAMES,
  ]) {
    expect(TOKEN_NAMES).toContain(name);
  }
});

it("builds the phone palette from the tokens, renaming only the aliases", () => {
  const palette = nativePalette(lightTokens);
  expect(Object.keys(palette).sort()).toEqual([...NATIVE_TOKEN_NAMES].sort());
  expect(Object.keys(palette)).toHaveLength(
    TOKEN_NAMES.length - WEB_ONLY_TOKENS.length,
  );
  expect(palette.field).toBe(lightTokens.paper);
  expect(palette.pressed).toBe(lightTokens.hover);
  expect(palette).not.toHaveProperty("paper");
  expect(palette).not.toHaveProperty("hover");
  for (const name of WEB_ONLY_TOKENS) expect(palette).not.toHaveProperty(name);
  expect(nativePalette(darkTokens).field).toBe(darkTokens.paper);
});

describe("renderTokensCss", () => {
  const css = renderTokensCss();
  const [light, dark] = css.split(':root[data-theme="dark"] {');

  it("writes every web token once in each block and no native-only token", () => {
    for (const block of [light, dark]) {
      const names = [...block.matchAll(/--color-([a-z-]+):/g)].map(
        ([, name]) => name,
      );
      expect(new Set(names).size).toBe(names.length);
      expect(names).toHaveLength(
        TOKEN_NAMES.length - NATIVE_ONLY_TOKENS.length + 1,
      );
      for (const name of ["key-line", "on-brand", "scrim"])
        expect(names).not.toContain(name);
      expect(names).toContain("on-fill");
      expect(names).toContain("card-line");
    }
  });

  it("lower-cases the hex values from the tokens", () => {
    expect(light).toContain(
      `--color-paper: ${lightTokens.paper.toLowerCase()};`,
    );
    expect(dark).toContain(`--color-paper: ${darkTokens.paper.toLowerCase()};`);
  });

  it("derives the pressed green from the accent in each theme", () => {
    expect(light).toContain(
      "--color-green-dark: color-mix(in srgb, var(--color-green) 80%, black);",
    );
    expect(dark).toContain(
      "--color-green-dark: color-mix(in srgb, var(--color-green) 80%, white);",
    );
  });

  it("writes the shadows of each theme", () => {
    expect(light).toContain(`--shadow-panel: ${shadowTokens.light.panel};`);
    expect(dark).toContain(`--shadow-seg: ${shadowTokens.dark.seg};`);
  });
});
