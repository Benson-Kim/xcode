# Verification: challenge before you claim

This document is normative. It says how every claim of "done", "correct", "secure" or
"matches .NET" is attacked before anyone relies on it. `docs/09-testing.md` section 1 says
what counts as proof; this document says how to look for what is missing. It applies to:
- the challenge pass at the end of every implementation prompt (`docs/prompts/*.md`);
- every run of the verification prompt (`docs/prompts/verify.md`);
- the conversion audit (`docs/prompts/11-audit.md`).

The method is the five modes of the Fool (the `the-fool` skill: Socratic questioning,
falsification, pre-mortem, red team, dialectic), made concrete for this codebase. It is
not run interactively: no mode is chosen, all five run every time, and the "engage" step
is an attempt to refute your own findings.

## 1. Why this exists

Each of these passed its own prompt's tests and was found only because someone attacked a
green state afterwards:
- the production TLS rule accepted `?sslmode=verify-full&sslmode=disable` (libpq reads the
  last value; the parser read the first), found by the red team of 2026-10-11;
- PIN derivations queued without bound on asyncio's default executor, so a burst of
  sign-ins could pile up work and threads against the host's per-account thread cap, found
  by the same red team;
- the auth rate limit was not charged for bodies FastAPI refused before dependencies ran,
  found by the 04/05 validation;
- the .NET API gained 19 routes, two tables and a PDF dependency on 9 and 10 October that no
  inventory or design document recorded, although two inventories were edited on 10
  October; nothing in the plan said so until 2026-10-11.

The lesson: a previous review is a claim, not evidence. Every run starts as if nobody had
ever looked.

## 2. Stance

1. **Fresh eyes, every run.** Assume no earlier challenge happened. Earlier reports,
   audits, memory notes, "validated" statuses, docs, commit messages, docstrings, comments
   and test names are claims to falsify. Read earlier audits only after your own pass, and
   only to find regressions and what they missed.
2. **Steelman, then attack.** Restate the thesis in its strongest form (the claims it
   implies, each with the code that would carry it) before challenging it. A challenge
   against a weaker version of the code is void.
3. **Ground every challenge.** `file:line`, the input or state, the expected and the actual
   behaviour. "What if something goes wrong" is not a challenge and is dropped.
4. **Concede what holds.** A challenge that fails its refutation attempt is recorded as
   conceded, with the guard that defeated it. That record is coverage evidence too.
5. **Synthesis is mandatory.** Every surviving challenge ends as exactly one of:
   - fixed, with a test that fails without the fix (fix mode only);
   - a document corrected (the code is right, the document was wrong);
   - an open question in `docs/13-open-questions.md`, with a default and what it blocks;
   - a residual risk in `docs/12-security.md` section 7, with an owner.
   A bare objection is not an output.
6. **Depth for narratives, breadth for probes.** Each mode reports its 3 to 5 strongest
   challenges; minor objections are not stacked to look thorough. The probe checklist in
   section 4 is covered in full: every probe gets a verdict.
7. **No silent zero.** A domain with no findings lists the three hardest attacks tried
   there and why each failed. "Nothing found" without that list is "not checked".
8. **Verdicts per clause.** Allowed verdicts: `holds`, `fails`, `unproven`, `n/a`,
   `not checked` (with the reason). "Mostly done" is not a verdict. Counts must add up.
9. **Facts over memory.** Versions, hosts, timings and file states are measured in this
   run (`git status`, file times, `SELECT version()`, `pytest` output), never copied from
   a note.
10. **The domain expert wins over generic scepticism.** The .NET code and its tests decide
    behaviour, the design documents decide intent; a challenge that contradicts them needs
    evidence from them.

## 3. The five modes, applied here

