/// <reference types="node" />
import { readdirSync, readFileSync } from "node:fs";
import { expect, it } from "vitest";

const pkg = JSON.parse(
  readFileSync(new URL("../package.json", import.meta.url), "utf8"),
) as { main?: string; types?: string; exports: Record<string, string> };

const INTERNAL = ["intlCache", "query"];

const modules = readdirSync(new URL("../src/", import.meta.url))
  .filter((file) => file.endsWith(".ts"))
  .map((file) => file.slice(0, -3))
  .filter((name) => !INTERNAL.includes(name))
  .sort();

it("has no root entry: every consumer imports a named module", () => {
  expect(pkg.main).toBeUndefined();
  expect(pkg.types).toBeUndefined();
  expect(pkg.exports["."]).toBeUndefined();
});

it("exports every public source module and nothing else", () => {
  expect(Object.keys(pkg.exports).sort()).toEqual(
    modules.map((name) => `./${name}`),
  );
});

it.each(Object.keys(pkg.exports))("points %s at its source file", (key) => {
  expect(pkg.exports[key]).toBe(`./src/${key.slice(2)}.ts`);
});

it.each(Object.keys(pkg.exports))(
  "imports %s through the package name",
  async (key) => {
    const mod = await import(
      /* @vite-ignore */ `@xcode/shared/${key.slice(2)}`
    );
    expect(Object.keys(mod).length).toBeGreaterThan(0);
  },
);
