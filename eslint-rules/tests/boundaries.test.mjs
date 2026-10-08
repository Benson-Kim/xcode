import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { before, describe, it } from "node:test";
import { fileURLToPath } from "node:url";

import { ESLint } from "eslint";

const root = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
  "..",
);
const sharedEntries = Object.keys(
  JSON.parse(
    readFileSync(path.join(root, "packages/shared/package.json"), "utf8"),
  ).exports,
).map((entry) => `@xcode/shared/${entry.replace(/^\.\//, "")}`);

const FRAMEWORK = "framework-free";
const APPS = "must not depend on the apps";
const SHARED_SOURCE = "source files are private";
const MOBILE = "must not import the mobile app";
const WEB = "must not import the web app";

// [file, code, the boundary message it must raise once, or null when it must pass]
const cases = [
  ["packages/shared/src/x.ts", 'import { useState } from "react";', FRAMEWORK],
  [
    "packages/shared/src/x.ts",
    'import type { ReactNode } from "react";',
    FRAMEWORK,
  ],
  [
    "packages/shared/src/x.ts",
    'import { createRoot } from "react-dom/client";',
    FRAMEWORK,
  ],
  [
    "packages/shared/src/x.ts",
    'import x from "react-native/Libraries/Foo";',
    FRAMEWORK,
  ],
  [
    "packages/shared/src/x.ts",
    'import { NextResponse } from "next/server";',
    FRAMEWORK,
  ],
  [
    "packages/shared/src/x.ts",
    'import * as Crypto from "expo-crypto";',
    FRAMEWORK,
  ],
  [
    "packages/shared/src/x.ts",
    'import x from "@react-native/assets";',
    FRAMEWORK,
  ],
  [
    "packages/shared/src/x.ts",
    'export const load = () => import("next/server");',
    FRAMEWORK,
  ],
  [
    "packages/shared/src/x.ts",
    'export const React = require("react");',
    FRAMEWORK,
  ],
  [
    "packages/shared/src/x.ts",
    'import { api } from "../../../apps/web/lib/api";',
    APPS,
  ],
  ["packages/shared/src/x.ts", 'import x from "@xcode/mobile/src/a";', APPS],
  [
    "packages/shared/tests/x.test.ts",
    'import { useState } from "react";',
    FRAMEWORK,
  ],
  [
    "packages/shared/src/x.ts",
    'import { createFormatter } from "./format";',
    null,
  ],
  [
    "packages/shared/tests/x.test.ts",
    'import { describe } from "vitest";\nimport { cache } from "../src/intlCache";',
    null,
  ],

  [
    "apps/web/lib/x.ts",
    'import { api } from "../../mobile/src/lib/api";',
    MOBILE,
  ],
  ["apps/web/lib/x.ts", 'import x from "@xcode/mobile/src/a";', MOBILE],
  ["apps/web/lib/x.ts", 'import x from "../../../apps/mobile/src/a";', MOBILE],
  [
    "apps/web/lib/x.ts",
    'export const load = () => import("../../mobile/src/Screen");',
    MOBILE,
  ],
  [
    "apps/web/lib/x.ts",
    'import { f } from "@xcode/shared/src/format";',
    SHARED_SOURCE,
  ],
  [
    "apps/web/lib/x.ts",
    'import { f } from "../../../packages/shared/src/format";',
    SHARED_SOURCE,
  ],
  ["apps/web/tests/x.test.tsx", 'import x from "@xcode/mobile";', MOBILE],
  [
    "apps/web/tests/x.test.tsx",
    'vi.mock("@xcode/shared/src/format");',
    SHARED_SOURCE,
  ],
  [
    "apps/web/lib/x.ts",
    'import { NextResponse } from "next/server";\nimport { useState } from "react";',
    null,
  ],
  ["apps/web/lib/x.ts", 'import { y } from "./y";', null],

  ["apps/mobile/src/x.ts", 'import { a } from "../../web/lib/a";', WEB],
  ["apps/mobile/src/x.ts", 'import { a } from "@xcode/web/lib/a";', WEB],
  ["apps/mobile/src/x.ts", 'import { a } from "../../../apps/web/lib/a";', WEB],
  [
    "apps/mobile/src/x.ts",
    'import { d } from "@xcode/shared/src/dates";',
    SHARED_SOURCE,
  ],
  [
    "apps/mobile/src/x.ts",
    'export * from "../../../packages/shared/src/dates";',
    SHARED_SOURCE,
  ],
  [
    "apps/mobile/src/x.ts",
    'export const d = require("../../../packages/shared/src/dates");',
    SHARED_SOURCE,
  ],
  ["apps/mobile/tests/x.test.tsx", 'jest.mock("@xcode/web/lib/api");', WEB],
  [
    "apps/mobile/tests/x.test.tsx",
    'jest.mock("../src/lib/api", () => ({}));',
    null,
  ],
  [
    "apps/mobile/metro.config.cjs",
    'module.exports = require("../web/next.config");',
    WEB,
  ],
  [
    "apps/mobile/metro.config.cjs",
    'module.exports = require("expo/metro-config");',
    null,
  ],
  [
    "apps/mobile/src/x.ts",
    'import { View } from "react-native";\nimport * as Store from "expo-secure-store";',
    null,
  ],

  // Every public entry of the shared package stays importable from both apps.
  ...sharedEntries.flatMap((entry) => [
    ["apps/web/lib/x.ts", `import * as m from "${entry}";`, null],
    ["apps/mobile/src/x.ts", `import * as m from "${entry}";`, null],
  ]),
];

let eslint;
before(
  () => {
    eslint = new ESLint({
      cwd: root,
      overrideConfigFile: path.join(root, "eslint.config.mjs"),
    });
  },
  { timeout: 120_000 },
);

async function boundaryMessages(file, code) {
  const [result] = await eslint.lintText(code, {
    filePath: path.join(root, file),
  });
  assert.ok(
    !result.messages.some((m) => m.fatal),
    JSON.stringify(result.messages),
  );
  // A path that no config block lints would pass every case vacuously.
  assert.ok(
    !result.messages.some((m) => /File ignored/.test(m.message)),
    `${file} was not linted`,
  );
  return result.messages
    .filter(
      (m) =>
        m.ruleId === "no-restricted-imports" ||
        m.ruleId === "no-restricted-syntax",
    )
    .map((m) => m.message);
}

describe("module boundaries", () => {
  it("covers at least one public shared entry", () =>
    assert.ok(sharedEntries.length > 0));

  for (const [file, code, expected] of cases) {
    it(`${file}: ${code}`, { timeout: 120_000 }, async () => {
      const messages = await boundaryMessages(file, code);
      if (expected === null) assert.deepEqual(messages, []);
      else {
        assert.equal(messages.length, 1, JSON.stringify(messages));
        assert.match(messages[0], new RegExp(expected));
      }
    });
  }
});
