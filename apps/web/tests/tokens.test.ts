/// <reference types="node" />
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, it } from "vitest";

import { renderTokensCss } from "@xcode/shared/tokens";

it("keeps app/tokens.css identical to what the shared tokens render", async () => {
  await expect(renderTokensCss()).toMatchFileSnapshot("../app/tokens.css");
});

it("takes every colour from tokens.css and declares none of its own", () => {
  const css = readFileSync(join(__dirname, "../app/globals.css"), "utf8");
  expect(css).toContain('@import "./tokens.css";');
  expect(css.match(/--color-[a-z-]+\s*:/g)).toBeNull();
});
