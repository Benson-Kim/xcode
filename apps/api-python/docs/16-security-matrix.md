# 16 — Security test matrix

Scope: the Python API (`apps/api-python`) and the web-facing surface that reaches it
(response headers, cross-origin, and anything the API emits that a browser or spreadsheet
renders). The mobile app is **out of scope** for this round.

This file turns "load N security skills" into a bounded checklist. It maps each applicable
skill to the session that runs it, the `docs/14-verification.md` domain it serves, the
invariant it targets (`CLAUDE.md` "Strengths to preserve"), and the concrete test artifact
its findings must land in. A skill run is not done until its finding is a committed test
that fails without the fix (`00-principles.md` section 11; the user's security-skills gate).

Offensive skills run **only** against local targets we own: the 5433 test cluster, a local
`xcode-api serve`, the code. Never the cPanel `priori` account, staging, or any shared or
production host.

## 0. The rule this table exists to enforce

- A loaded skill protects nothing. It produces findings.
- A finding hardens the system only once it is a regression test folded into the suite.
- The metric is not "skills loaded"; it is "every applicable skill's finding is a passing
  assertion, run in CI, on a committed SHA, against a real host."

## 1. Clusters (the working set)

One cluster per session so no session drowns in context (cost discipline). Each cluster
lists its skills, owner session, `docs/14` domain, invariant, and where its tests live.

### SC1 — Auth and session attack · domain D2
Owner: a fresh `verify.md prompt:07b D1` session (NOT revenue-17, which built D1), with the
first live attack on local `xcode-api serve`.

Skills: `testing-api-authentication-weaknesses`, `testing-jwt-token-security`,
`exploiting-jwt-algorithm-confusion-attack`, `performing-jwt-none-algorithm-attack`,
`performing-api-rate-limiting-bypass`.

Invariant: enumeration-resistant responses (unknown number / paused / capped untrusted
look identical); five-wrong-PIN lock in both scopes; HS256 verify rejects `alg=none` and
RS/HS confusion; code caps (3 tries, 1/min, 5/hr); auth limiter charged before auth.

Tests: `tests/api/test_auth_*.py`, `tests/api/test_auth_races.py`, new
`tests/api/test_jwt_forgery.py` (alg-none, alg-confusion, truncated-key HS384/HS512 forgery
→ 401), new `tests/api/test_auth_enumeration.py` (the number step and lock paths return the
same body/headers for real and simulated accounts).

### SC2 — Object, function and property authorization · domain D1
Owner: `verify.md prompt:06`, and a re-pass over 05's access/people.

Skills: `testing-api-for-broken-object-level-authorization`, `exploiting-idor-vulnerabilities`,
`exploiting-broken-function-level-authorization`,
`detecting-broken-object-property-level-authorization`,
`exploiting-excessive-data-exposure-in-api`, `exploiting-mass-assignment-in-rest-apis`
(with `testing-api-for-mass-assignment-vulnerability`).

Invariant: tenant RLS on every service role (no BYPASSRLS); anti-escalation (only Owner
grants Owner, cannot edit yourself, can only grant permissions you hold); snapshot/response
field whitelists; no mass-assignment into version, OrganizationId, role or permission sets.

Tests: `tests/db/test_*` RLS and grant tests; `tests/api/test_access_routines.py`,
`test_people.py`; new `tests/api/test_object_authorization.py` (a token for org A cannot
read/write any id belonging to org B — numeric, uuid and slug ids); new
`tests/api/test_mass_assignment.py` (extra body fields are ignored, never bound).

### SC3 — Injection · domain D6
Owner: each build phase that adds a routine or an export; plus one dedicated sweep.

Skills: `exploiting-sql-injection-vulnerabilities`, `exploiting-sql-injection-with-sqlmap`,
`performing-second-order-sql-injection`, `exploiting-api-injection-vulnerabilities`
(CSV / Excel formula injection on exports).

Invariant: no-raw-SQL posture (only justified migrations use SQL); every value reaches the
DB as a bound parameter; stored snapshots replayed later are re-escaped (second-order);
export cells starting `= + - @ TAB CR` are neutralised before Excel/CSV.

Tests: existing structure tests that forbid SQL text in Python; new
`tests/api/test_export_injection.py` in 08b (a vehicle name or category of `=cmd()` exports
as inert text); a scripted `sqlmap` run against the most parameter-heavy routes, recorded
in the report, with any finding pinned as a routine test.

### SC4 — Business logic and concurrency · domains D3, D5
Owner: `verify.md` on prompt:07, 08, 08b.

Skills: `testing-for-business-logic-vulnerabilities`, `exploiting-race-condition-vulnerabilities`.

Invariant: version concurrency → 409; idempotent replay; petty-cash balance = opening +
issued − expenses − credit notes; back-dating limit enforced on the record's date; caps
(code, untrusted device, PIN pool) cannot be beaten by parallel requests.

Tests: the two-connection lock tests already added for 05; new per-write race tests for
07/08/08b money paths; replay-idempotency tests; a single-packet parallel attack on
balance/approval endpoints, each failing first with the guard removed.

### SC5 — Input, schema, abuse and inventory · domain D8
Owner: `verify.md prompt:00` and one API-wide fuzz pass.

Skills: `implementing-api-schema-validation-security`, `testing-api-security-with-owasp-top-10`,
`performing-api-fuzzing-with-restler` (or schemathesis driven by `openapi.json`),
`implementing-api-rate-limiting-and-throttling`, `implementing-api-abuse-detection-with-rate-limiting`,
`performing-api-inventory-and-discovery`, `detecting-shadow-api-endpoints`.

Invariant: 1 MiB body cap; 429 with empty body; strict pydantic rejects unknown/extra and
bad types with 400; U+0000 and unpaired surrogates refused before auth; every route in the
OpenAPI document is documented in `docs/06` and vice versa (no shadow endpoints).

Tests: a schemathesis/RESTler harness over `openapi.json` wired into CI (negatives become
fixed tests); `tests/api/test_http_plumbing.py` body-cap and 429 assertions; the prompt-11
OpenAPI ↔ `docs/06` crosswalk.

### SC6 — Web-facing headers and cross-origin · domain D4 (web where it matters)
Owner: the web verification pass, when web is pointed at local Python.

Skills: `testing-cors-misconfiguration`, `performing-content-security-policy-bypass`,
`performing-clickjacking-attack-test`, `performing-csrf-attack-simulation`,
`testing-for-xss-vulnerabilities`.

Invariant: CORS serves no credentials and no wildcard-with-credentials; the API emits no
HTML (JSON only), so reflected/stored XSS has no sink in the API itself — the check is that
no field is echoed as HTML and that any string the web renders is treated as text; bearer
auth (not cookies) means CSRF is not applicable to the token flow, which the test asserts
rather than assumes; security headers present where the API is the origin.

Tests: `tests/api/test_http_plumbing.py` header and CORS assertions; a web browser pass
(your test-before-push rule) confirming an injected value in a name/reason/category field
renders as text, not markup, in every screen that shows it.

### SC8 — Secrets, supply chain and CI · domain D9
Owner: the dedicated security-tooling session (Wave 3 C).

Skills: `implementing-secret-scanning-with-gitleaks`, `implementing-secrets-scanning-in-ci-cd`,
`detecting-dependency-confusion`, `detecting-supply-chain-attacks-in-ci-cd`,
`analyzing-sbom-for-supply-chain-vulnerabilities`, `implementing-semgrep-for-custom-sast-rules`,
`integrating-sast-into-github-actions-pipeline`, `integrating-dast-with-owasp-zap-in-pipeline`.

Invariant: no secret or credentialed connection string in the tree or history; GitHub
Actions pinned by commit SHA, not tag (currently tag-pinned — `checkout@v4`, `trivy@0.28.0`);
SAST (CodeQL/Semgrep) and a DAST (ZAP API scan) gate the pipeline; an SBOM is generated and
checked against CVEs; dependency-confusion guarded (private names, index pinning).

Artifacts: changes to `.github/workflows/xcode-api.yml`; `docs/12-security.md` updates; a
gitleaks history scan recorded in the report; custom Semgrep rules under the repo; each tool
finding pinned as a test or a CI gate.

### SC9 — Threat model and review · cross-cutting
Owner: the prompt-11 final audit (read-only Opus).

Skills: `security-reviewer`, `secure-code-guardian`, and one of
`implementing-threat-modeling-with-mitre-attack` / `performing-threat-modeling-with-owasp-threat-dragon`.

Artifact: a threat-model section appended to `docs/12-security.md` (assets, entry points,
trust boundaries, the accepted-risk register already in `docs/12` section 7 mapped to
MITRE ATT&CK technique ids), referenced by the go/no-go verdict.

## 2. Watch-list (not applicable now; revisit if the surface changes)

- **SSRF** (`performing-ssrf-vulnerability-exploitation`, `performing-blind-ssrf-exploitation`):
  the API makes no user-controlled outbound fetch. Branding stores URLs but does not fetch
  them; logo upload is multipart, not a URL. Add SC-SSRF the day a webhook, link-preview, or
  server-side branding fetch is introduced.
- **Blue-team / SIEM detection** (`detecting-sql-injection-via-waf-logs`,
  `detecting-anomalous-authentication-patterns`, `detecting-api-enumeration-attacks`,
  `analyzing-api-gateway-access-logs`): these need a running log pipeline. Defer to
  post-deploy operability, not pre-cutover certification.
- **Deserialization** (`exploiting-insecure-deserialization`): no pickle/yaml.load/eval in
  `src`. Re-check if any is added.

## 3. Excluded families (and why)

| Family | Skills | Why excluded |
|---|---|---|
| Mobile RE / forensics / malware | apktool, jadx, Frida, objection, MobSF, Cellebrite, cert-pinning bypass, android-intents, mobile-malware, insecure-data-storage, mobile-app-management, intercepting-mobile-traffic, testing-mobile-api-authentication, conducting-mobile-app-pentest | Mobile app is out of scope this round |
| GraphQL | depth-limit, introspection, graphql-security-assessment | API is REST only (no GraphQL in `src`) |
| WebSocket | exploiting-websocket, testing-websocket-api-security | No WebSocket endpoints |
| OAuth / OIDC / federated | oauth2-flaws, oauth-misconfiguration, device-code-phishing, oauth-token-theft, oauth-consent, oauth-scope-review, passwordless-fido2/entra, hardware-security-key, zero-knowledge-proof | Auth is phone + PIN + HS256 bearer; no third-party IdP |
| Cloud-vendor controls | AWS WAF, GCP Binary Authorization, APIM gateway, OpenVAS, Rapid7 InsightVM, Snyk appliance, Vault | Host is cPanel, not a cloud gateway; no such infra |
| NoSQL injection | exploiting-nosql-injection | PostgreSQL only |
| Wifi / container escape | aircrack, escaping-containers-to-host | Not in the threat model (no Docker on host) |

## 4. Execution order

The exact per-session handoffs for the waves below are in `docs/prompts/security-waves.md`.
Wave 3's two independent prompts are `docs/prompts/parity.md` (.NET vs Python, response by
response) and `docs/prompts/security-tooling.md` (SC8 plus the SC5 fuzz half).


