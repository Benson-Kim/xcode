import next from "eslint-config-next/core-web-vitals";
import ts from "typescript-eslint";
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
    // eslint-plugin-react's "detect" calls context.getFilename(), which ESLint 10 removed; keep in step with apps/web.
    files: ["apps/web/**/*.{ts,tsx,js,mjs}"],
    settings: { react: { version: "19.3" }, next: { rootDir: "apps/web" } },
  },
];
