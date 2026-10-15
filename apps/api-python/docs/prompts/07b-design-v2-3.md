# Prompt 07b: the design notes v2.29 to v2.33, built ahead of .NET

Sign-in, people and access, dated targets, fleet numbers, the back-dating limit, the full
rights catalogue, three-level expense categories, savings rights, low-day reasons and the
revenue gap, from `docs/design/XCODE_Build_Notes_v2.3.md` (repository root).

The owner decided on 2026-10-11 that Python builds these rules before .NET has them
(`docs/13-open-questions.md` question 46). For the rows of this prompt the notes decide
behaviour, not the .NET code. They are rows B1 to B17 of the design register in
`docs/prompts/README.md`, without B18 and B19 and without the report parts. Prompt 08 owns
B19 (petty cash), 08b owns B18 (the saving model) and the report parts of B9, B15 and B16,
and 10 owns B20 (the data changes on the real data).

This prompt runs as separate sessions, one after the other:
1. **Design (Opus)**: D0 only. It writes the documents and changes no code. Then run
   `docs/prompts/verify.md` with `SCOPE: change:<the files D0 changed>` and
   `MODE: report` in another session, and fix what it finds before any build.
2. **Build sessions**, from the documents D0 wrote, in this order:
   - `build-auth` (D1, Opus, because authentication behaviour is redesigned);
   - `build-access` (D2, Sonnet);
   - `build-setup` (D3, Sonnet);
   - `build-revenue` (D4, Sonnet).

Requires prompts 00 to 07. Do not run beside any other prompt (shared `container.py`,
`main.py`, `application/repositories.py`, `tests/support/fakes.py`, `http/messages.py`,
the permission catalogue).

---

You are bringing `apps/api-python` level with the product rules of the design notes v2.29
to v2.33, ahead of the .NET API. The parameter below says which session you are.

`SESSION:` <`design` (D0) | `build-auth` (D1) | `build-access` (D2) | `build-setup` (D3) | `build-revenue` (D4)>

## Read first, in this order

1. `CLAUDE.md`; `apps/api-python/README.md`.
2. `docs/00-principles.md`, `docs/01-architecture.md` sections 3, 4, 7, 8, 9,
   `docs/11-naming.md`, `docs/14-verification.md`.
3. `docs/prompts/README.md`: the status, the drift register and the design register (both
   are claims from 2026-10-11; re-measure them), and the section "When a prompt and the
   code disagree" with its exception for the design register.
4. The design, in the repository root's `docs/design/` (not `apps/api-python/docs`):
   `XCODE_Build_Notes_v2.3.md` (all; v2.33 to v2.29, newest first, with later versions
   overruling earlier ones) and `XCODE_Web_v2.3.html` (the `MODS` permission list, the
   sign-in screens, the people form, the vehicle and target pop-ups, the revenue grid).
   Section 4 of v2.33 lists review aids that are not to be built.
5. `docs/13-open-questions.md` questions 46 to 55, and 22 (the legacy spelling the released
   phones still use: the pattern for keeping old clients working).
6. `design` only: `docs/07-auth.md` (all), `docs/04-schema.md` sections 3, 4, 5,
   `docs/05-routines.md` sections 2 and 3 and the setup and revenue routines,
   `docs/06-http-contract.md` sections 1, 2.1 to 2.6 and 3, `docs/12-security.md`, the
   code of prompts 00 to 07, and the clients: `apps/web` (sign-in, people, vehicles,
   expense categories, revenue), `apps/mobile/src/auth/*` and `apps/mobile/src/revenue/*`
   (mobile is parked at v2.11: what it sends must keep working, question 54). Read the
   .NET code only where it has part of a row (B2, B9, B14 rights, B17), to keep the wire
   shapes compatible.
7. Build sessions: the documents D0 wrote, the code of prompts 00 to 07, and the test style
   of `tests/api/test_auth_contract.py`, `tests/db/test_access_routines.py` and
   `tests/db/test_setup_vehicle_routines.py`. Do not read C#.

## Rules of this prompt

- The notes decide behaviour for these rows. Where they are silent, decide on the merits,
  write the reason into the document, and add an entry to `docs/13-open-questions.md` only
  for what is truly the owner's (business rules, wording, money).
- Released clients keep working (question 54). Phones at v2.11 send number and PIN
  together, use the current envelope, and hold trust by `deviceId`. New behaviour arrives
  as new routes, new fields and new outcomes. An existing route changes only where the
  notes require it, and then with a released-client test that shows the old request still
  gets an answer the old client understands.
- Existing data keeps working: PINs longer than four digits, trusted devices, sessions,
  weekly targets, vehicles without a fleet number, categories without a main category.
  The design says what happens to each until its owner changes it. The development data
  is migrated in this prompt's migrations; the real data is prompt 10's (row B20).
- Security stays at least as strong as it is (`docs/12-security.md`): enumeration
  resistance, the byte-for-byte refusals, digests only at rest, decisions in routines.

## Environment

As prompt 01; the local cluster is PostgreSQL 16 (`docs/09-testing.md` section 5).
`git status` first; write only under `apps/api-python/`.

