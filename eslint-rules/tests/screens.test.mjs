import assert from "node:assert/strict";
import path from "node:path";
import { before, describe, it } from "node:test";
import { fileURLToPath } from "node:url";

import { ESLint } from "eslint";

const root = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
  "..",
);

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

async function lint(file, code, ruleIds) {
  const [result] = await eslint.lintText(code, {
    filePath: path.join(root, file),
  });
  assert.ok(
    !result.messages.some((m) => m.fatal),
    JSON.stringify(result.messages),
  );
  assert.ok(
    !result.messages.some((m) => /File ignored/.test(m.message)),
    `${file} was not linted`,
  );
  return result.messages.filter((m) => ruleIds.includes(m.ruleId));
}

const ENDPOINTS = "lib/endpoints";
const MOBILE = "must not import the mobile app";
const call = (argument) =>
  `import { apiRequest } from "../lib/api";\nexport const go = (id: string) => apiRequest(${argument});\n`;

// [file, code, the message it must raise once, or null when it must pass]
const cases = [
  [
    "apps/web/components/PeopleAccessView.tsx",
    call('"setup/people"'),
    ENDPOINTS,
  ],
  [
    "apps/web/components/PeopleAccessView.tsx",
    call("`setup/people/${id}/sign-out`"),
    ENDPOINTS,
  ],
  [
    "apps/web/components/people/PersonEditor.tsx",
    call('"setup/people", { method: "POST" }'),
    ENDPOINTS,
  ],
  [
    "apps/web/components/RecurringEditor.tsx",
    call("`setup/recurring/${id}`"),
    ENDPOINTS,
  ],
  [
    "apps/web/components/recurring/useRecurringActions.ts",
    call('"setup/recurring"'),
    ENDPOINTS,
  ],
  [
    "apps/web/components/OrganizationSettingsView.tsx",
    call('"setup/organization/logo"'),
    ENDPOINTS,
  ],
  [
    "apps/web/components/PreferencesView.tsx",
    call('"setup/preferences"'),
    ENDPOINTS,
  ],
  [
    "apps/web/components/RevenuePage.tsx",
    call("`setup/revenue/${id}`"),
    ENDPOINTS,
  ],
  [
    "apps/web/components/revenue/useCaptureFlow.ts",
    call('"setup/revenue"'),
    ENDPOINTS,
  ],
  ["apps/web/components/PeopleAccessView.tsx", call("peoplePath(id)"), null],
  [
    "apps/web/components/PeopleAccessView.tsx",
    call('path(id), { method: "PUT" }'),
    null,
  ],
  // Screens not yet moved onto lib/endpoints keep their literal paths.
  [
    "apps/web/components/setup/CompaniesPage.tsx",
    call('"setup/companies"'),
    null,
  ],
  // The guarded screens still keep the module boundaries.
  [
    "apps/web/components/people/PersonEditor.tsx",
    'export const load = () => import("../../../mobile/src/Screen");',
    MOBILE,
  ],
  [
    "apps/web/components/RevenuePage.tsx",
    'export const m = require("@xcode/mobile/src/a");',
    MOBILE,
  ],
  [
    "apps/web/components/recurring/x.ts",
    'import { a } from "../../../mobile/src/a";',
    MOBILE,
  ],
];

describe("screens that call the API through lib/endpoints", () => {
  for (const [file, code, expected] of cases) {
    it(
      `${file}: ${code.split("\n").at(-2) ?? code}`,
      { timeout: 120_000 },
      async () => {
        const messages = (
          await lint(file, code, [
            "no-restricted-syntax",
            "no-restricted-imports",
          ])
        ).map((m) => m.message);
        if (expected === null) assert.deepEqual(messages, []);
        else {
          assert.equal(messages.length, 1, JSON.stringify(messages));
          assert.match(messages[0], new RegExp(expected));
        }
      },
    );
  }
});

const component = (codeLines, { blank = 0, comments = 0 } = {}) =>
  [
    "export function Big() {",
    ...Array.from({ length: codeLines - 2 }, (_, i) => `  const v${i} = ${i};`),
    ...Array.from({ length: blank }, () => ""),
    ...Array.from({ length: comments }, (_, i) => `  // note ${i}`),
    "}",
    "",
  ].join("\n");

describe("function length", () => {
  const size = async (file, code) =>
    (await lint(file, code, ["max-lines-per-function"])).map((m) => m.severity);

  it(
    "warns on an app function over 150 code lines",
    { timeout: 120_000 },
    async () => {
      assert.deepEqual(
        await size("apps/web/components/Big.tsx", component(151)),
        [1],
      );
      assert.deepEqual(
        await size("apps/mobile/src/shell/Big.tsx", component(151)),
        [1],
      );
    },
  );

  it(
    "allows 150 code lines, not counting blank lines and comments",
    { timeout: 120_000 },
    async () => {
      assert.deepEqual(
        await size(
          "apps/web/components/Big.tsx",
          component(150, { blank: 20, comments: 20 }),
        ),
        [],
      );
    },
  );

  it(
    "leaves tests and the shared package alone",
    { timeout: 120_000 },
    async () => {
      assert.deepEqual(
        await size("apps/web/tests/Big.test.tsx", component(400)),
        [],
      );
      assert.deepEqual(
        await size("apps/mobile/tests/Big.test.tsx", component(400)),
        [],
      );
      assert.deepEqual(
        await size("packages/shared/src/big.ts", component(400)),
        [],
      );
    },
  );
});