1. **Wave 0** — commit + push the baseline (CI runs the full suite on PG 18, pip-audit,
   trivy on a committed SHA); hosting facts for questions 39–45. SC8 begins here (gitleaks
   on history, SHA-pin the actions) because it needs the committed tree.
2. **Wave 1** — SC1, SC2, SC4 as the fresh `verify.md` runs on 06, 07, 07b-D1, one at a time.
3. **Wave 2** — build D2→D3→D4→08→08b→09→10; SC3 and SC4 ride each build; SC3 export checks
   land in 08b.
4. **Wave 3** — SC5 (fuzz), SC6 (web), SC8 (full CI hardening), independent parity and
   capacity drills.
5. **Last** — SC9 inside prompt 11; threat model written; go/no-go.

## 5. Independent-of-Claude checks (break the model-checks-model loop)

These are not skills; they are the evidence Claude cannot supply about itself.

- Response-by-response parity: run .NET (XCodeTest) and Python on the same seed, diff every
  response; only design-register rows may differ.
- A DBA review of `db/routines` (the reason the rules live in stored procedures).
- Real web/mobile v2.11 clients pointed at local Python.
- If budget allows, a short human pentest of the sign-in flow.

Completion claim this matrix supports: **no open critical or major finding across SC1–SC9
and the independent checks, every finding pinned as a passing test or CI gate, and the
owner has signed off the residual-risk register in `docs/12` section 7.** "Completely
secure" is not a claim anyone can prove; this is the defensible one.
