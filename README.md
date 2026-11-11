# Multi-platform authentication application

Python API (`apps/api-python`, FastAPI on PostgreSQL), Next.js web (`apps/web`), Expo/React Native mobile (`apps/mobile`) and a shared TypeScript package (`packages/shared`) in one npm-workspaces repository. The API has its own README, tests and CI workflow (`.github/workflows/xcode-api.yml`).

## Requirements

- Node.js at the version in `.nvmrc`.
- For the API: Python 3.13 and PostgreSQL 16 or later (see `apps/api-python/README.md`).

## Commands

Run these from the repository root after `npm ci`. Each is a step in CI, so a green local run means a green pipeline.

| Command | Runs | CI job |
|---|---|---|
| `npm run format:check` | Prettier without writing (`npm run format` writes) | js |
| `npm run lint` | ESLint, including the module-boundary rules | js |
| `npm run typecheck` | `tsc --noEmit` in shared, web and mobile | js |
| `npm test` | lint-rule fixtures, then the shared, web and mobile tests | js, mobile |

Each part also runs alone: `test:lint-rules`, `test:shared`, `test:web`, `test:mobile`, `typecheck:shared`, `typecheck:web`, `typecheck:mobile`. The API's checks run from `apps/api-python`: `ruff check .`, `ruff format --check .`, `mypy` and `pytest -n auto` (with `XCODE_TEST_DATABASE_URL`).

## Toolchain

- Node: the version in `.nvmrc`, which is also the `engines` minimum.
- TypeScript: one version, `~6.0.3`, at the root and in every workspace. `typescript-eslint` parses every workspace and supports TypeScript below 6.1, and TypeScript 7 has no compiler API for it to use, so all workspaces move together once it does.
- React: the web app runs React 19.3, and React Native 0.86 pins the phone to 19.2.3. npm hoists the web copy to the root, where `react-native` would otherwise load it, so `apps/mobile/metro.config.cjs` and `apps/mobile/jest.config.cjs` resolve `react` and `react-dom` from `apps/mobile`. Keep both until the two versions meet. Each app pins `react` and `react-dom` exactly, `packages/shared` imports no React, and `settings.react.version` in `eslint.config.mjs` follows the web app's React.
- `eslint-rules/tests/toolchain.test.mjs` fails when any of these drift.
- Prettier is pinned exactly, because a new version can reformat code. `.gitattributes` keeps line endings LF on every platform.
- Shared coverage: thresholds in `packages/shared/vitest.config.ts` apply whenever `CI` is set, which CI always does. Locally, run `npm run test:shared -- --coverage`.
- Colours: `packages/shared/src/tokens.ts` is the only source. `apps/web/app/tokens.css` is generated from it, and the phone's palette is built from the same tables. After changing a token, regenerate the CSS with `cd apps/web && npx vitest run tests/tokens.test.ts -u`; tests in both apps fail on drift.
- Requests: the revenue, people, recurring, organization settings and preferences screens call the API through `apps/web/lib/endpoints/*`, and ESLint refuses a literal path passed to `apiRequest` there. The other setup pages still pass paths; move them over when you next change them, then add them to `endpointScreens` in `eslint.config.mjs`.
- Function length: ESLint warns on any app function over 150 lines, not counting blank lines and comments (tests excluded). These still exceed it. Split them when you next change them, and do not raise the limit:
  - web: `SettingsForm` 548, `ExpenseCategoriesPage` 518, `VehicleEditor` 462, `AuthPanel` 442, `VehicleInvestmentTab` 323, petty-cash `EntryForm` 274, `PettyCashPage` 276, `CompaniesPage` 280, `PreferencesForm` 180, `VehiclesPage` 163, the auth route's `POST` 159, `dashboardCards` 159;
  - mobile: `openQueue` 286, `PettyCashScreen` 257, `AppShell` 189, `App` 187, `HomeScreen` 187, `PinPad` 161, `FloatSection` 160.

## Continuous integration

`.github/workflows/ci.yml` runs on every pull request and on pushes to `develop` and `master`. Each job is a required check:

- `js`: `npm ci`, which fails when `package-lock.json` disagrees with any workspace's `package.json`; then format, lint, typecheck, the lint-rule fixtures, the shared tests with their coverage thresholds, and the web tests.
- `mobile`: the jest suite.
- `api`: the API workflow (`xcode-api.yml`): lint, types, tests on PostgreSQL, the dependency audit, a fresh database migrated, verified and seeded, the migration tool, and the image scan.
- `web-image`: builds the web image and checks that it serves the sign-in page with its Content-Security-Policy.

## Deploying

Staging deploys itself when a push to `develop` passes every job. Nothing reaches into a host: each one installs the build CI publishes as a GitHub release.

- API (`deploy-api`): release `staging-api`, the API source of that commit and its checksum. A timer on the staging droplet runs `apps/api-python/deploy/install-release.sh`, which builds the release, migrates and verifies the database, switches over and restarts, and goes back to the previous build if the new one is not ready. The job waits until `$API_URL/release` names the commit and the API is ready.
- Web (`deploy-web`): release `staging-web`, installed by the cPanel account's cron (`deploy/cpanel/update.sh`).
- Android (`android`): release `staging-android`, an APK built against the staging API.

The API image and its settings are described in `apps/api-python/deploy/README.md` and `apps/api-python/docs/08-operability.md`. Migrations are a deploy step (`xcode-api db migrate`); starting the API never creates or migrates the schema.

## Web server settings

- `API_URL`: where the web proxy reaches the API (default `http://localhost:5000`). Production requires it, over HTTPS unless it names `localhost` or `127.0.0.1`. It is read per request, so one web image serves any environment.
- `TRUSTED_PROXY_HOPS`: how many trusted reverse proxies sit in front of the web server (a non-negative integer). Production must set it, `0` for none: the web server refuses to start without it, since a proxy left uncounted would give every browser the proxy's address and one shared sign-in limit. Development and tests default to `0`. The sign-in rate limit is per client, and Next.js keeps any `X-Forwarded-For` a client sends, so the proxy only names the client from the entry the outermost trusted proxy appended: the Nth from the right. At `0` no client address is forwarded and the API sees one shared address for the web server (safe, but one limit for everyone). `X-Real-IP` and `Forwarded` are never used. The API believes the forwarded address only from the proxies in `XCODE_TRUSTED_PROXIES`.
