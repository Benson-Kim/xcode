# Multi-platform authentication application

.NET 10 API (`apps/api`), Next.js web (`apps/web`), Expo/React Native mobile (`apps/mobile`) and a shared TypeScript package (`packages/shared`) in one npm-workspaces repository. The API tests are in `tests/api`.

## Requirements

- Node.js at the version in `.nvmrc`.
- .NET 10 SDK.
- SQL Server, only to run the API against a real database or the `SqlServer` test category.

## Commands

Run these from the repository root after `npm ci`. Each is a step in CI, so a green local run means a green pipeline.

| Command | Runs | CI job |
|---|---|---|
| `npm run format:check` | Prettier without writing (`npm run format` writes) | js |
| `npm run lint` | ESLint, including the module-boundary rules | js |
| `npm run typecheck` | `tsc --noEmit` in shared, web and mobile | js |
| `npm test` | lint-rule fixtures, then the shared, web and mobile tests | js, mobile |
| `npm run test:api` | the API tests except the `SqlServer` category (about 10 minutes) | api |
| `npm run test:api:sqlserver` | every migration against SQL Server; needs `SQLSERVER_TEST_CONNECTION` | api-sqlserver |

Each part also runs alone: `test:lint-rules`, `test:shared`, `test:web`, `test:mobile`, `typecheck:shared`, `typecheck:web`, `typecheck:mobile`. `restore:api` restores the API and its tests from their NuGet lock files (`--locked-mode`) and `build:api` builds both; extra arguments pass through, for example `npm run test:api -- -c Release --no-build`.

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
  - web: `SettingsForm` 550, `ExpenseCategoriesPage` 530, `VehicleEditor` 466, `AuthPanel` 456, `VehicleInvestmentTab` 325, `PettyCashPage` 288, petty-cash `EntryForm` 283, `CompaniesPage` 283, `RecurringPage` 278, `PreferencesForm` 181, the auth route's `POST` 159, `dashboardCards` 159, `VehiclesPage` 158;
  - mobile: `openQueue` 286, `PettyCashScreen` 257, `AppShell` 189, `App` 187, `HomeScreen` 187, `PinPad` 161, `FloatSection` 160.

## Continuous integration

`.github/workflows/ci.yml` runs on every pull request and on pushes to `develop` and `master`. Each job is a required check:

- `js`: `npm ci`, which fails when `package-lock.json` disagrees with any workspace's `package.json`; then format, lint, typecheck, the lint-rule fixtures, the shared tests with their coverage thresholds, and the web tests.
- `mobile`: the jest suite.
- `api`: a locked-mode restore, a build, and the API tests except the `SqlServer` category.
- `api-sqlserver`: a SQL Server service container. The `SqlServer` tests apply every migration to an empty database. Then the API image is built and run twice with `--migrate`; the second run must change nothing. Finally the image is started against the migrated database until `/health/ready` answers.
- `web-image`: builds the web image and checks that it serves the sign-in page with its Content-Security-Policy.

## Deploying

Build both images from the repository root:

```sh
docker build -t xcode-api apps/api
docker build -t xcode-web -f apps/web/Dockerfile .
```

For each release:

1. Run the new API image once with `--migrate`, with the production settings below, before any replica of it starts. It applies pending migrations and exits. A non-zero exit stops the release.

   ```sh
   docker run --rm -e ConnectionStrings__Auth=... -e Auth__SigningKey=... -e Email__Host=... -e Email__From=... xcode-api --migrate
   ```

2. Start the API replicas. Outside local development, starting the API never creates or migrates the schema.
3. Start the web replicas.

The API image listens on port 8080. Point liveness probes at `/health/live` and readiness probes at `/health/ready`, which checks the database.

## API settings

Environment variables, in ASP.NET Core's `Section__Key` form:

- `ConnectionStrings__Auth`: the SQL Server connection string.
- `Auth__SigningKey`: at least 32 random bytes. Changing it signs everyone out.
- `Email__Host`, `Email__From`, and optionally `Email__Port` (587), `Email__Username` and `Email__Password`: the SMTP server that sends sign-in codes.
- `Cors__Origins__0`, `Cors__Origins__1`, ...: browser origins allowed to call the API directly.
- `ForwardedHeaders__KnownProxies__0`, ...: the IP addresses whose `X-Forwarded-For` is believed (loopback when unset). Include the web server's address when it runs on another host.
- `RateLimiting__AuthPermitLimit`: sign-in requests per client per minute (30).

## Web server settings

- `API_URL`: where the web proxy reaches the API (default `http://localhost:5000`). Production requires it, over HTTPS unless it names `localhost` or `127.0.0.1`. It is read per request, so one web image serves any environment.
- `TRUSTED_PROXY_HOPS`: how many trusted reverse proxies sit in front of the web server (a non-negative integer, default `0`). The sign-in rate limit is per client, and Next.js keeps any `X-Forwarded-For` a client sends, so the proxy only names the client from the entry the outermost trusted proxy appended: the Nth from the right. At `0` no client address is forwarded and the API sees one shared address for the web server (safe, but one limit for everyone). `X-Real-IP` and `Forwarded` are never used. The API believes the forwarded address only from `ForwardedHeaders:KnownProxies` (loopback when unset).
