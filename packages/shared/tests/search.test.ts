/// <reference types="node" />
import { readFileSync } from "node:fs";
import { expect, it } from "vitest";

import {
  normalizeSearchText,
  rankOptions,
  type RankableOption,
} from "../src/search";

type Vector = {
  name: string;
  query: string;
  options: (string | RankableOption)[];
  expected: string[];
};

const vectors = JSON.parse(
  readFileSync(
    new URL("./fixtures/rank-options.json", import.meta.url),
    "utf8",
  ),
) as Vector[];

const asOption = (option: string | RankableOption): RankableOption =>
  typeof option === "string" ? { label: option } : option;

it.each(vectors)("$name", ({ query, options, expected }) => {
  expect(
    rankOptions(query, options.map(asOption)).map((option) => option.label),
  ).toEqual(expected);
});

it("returns the caller's own option objects, not copies", () => {
  const options = [{ label: "Tyres", value: "i1" }];
  expect(rankOptions("ty", options)[0]).toBe(options[0]);
  expect(rankOptions("", options)).not.toBe(options);
});

it("folds case, accents and runs of spaces", () => {
  expect(normalizeSearchText("  Çáfé   Ñandú ")).toBe("cafe nandu");
});
