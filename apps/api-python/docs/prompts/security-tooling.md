# Security-tooling prompt: SAST, DAST, secrets, supply chain, fuzz

Paste everything below the line into a fresh Claude Code session started in the repository
root, on Opus, after Wave 0a (the tree is committed and pushed, so there is a history and a
CI run to harden). This session runs cluster **SC8** of `docs/16-security-matrix.md` and the
fuzz half of **SC5**: it points real tools at the committed code and a local running server,
turns every finding into a test or a CI gate, and leaves the pipeline stronger than it found
it.

Every finding is pinned: a secret becomes a rotation + a scanner gate, a SAST hit becomes a
fix + a rule that stays on, a DAST/fuzz hit becomes a failing-first test. A clean scan with
no gate added is not a result.

---

You are hardening `apps/api-python` and its pipeline against external attack and supply-chain
compromise. You attack **only** what we own: the committed repository, a local
`xcode-api serve` on the 5433 cluster, and the CI configuration. Never scan, fuzz or attack
cPanel `priori`, staging, or any shared or production host — doing so is outside the
authorised-testing boundary in `CLAUDE.md`.

## Parameters

- `MODE:` <`report`: write the report plus proposed CI diffs and rules, change no running
  config | `fix`: also apply the CI hardening and the code fixes, each with a test or gate
  that fails without it>

## Read first

1. `CLAUDE.md` (authorised-testing boundary, shared tree); `apps/api-python/README.md`.
2. `docs/16-security-matrix.md` (SC8 and SC5, and the excluded families — do not run the
   mobile, GraphQL, WebSocket, OAuth or cloud-vendor tools); `docs/12-security.md` section 7
   (the residual-risk register) and `docs/14-verification.md` D9.
3. `.github/workflows/xcode-api.yml` (the current pipeline: it has pip-audit and trivy;
   actions are tag-pinned; there is no secret scan, no SAST, no DAST, no SBOM).
4. `requirements.txt`, `requirements.lock.txt`, `requirements-dev.txt`, `pyproject.toml`,
   `deploy/Dockerfile`.

## Tasks

Each task names the installed skill to load (`docs/16` SC8/SC5) and the gate it must leave.

### T1 Secret scanning over history
Skill: `implementing-secret-scanning-with-gitleaks`, `implementing-secrets-scanning-in-ci-cd`.
- Run gitleaks and trufflehog over the full git history of the branch, not just the working
  tree. A signing key, database password or credentialed connection string anywhere in
  history is a blocker: rotate it (the key and password are regenerated outside the repo) and
  record that the old value is burned.
- Confirm `.env` is git-ignored and absent from history; confirm `.env.example` carries only
  placeholders.
- Gate: a gitleaks step in CI that fails the build on any hit, with a committed config whose
  allow-list is justified line by line.

### T2 SAST
Skill: `implementing-semgrep-for-custom-sast-rules`, `integrating-sast-into-github-actions-pipeline`.
- Run Semgrep with the Python and security rule packs, and CodeQL for Python, over `src` and
  `db`.
- Write custom Semgrep rules for this codebase's invariants: no SQL string built in Python
  outside `db/session.py`, `db/pool.py`, `db/migrate.py`, `db/verify.py`; no `EXECUTE`/
  `format(` in a routine without a justification comment; no `SECURITY DEFINER` without
  `SET search_path`; no logging of a body, phone, email, PIN, code or token; no `pickle`,
  `yaml.load`, `eval`, `exec` in `src`.
- Triage every hit (`performing-web-application-vulnerability-triage`): fix a true positive
  with a test; suppress a false positive with an inline reason, never a blanket ignore.
- Gate: Semgrep and CodeQL run on pull requests and block on a new high finding.

### T3 Dependency and supply-chain integrity
Skill: `detecting-dependency-confusion`, `detecting-supply-chain-attacks-in-ci-cd`,
`analyzing-sbom-for-supply-chain-vulnerabilities`.
- Pin every GitHub Action by commit SHA, not tag (`checkout@v4`, `setup-python@v5`,
  `trivy-action@0.28.0` and the rest become `@<40-hex-sha>` with the tag in a trailing
  comment). Add `permissions:` least-privilege to each job and a `concurrency` guard.
- Check for dependency confusion: every dependency resolves from PyPI by the intended name;
  the lockfile is the single source; no internal package name shadowable by a public one.
- Generate a CycloneDX SBOM in CI, store it as an artifact, and scan it against the NVD/OSV
  CVE feed; a known-exploitable CVE in a runtime dependency fails the build.
- Gate: SHA-pinned actions, least-privilege `permissions`, SBOM generation + CVE check.

### T4 DAST against a local server
Skill: `integrating-dast-with-owasp-zap-in-pipeline`.
- Start `xcode-api serve` locally with a seeded database and a valid token. Run the OWASP ZAP
  API scan driven by `xcode-api openapi` (the OpenAPI document), baseline then full.
