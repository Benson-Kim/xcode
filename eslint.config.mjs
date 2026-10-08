import next from "eslint-config-next/core-web-vitals";
import ts from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";
import importOrder from "./eslint-rules/import-order.mjs";

// Module boundaries: the apps never import each other or shared's source files, and shared stays framework-free.
const sharedSource = {
  regex: "^@xcode/shared/src(/|$)|(^|/)packages/shared(/|$)",
  message:
    "Import a public entry such as @xcode/shared/format; shared's source files are private.",
};
const fromMobile = {
  regex: "^@xcode/mobile(/|$)|(^|/)apps/mobile(/|$)|^(\\.\\./)+mobile(/|$)",
  message: "The web app must not import the mobile app.",
};
const fromWeb = {
  regex: "^@xcode/web(/|$)|(^|/)apps/web(/|$)|^(\\.\\./)+web(/|$)",
  message: "The mobile app must not import the web app.",
};
const framework = {
  regex:
    "^((react|react-native|next|expo)(-[^/]+)?|@(react-native|expo|next)/[^/]+)(/|$)",
  message:
    "packages/shared must stay framework-free: no React, React Native, Expo or Next.",
};
const fromApps = {
  regex: "^@xcode/(web|mobile)(/|$)|(^|/)apps(/|$)",
  message: "packages/shared must not depend on the apps.",
};
// no-restricted-imports does not see require(), import() or jest/vi.mock(), so the same paths are refused there too.
// A later block that sets no-restricted-syntax for these files replaces this one, so it passes its own selectors in.
const boundaries = (rules, syntax = []) => ({
  "no-restricted-imports": ["error", { patterns: rules }],
  "no-restricted-syntax": [
    "error",
    ...rules.flatMap(({ regex, message }) => {
      const value = `[value=/${regex.replaceAll("/", "\\x2F")}/]`;
      return [
        `CallExpression[callee.name='require'] > Literal${value}`,
        `ImportExpression > Literal${value}`,
        `CallExpression[callee.object.name=/^(jest|vi)$/] > Literal${value}`,
      ].map((selector) => ({ selector, message }));
    }),
    ...syntax,
  ],
});

// Screens whose requests go through lib/endpoints; the other setup pages still pass paths.
const endpointScreens = [
  "apps/web/components/{OrganizationSettingsView,PreferencesView,PeopleAccessView,RecurringEditor,RevenuePage}.tsx",
  "apps/web/components/{people,recurring,revenue}/**/*.{ts,tsx}",
];
const endpointPaths = {
  selector:
    "CallExpression[callee.name='apiRequest'] > :first-child:matches(Literal, TemplateLiteral)",
  message:
    "Call a function from lib/endpoints instead of passing apiRequest a path.",
};

export default [
  {
    ignores: [
      "**/node_modules/**",
      "**/dist/**",
      "**/.next/**",
      "**/bin/**",
      "**/obj/**",
      "**/coverage/**",
      "design/**",
      "apps/web/next-env.d.ts",
    ],
  },
  ...ts.configs.recommended,
  ...next.map((config) => ({
    ...config,
    files: ["apps/web/**/*.{ts,tsx,js,mjs}"],
  })),
  {
    files: ["apps/web/**/*.{ts,tsx}", "apps/mobile/**/*.{ts,tsx}"],
    plugins: { local: { rules: { "import-order": importOrder } } },
    rules: { "local/import-order": "error" },
  },
  {
    // eslint-plugin-react's "detect" calls context.getFilename(), which ESLint 10 removed; keep in step with apps/web.
    files: ["apps/web/**/*.{ts,tsx,js,mjs}"],
    settings: { react: { version: "19.3" }, next: { rootDir: "apps/web" } },
  },
  {
    // The Expo app: the same hooks rules as the web app, without the Next.js ones.
    files: ["apps/mobile/**/*.{ts,tsx}"],
    plugins: { "react-hooks": reactHooks },
    rules: {
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "error",
    },
  },
  {
    files: ["packages/shared/**/*.{ts,tsx,js,mjs,cjs}"],
    rules: boundaries([framework, fromApps]),
  },
  {
    files: ["apps/web/**/*.{ts,tsx,js,mjs,cjs}"],
    rules: boundaries([sharedSource, fromMobile]),
  },
  {
    files: endpointScreens,
    rules: boundaries([sharedSource, fromMobile], [endpointPaths]),
  },
  {
    files: ["apps/mobile/**/*.{ts,tsx,js,mjs,cjs}"],
    rules: boundaries([sharedSource, fromWeb]),
  },
  {
    // Long components are split into hooks and parts; the README lists the functions still over the limit.
    files: ["apps/**/*.{ts,tsx}"],
    ignores: ["apps/**/tests/**"],
    rules: {
      "max-lines-per-function": [
        "warn",
        { max: 150, skipBlankLines: true, skipComments: true },
      ],
    },
  },
  {
    // CommonJS config files, jest.mock factories, which are hoisted above imports and must require, and the cPanel
    // startup file, which Passenger loads with require.
    files: [
      "**/*.cjs",
      "apps/mobile/tests/**/*.{ts,tsx}",
      "deploy/cpanel/start.js",
    ],
    rules: { "@typescript-eslint/no-require-imports": "off" },
  },
];