## Deliverables

### D0 Design (`SESSION: design`; documents only)

Give every rule an id (`DN-B<row>-<n>`) with its notes section. For each, record the
.NET behaviour it replaces, with `file:line`, where one exists. Then write:

- `docs/07-auth.md`, rewritten for B1 to B8:
  - the number-first step and what it answers;
  - the PIN rules (exactly four digits; refused: one digit four times, runs, the last
    four digits of the person's own number, the PIN being replaced);
  - what happens to longer PINs and to the organization `pin_length` policy (section 8);
  - the lock after five wrong PINs on every device until a reset with a code;
  - the code rules: void after three tries with a new code sent, one a minute and five an
    hour;
  - forced reset;
  - the trusted-device token: random, hashed at rest, with device name, date trusted and
    last used, and expiry 90 days after last use;
  - removal of every device after a reset or a block;
  - the sign-in history;
  - the change-log wording, verbatim from the notes.

  The section on threats must decide two attacks, arguing each side at full strength:
  - **The number step.** Answering "PIN", "code" or "blocked" for a number tells anyone
    whether the number has an account and a PIN. The notes accept this only "where
    possible".
  - **Lock-by-stranger.** Anyone who knows a number can lock that person on every device,
    and the person then needs an email code to get back in. Today's model avoids this:
    untrusted devices hit a separate cap and never pause the account. Weigh the notes'
    per-device and per-address limits as the mitigation.

  Record each decision and its residual risk in `docs/12-security.md`.
- `docs/04-schema.md`: the new and changed tables and columns, each with constraints,
  RLS, grants and an index per query:
  - forced-reset and lock state;
  - device tokens, names and last use;
  - sign-in history;
  - the back-dating limit on the membership (mode, number, fixed date);
  - target sets with seven day figures;
  - fleet number (nullable for existing vehicles, required on every write);
  - optional initial investment;
  - main categories;
  - the organization settings for the low-day threshold (4,000) and the amber band (10 per
    cent).
- `docs/05-routines.md`: the helpers and `api.*` routines, with check orders and statement
  budgets. This includes the one helper that computes the earliest writable date
  (organization time zone; months back on a missing day falls back to the month's last
  day; the later of the rolling limit and the fixed date). Prompts 08 and 08b call it
  too.
- `docs/06-http-contract.md`:
  - the new routes (the number step, change PIN, own devices and their removal, the
    people sign-in actions, target sets, main categories);
  - the changed bodies (people status and "can change", vehicles with fleet number,
    target in force and the next one, revenue cells with amount and reason, the gap
    figure);
  - the message block, every sentence from the notes or decided here;
  - the client facts;
  - a note on each route that is new in Python and absent from .NET.
- The rights catalogue: the 58 rights of v2.32 plus the sign-in right of v2.33 (59).
  - Reconcile the prototype's `MODS` ids with the current keys and give every key a name
    under `docs/11-naming.md`.
  - State the role defaults, and the grants a migration copies: whoever can add a
    petty-cash expense today gets "edit own", and whoever holds a scheduled-items right
    gets the matching savings right.
  - Prompt 08 uses the petty-cash keys, 08b the savings keys.
- `docs/09-testing.md` section 4: the tests that will pin each rule.
- `docs/10-data-migration.md` section 3: the B20 rows (weekly target to a dated set, a
  seventh per day; people without a PIN; fleet numbers; copied rights; categories without
  a main category).
- `docs/13-open-questions.md`: what is truly the owner's.
- `docs/prompts/README.md`: mark rows B1 to B17 "documented" (B18 and B19 stay with their
  owners); add any rule the register missed.

### D1 Sign-in (`SESSION: build-auth`)

A migration for the identity changes, then the `api.auth_*` routines, `security/` (the
device token and its digest), the use cases, the routes, mail (the code email holds the
code, the purpose and the device name, nothing else) and the fakes, for B1, B2's
number-first entry, B4 to B8 and the forced-reset part of B3.

Evidence:
- one test per rule that fails without it;
- `tests/api/test_auth_contract.py` extended so that the refusals the design keeps
  uniform stay byte-for-byte identical, the new step included;
- `tests/api/test_contract_released_clients.py` rows proving that a v2.11 request (number
  and PIN together, trust by `deviceId`) still signs in;
- concurrency tests for the lock (two wrong PINs at once both count) and for a code
  voided while a new one is issued.

### D2 People and access (`SESSION: build-access`)

- The rights catalogue and its migration of grants (B13, the keys of B17).
- The people sign-in actions:
  - "make [name] reset the PIN", which removes their devices and forces a new PIN at the
    next sign-in;
  - remove one device, remove all.

  They act at once and are logged (B3).
- The people statuses: Active, Not signed in yet, PIN reset due, Locked, Blocked.
- The "can change" summary (B8, B13).
- The back-dating limit (B12):
  - the setting on the person, logged with access changes;
  - the earliest-writable helper;
  - the new-person default of seven days.

  Evidence: anti-escalation tests for the new right (a person cannot grant it without
  holding it, cannot use it on themselves, and only an Owner acts on an Owner), and
  boundary tests for the limit (0 days, month ends, a fixed date later than the rolling
  limit, the organization time zone at midnight).

### D3 Setup (`SESSION: build-setup`)

- Target sets (B9). A set starts today or later. A started set is fixed. A future set is
  replaced or removed. A set equal to the one in force is refused. Each change is logged
  as "Target set, [registration]". The right is its own. A new vehicle's seven figures
  start today, and "edit vehicle" no longer carries targets. `setup.target_on` reads the
  set in force, and the vehicle list shows it with the next set.
- Fleet number (B10).
- Optional initial investment (B11).
- Main categories (B16). Categories may have none. "Counts as" and the built-in groups go,
  with their data moved as D0 decided.
- Savings and scheduled-expense rights on the scheduled-item routes of prompt 06 (B17),
  with the change-log wording of the notes.

Evidence: the visibility and tenancy tests of prompt 06 extended to every new route.

### D4 Revenue (`SESSION: build-revenue`)

- Low-day reasons (B14). A day below the threshold needs a reason. The threshold is an
  organization setting. A record holds an amount, an amount with a reason, or a reason
  alone. The "Below [threshold]" figure counts low days and no-revenue days. Filling an
  empty day and changing a saved one are separate rights.
- The gap (B15): signed, against the day targets of the days that count so far, with the
  amber band as a setting.
- The back-dating check on capture and change, on the record's date. An offline replay is
  checked against the limit at its capture time.
- Every figure computed in SQL. Offline replay keeps working for v2.11 phones.

## Invariants at the end

- Every rule of rows B1 to B17 (without the report parts) has its document section, its
  routine or code, and a test that fails without it.
- A v2.11 phone and today's web requests still work: every row of
  `tests/api/test_contract_released_clients.py` passes unchanged, apart from those the
  design changed on purpose, which are listed in the report.
- No refusal tells an unknown number from a known one beyond what D0 decided and recorded.
- Lint, types, all tests green; `db verify` exit 0; no TODO/FIXME; no plan or prompt
  identifiers.

## Verify (paste the outputs into the report)

```
cd apps/api-python
ruff check . && ruff format --check . && mypy
pytest <the test modules you touched> -q
pytest -n 3 -q -p no:cacheprovider > <scratchpad>/full.log 2>&1
xcode-api db migrate && xcode-api db routines && xcode-api db verify ; echo "exit=$?"
```

Run the touched modules while you work. At the end of each build session, run the full
suite once in the background, with its log in your scratchpad, and report passed, failed,
skipped and errors from the log. Before that run, drop `xcode_template` (you changed
migrations and routines), after checking that no other session's run uses the cluster
(`docs/09-testing.md` section 5).

## Challenge pass (before the report)

Apply `docs/14-verification.md` to your own work as if nobody, including you earlier in
this session, had reviewed it:
1. Steelman: list every deliverable bullet and invariant above as a claim. Give the code
   that carries it, or, in the design session, the document section and the notes
   section.
2. Falsify: for each claim, name the observation that would disprove it and look for it;
   grade the evidence (section 5). Identity, tenancy and security claims need grade A.
3. Run the five modes over these domains, and give every probe of section 4 for them a
   verdict:
   - D2 first: the stranger who locks a person out, enumeration through the number step,
     the code that is re-sent after three tries as a mail flood, and a stolen device
     token;
   - D1 (the new people actions across organizations and scopes);
   - D3 (target sets and the lock under concurrent writes);
   - D4 (released clients);
   - D5 (the back-dating limit at month ends and midnight in the organization time zone;
     target sets starting today);
   - D6;
   - D10 (tests as evidence) and D11 (documents).

   The design session argues the other side of each decision it took.
4. Try to refute each finding; fix the survivors with a test that fails first (build) or a
   corrected document (design), or record them (open question, residual risk).
5. Report the findings table (section 7), the conceded challenges with the guard that
   defeated each, and the three hardest attacks for any domain without findings.

This pass does not replace the separate `verify.md` run; it makes that run cheaper.

## Report format

1. Design session:
   - every rule id with its notes section and the .NET behaviour it replaces;
   - every document section written;
   - the decisions on the two attacks of D0 and their residual risks;
   - the open questions added;
   - the design register as you left it.
2. Build sessions: checklist, one row per deliverable and per bullet: done or not,
   `file:symbol`, test name; verify outputs, trimmed.
3. Deviations from the documents with reasons; document lines changed.
4. The challenge-pass results.
5. Items left for later prompts (08, 08b, 10).

## House rules

- Shared tree: `git status` first; edit only under `apps/api-python/`; never revert or
  reformat others' changes; never kill processes you did not start; never bare `git stash`.
- No commits unless the user asks. No AI attribution anywhere.
- No comments unless needed; routine files carry the header the conventions require and
  nothing decorative; no plan or prompt identifiers anywhere.
- Never weaken a test to make it pass. If a document is wrong, fix the document and report
  it.