| Mode | Question | How it runs here | Output |
|---|---|---|---|
| Expose assumptions (Socratic) | What is taken for granted? | List the assumptions the scope relies on: words like "always", "never", "only", "cannot", "already checked", invariants stated in comments, docs or routine headers, and environment facts (PostgreSQL version, host, thread budget, clock). For each, find what enforces it. | Assumption inventory: assumption, where stated, enforced by (`file:line`) or "nothing" |
| Test the evidence (falsification) | What would prove this wrong? | Extract every claim the scope makes (prompt deliverables, invariants, doc clauses, report lines). For each, write the observation that would disprove it and look for it: run the test, read the assertion against the code path, query the database. Grade the evidence (section 5). | Claims table with falsifier, result and grade |
| Find the failure modes (pre-mortem) | It is three months after cutover and this failed. Why? | Write specific narratives: a trigger, a number or threshold, the chain of effects, the point where someone notices. Then invert: what would guarantee failure, and does that condition exist now? | Ranked narratives (likelihood x impact), early signs, mitigations |
| Attack this (red team) | How would someone break, exploit or game it? | Use the personas below against the scope's routes, routines and data. | Ranked attack vectors with the defence that stops each, or the gap |
| Argue the other side (dialectic) | What if the rejected option was right? | For each design decision the scope relies on (an ADR in `docs/02-stack.md`, a default in `docs/13-open-questions.md`, a "deliberately not" in `docs/01-architecture.md` section 10), argue the alternative at full strength, then keep or change the decision. | Decision, strongest counter, verdict, confidence |

Red-team personas (specific to xcode; add others the scope invites):
1. **Clerk in tenant A**: a valid token, a few permissions, scoped to some vehicles. Wants
   tenant B's rows, unscoped vehicles' money, or a permission they do not hold. Tries
   foreign ids, aggregates, exports, history, error differences (403 versus 404), paging
   counts.
2. **Dismissed employee with the old phone**: refresh token, trusted device, an offline
   queue of captures. Tries to keep a session after deactivation, replay old captures,
   approve their own entries.
3. **Outsider with a list of phone numbers**: enumeration, PIN guessing, code flooding
   (mail cost), timing differences, lockout of real users.
4. **Compromised neighbour on the host**: the web app or another process on the same
   cPanel account. Reads secrets from files and environment, exhausts the thread cap,
   tampers with the release the installer fetches.
5. **Operator with the CLI**: uses `ops_*` routines beyond intent, leaves no audit row,
   runs as the wrong role.
6. **Hurried DBA**: runs a migration against the wrong database, as the owner, disables
   RLS to fix data, edits a routine in place.
7. **The calendar**: month ends, 29 February, year boundaries, time zones other than
   Africa/Nairobi, midnight between check and write, a client clock that is wrong.
8. **The gamer**: a petty-cash holder inflating a float, approving their own spending,
   reopening a closed day, splitting an expense to stay under an approval limit, an export
   cell that starts with `=`.

## 4. Domains and probes

Every run covers the domains its scope touches; D10 and D11 are always in scope. Each probe
gets a verdict. Probes are a floor, not a ceiling.

`docs/16-security-matrix.md` maps the installed app-security skills to these domains: which
skill cluster a session loads, the invariant it targets, and the test its findings must
land in. Load only the cluster for the domain you are attacking (cost discipline); a skill
finding is not done until it is a test that fails without the fix.

### D1 Tenancy and authorization
- Every tenant-scoped `api.*` routine calls `tenancy.enter_organization` before its first
  read of a tenant table; the `db verify` tenant-guard check would catch a new routine that
  does not (prove the check bites: name the routine shape it rejects).
- Every tenant table, including new ones, has RLS and the `tenant_isolation` policy. List
  every function owned by `xcode_owner` (they read past RLS: `FORCE ROW LEVEL SECURITY` is
  deliberately off) and show that no caller input can steer them to another organization.
- Scoped viewers: hidden vehicles and companies do not leak through totals, counts
  (`totalVehicles`, `partial`, `active_amount`), report sums, history, exports, dashboard
  cards, option lists, ordering or the difference between 403 and 404.
- Every `{id}` route proves the id belongs to the caller's organization and is visible to
  the caller; a foreign id answers what the contract says (usually 404).
- Anti-escalation in SQL: only an Owner grants Owner, nobody edits themselves, nobody grants
  a permission they do not hold.
- The permission catalogue equals `packages/shared` and the design's `MODS` list.

### D2 Identity and sessions
- Unknown number, paused account and capped untrusted device answer byte for byte the same
  (status, body, headers minus `X-Request-ID` and `Date`) and take similar time (dummy hash
  for unknown accounts; a full PIN pool answers the same way for known and unknown
  numbers).
- The lockout model: trusted-device pauses, the untrusted cap, resets only on a PIN change
  or a verified new device; clearing a pause does not reset the cap.
- A `security_version` bump, a deactivation and a device revocation stop the next request
  (no cache anywhere); refresh rotation; reuse of a rotated token revokes the family.
- Tokens: algorithm pinned, `iss`, `aud`, `exp`, zero leeway, exact claim set; previous
  signing keys verify only.