- Triage findings against the known contract: a missing security header where the API is the
  origin, a verbose error, a method allowed that should not be. Confirm the 1 MiB body cap,
  the 429 empty body, and that framework 404/405/415 carry empty bodies.
- Gate: a ZAP baseline scan in CI (against an ephemeral server) that blocks on a new high
  alert; each real alert pinned as a `tests/api/` assertion.

### T5 Schema fuzzing
Skill: `performing-api-fuzzing-with-restler`, `implementing-api-schema-validation-security`,
`testing-api-security-with-owasp-top-10`, `performing-api-inventory-and-discovery`,
`detecting-shadow-api-endpoints`.
- Drive schemathesis (or RESTler) from `xcode-api openapi` against the local server with a
  valid token: property-based inputs, boundary values, wrong types, extra and missing fields,
  oversized and malformed bodies, U+0000 and unpaired surrogates.
- Any 500 is a finding (the contract says a malformed input is a 400, a missing code is the
  only 500 and that is a defect). Any route reachable but absent from the OpenAPI document or
  from `docs/06` is a shadow endpoint — a finding.
- Gate: a schemathesis run wired into CI; every crash or contract violation pinned as a
  failing-first test in `tests/api/`.

### T6 Targeted injection and rate-limit probes
Skill: `exploiting-sql-injection-with-sqlmap`, `performing-api-rate-limiting-bypass`,
`implementing-api-abuse-detection-with-rate-limiting`.
- Run sqlmap against the most parameter-heavy routes (list filters, report queries) through
  the local server. The expectation is nothing: confirm the no-raw-SQL posture holds and
  record the attempt. Any hit is a blocker and a routine test.
- Probe the fixed-window rate limiter for edge-of-window bursts and header-spoofed source
  addresses (`X-Forwarded-For`); confirm the per-account caps hold where the window admits a
  burst, and that `ops.rate_limit_windows` growth (question 56) is bounded or recorded.
- Gate: injection tests on the probed routes; a rate-limit-bypass test.

## Invariants at the end

- No secret in the tree or history; any found is rotated and burned.
- CI gates added: gitleaks, Semgrep + CodeQL, SBOM + CVE scan, ZAP baseline, schemathesis;
  all actions SHA-pinned with least-privilege `permissions`.
- Every true-positive finding is a fix with a test, or a rule that stays on; every accepted
  residual is in `docs/12` section 7 with an owner.
- `docs/12-security.md` updated with what was scanned, with what tool version, and the
  result; the matrix SC8/SC5 rows annotated done.

## Verify (paste the outputs into the report)

```
# gitleaks + trufflehog over history: hits (expect 0 after rotation)
# semgrep + codeql: high findings before/after
# actions SHA-pin: grep -n "uses:" .github/workflows/xcode-api.yml  (every ref a 40-hex sha)
# sbom: the CycloneDX file + CVE scan result
# zap baseline + schemathesis: alert/crash counts, each mapped to a test
# fix mode: ruff check . && ruff format --check . && mypy ; pytest of the new tests
```

## Challenge pass (before the report)

Run the five modes of `docs/14-verification.md` over this work:
- assumptions: does a passing scan mean secure, or only that this tool, this version, these
  rules found nothing? State the coverage gap.
- falsification: plant a known-bad secret and a known SQLi pattern in a scratch branch and
  confirm the gates actually catch them.
- pre-mortem: which gate is advisory (warns) when it should block, and would a real finding
  slip through on a Friday merge?
- red team: can an attacker who controls a pull request disable a gate, exfiltrate a secret
  through CI logs, or poison the cache? (`permissions`, `pull_request_target`, cache keys.)
- dialectic: for each residual risk, argue it must be fixed now, then that it is acceptable
  to ship with a mitigation; record which won.

## Report format

Write `apps/api-python/docs/audit/<yyyy-mm-dd>-security-tooling.md`:
1. Verdict line: `clean + gated`, `gated with residual risks`, or `blocked`, with counts.
2. Per task T1–T6: tool, version, what was scanned, findings, the gate added.
3. Findings, blockers first, in the `docs/14` section 7 format; each with its pinned test or
   gate.
4. CI diff: the exact `.github/workflows/xcode-api.yml` change (SHA pins, new jobs,
   `permissions`).
5. Residual risks added to `docs/12` section 7, each with an owner.
6. The challenge pass, including the planted-finding proof that the gates fire.
7. Commands and outputs, trimmed.

## House rules

- Authorised-testing boundary: local and committed targets only. Never a shared or
  production host. If a scan would reach outward, stop and report instead.
- Shared tree: `git status` first; never revert or reformat others' changes; never bare
  `git stash`; never kill a process you did not start.
- `report` mode changes no running config (it writes the report and proposed diffs). `fix`
  mode edits under `apps/api-python/` and `.github/workflows/xcode-api.yml` only.
- No commits unless asked; no AI attribution; no plan/prompt/finding identifiers in code.
- Rotated secrets are regenerated outside the repo and never written back into it.
- At ~100k context or three hours, write the report with the tasks done, mark the rest `not
  run`, and say where to resume.
