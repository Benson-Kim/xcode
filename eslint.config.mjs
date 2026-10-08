import next from "eslint-config-next/core-web-vitals";
import ts from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";
import importOrder from "./eslint-rules/import-order.mjs";
export default [
  {
    ignores: [
      "**/node_modules/**",
      "**/dist/**",
      "**/.next/**",
      "**/bin/**",
      "**/obj/**",
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
    // CommonJS config files, and jest.mock factories, which are hoisted above imports and must require.
    files: ["**/*.cjs", "apps/mobile/tests/**/*.{ts,tsx}"],
    rules: { "@typescript-eslint/no-require-imports": "off" },
  },
];