- Codes: caps (superseded codes count), expiry through `ManualClock`, mail enqueued only
  after commit, development codes refused outside development.
- The rate limit runs before body validation and is charged once per request.

### D3 Data integrity and concurrency
- Every `version` column is bumped by the routine that writes the row and compared with
  `expected_version`; a stale writer gets `XC409` and the 409 the contract describes
  (with `current` where it says so). Prove both with two connections, not one.
- Lock order: list the `FOR UPDATE` and row-lock statements per routine; two routines must
  not take the same pair of locks in opposite orders. Count the implicit locks too: a
  foreign-key check takes `FOR KEY SHARE` on the referenced row, so a routine that locks a
  row `FOR UPDATE` and later waits for a lock another routine holds while inserting a row
  that references it is an opposite-order pair (`FOR NO KEY UPDATE` does not conflict with
  the check). Prove a lock mode with `NOWAIT` from a second connection.
- Replays rely on a unique constraint, not a prior `SELECT`; an identical replay adds no
  change-log row; two identical first writes racing produce one row.
- Append-only tables refuse `UPDATE` and `DELETE` by grant, not by convention.
- Money: `numeric(14,2)` everywhere money is stored; each rounding rule names its mode
  (banker's or half away from zero) and is rounded once; a sum cast back into
  `numeric(14,2)` cannot overflow for the largest plausible tenant.
- One routine call is one transaction; only commands marked idempotent are retried.

### D4 Contract parity (.NET and the clients)
- Routes: the .NET route table (`apps/api/Api/*.cs`), `docs/06-http-contract.md`, the
  Python routers and the OpenAPI document list the same methods, paths, status codes,
  operation ids and tags. Any .NET route missing from `docs/06` is a finding.
- Bodies: property names and order, nullability, numbers versus strings (Money is a JSON
  number), integer versus word enumerations, the legacy `useGroupping`.
- Errors: problem-details shape, exact titles and details from `http/messages.py`, empty
  bodies for 404, 405, 415 and 429, `WWW-Authenticate: Bearer` on envelope 401s.
- Clients: what `apps/web`, `apps/mobile` (the offline queue reads 200 `{id, version}`, 409
  `current` and the `detail` of a 400, 403 or 404) and `packages/shared` read.
- Drift: `git log` and `git diff` of `apps/api` and `tests/api` since the inventory dates;
  the drift register in `docs/prompts/README.md` is current.

### D5 Domain rules and time
- Business dates come from the organization's time zone (`tenancy.business_date`) and an
  injected `p_now`; no `now()`, `current_date` or `clock_timestamp()` in a decision path
  outside the helpers that own them.
- Week start per organization; month ends; 29 February; schedules on day 28 and "last
  day"; zones other than Africa/Nairobi, including one with daylight saving.
- Automatic reasons and snapshots equal the .NET text byte for byte (`d MMM yyyy`,
  `{CUR} {amount}`, key order).
- Normalisation parity (phones, emails, registrations, case folding, open question 17).

### D6 Database craft
- `db verify` exit 0, and each of its checks is shown to fail on a database built to break
  it (a test per check, or the check is `unproven`).
- `SECURITY DEFINER` routines have a fixed `search_path` and the documented owner;
  `EXECUTE` is revoked from `PUBLIC` on every function, including ones created after the
  default-privilege statements ran; no stale overload of a changed signature survives with
  wider grants.
- No dynamic SQL built from inputs (`format()` only with `%I`/`%L` on catalogue values).
- Migrations: forward-only, checksummed, advisory-locked, a reviewed `.down.sql`; routine
  files idempotent.
- Every query a routine runs has its index in `docs/04-schema.md`; timeouts per role.
- Version: list every feature the SQL uses that is newer than the oldest PostgreSQL the
  project claims to support (for example `MERGE` 15, `NULLS NOT DISTINCT` 15,
  `pg_input_is_valid` 16, `ANY_VALUE` 16, `JSON_TABLE` 17, `uuidv7()` 18, `RETURNING OLD`
  18). Measure the versions in use (`SELECT version()` locally, in CI, on the host).
- The test template: `tests/support/database.py` rebuilds `xcode_template` when its
  fingerprint comment differs from the current `db/` files and runner, and refuses to while
  another session holds the shared use lock. Show that the comment of the template the run
  used equals the fingerprint of the files you tested, and that no session started before
  the harness took that lock was still running when the template was rebuilt.

### D7 Performance and scale
- Statement budgets asserted per endpoint through `statement_counter`.
- `EXPLAIN (ANALYZE, BUFFERS)` at 10x the demo seed for the heavy reads (week grid,
  dashboard, reports, ledgers, exports).
- No query per row inside a routine loop.
- Connections: pool size x replicas against the role connection limits.
- Threads: event loop, the default executor, the PIN pool, mail, pool workers, counted
  against the host's thread cap (100 on the cPanel account, shared with the web).
- Hot rows (the organization and `settings_version` rows under capture bursts); paging
  capped in Python and SQL; exports bounded in rows, bytes and time.

### D8 Reliability and operability
- Startup order, contract version, readiness semantics, shutdown drain, mail failure paths.
- Retries only for idempotent commands; every timeout set (statement, lock, idle, SMTP,
  body read).
- Logs never carry bodies, PINs, codes, tokens, phone numbers or emails (grep every log
  call in the scope); `X-Request-ID` everywhere.
- CLI exit codes; every state-changing command writes `ops.operator_actions`.
- Every `XCODE_*` setting appears in `settings.py`, `.env.example`, `docs/08-operability.md`
  and `tests/unit/test_settings.py`.

### D9 Hosting and supply chain
- The documented deployment matches the real target (open questions 39 to 45): PostgreSQL
  and Python versions on the host, whether the five roles can exist, how an ASGI app runs
  under the host's process manager with its lifespan, the thread cap, where secrets live,
  how a release is proven authentic.
- Lock files with hashes; `pip-audit` clean; CI actions pinned; workflow permissions
  minimal; no secret or `.env` in the repository.
- The production TLS rule read exactly as libpq reads the URL.

### D10 Tests as evidence (always)
- No fake of the capability under test; fakes only prove orchestration and match the
  routines (`tests/db/test_fakes_match_routines.py`).
- Grep the scope's tests for `skip`, `xfail`, `importorskip`, early `return`, broad
  `except`, `sleep`, assertions on status alone where the body is the contract.
- A test named after a rule asserts the output that distinguishes the rule; for the five
  most important invariants, describe a wrong implementation and say whether the tests
  would catch it ("would a routine that skipped the visibility check still pass?").
- Every `Raises:` code in a routine header has a test.
- The full suite ran once on a fresh template with its counts (passed, failed, skipped,
  errors) and duration; a partial run is evidence only for what it ran.

### D11 Documents and prompts (always)
- Every doc clause the scope touches matches the code; section references in prompts still
  resolve; `docs/13-open-questions.md` and the README status are current.
- Claims in memory notes and earlier reports that the scope relies on are re-measured.

## 5. Evidence grades

| Grade | Means | Example |
|---|---|---|
| A | A test against real PostgreSQL or the real app that fails without the code, and whose assertion distinguishes the claim | a two-connection test where the stale writer gets 409 with `current` |
| B | A real test reaches the path, but its assertion is weaker than the claim | asserts 409, not the body the mobile queue reads |
| C | Indirect: a unit test with fakes for a rule the database owns, or a test that reaches the path by accident | a use-case test with `FakeSetupRepository` for a visibility rule |
| D | Words: docs, comments, reports, memory, commit messages | "validated on 2026-10-10" |
| F | Nothing | |

A claim graded C, D or F is `unproven`. Only A makes a security, tenancy or integrity
claim `holds`.

## 6. Severity

| Severity | Means |
|---|---|
| Blocker | Cross-tenant read or write, privilege escalation, authentication bypass, data loss or corruption, a contract break a released client hits, a deploy that cannot work on the real host |
| Major | A rule wrong on a reachable path, a 5xx on a valid request, a missing test for a security or integrity claim, documentation that would make the next session build the wrong thing |
| Minor | Wrong message text, a weak assertion, a missing index with small data, a doc reference that no longer resolves |
| Note | A hardening idea or style point with no failure scenario |

## 7. Challenge record

Every finding is one row:

| Field | Content |
|---|---|
| id | `V-<domain>-<n>`, unique in the report |
| mode | Socratic, falsification, pre-mortem, red team or dialectic |
| claim attacked | the clause, with where it is stated |
| challenge | the concrete scenario: input or state, expected, actual |
| evidence | `file:line`, test name, command output |
| refutation tried | what you did to prove the challenge wrong, and what happened |
| verdict | survives (with severity) or conceded (with the guard that defeats it) |
| synthesis | fixed (+ test), doc corrected, open question #, residual risk, or "for the user" with a recommendation |
