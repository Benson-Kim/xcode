# Verify `prompt:07b` D0 (design notes v2.29–v2.33) — fix mode

Date 2026-10-11 (session `revenue-45`, Opus, coordinator from 21:45). Scope: the D0 design
documents of `docs/prompts/07b-design-v2-3.md` (documents only; D0 writes no code). Mode:
**fix** (user-requested; the prompt's own default is `report`). A design fix is a corrected
document. Depth: standard. This is a fresh-eyes run by a session that did not write the
design: the D0 report `docs/audit/2026-10-11-design-07b-d0.md` and its challenge pass are
*claims* re-verified here, not evidence.

## 1. Verdict

**pass with findings.**

Per severity: blockers 0; major 4 (all fixed in the documents); minor 3 (2 fixed/recorded,
1 note). Per verdict over the prompt's D0 deliverables and the register's claims: holds 7,
fails 7 (all corrected in the documents this session), unproven (by construction, a design
has no passing test until the build sessions) the rest, not checked: full .NET re-parity of
every register citation (one spot-checked; see §8), and the three code-sweep families
(`now()`/`EXECUTE`/`SECURITY DEFINER` in `db/routines`, `skip`/`xfail` in `tests/`) which are
n/a to a documents-only scope (D0 adds no `db/` or `tests/` file).

No full suite was run: the scope changes only documents, and a shared full run (queue row 1)
holds a freeze on `src/`, `db/`, `tests/`.

## 2. Thesis and claims

Thesis: *prompt 07b D0 specifies rows B1–B17 (minus the 08/08b/10 parts) of the design
register across `docs/04,05,06,07,09,10,11,12,13,15`; its rules are internally consistent,
buildable, keep released clients working, and keep security at least as strong as today,
with the two notes-level attacks decided and recorded.*

| # | Claim | Where | Verdict | Grade |
|---|---|---|---|---|
| C1 | Every rule has an id, a notes section, a .NET location | `docs/15` §1 | holds (92 ids, counts in §3 reconcile; one .NET citation spot-checked accurate) | C→B |
| C2 | `docs/07` covers the ten auth items of the prompt | `docs/07` 12.1–12.14 | holds | B |
| C3 | `docs/04` §13 covers the nine table areas with constraints, RLS, grants, indexes | `docs/04` 13.1–13.5 | holds | B |
| C4 | One earliest-writable helper, month-clamp correct | `docs/05` 10.2 | holds (PostgreSQL clamps `2026-03-31 − 1 month → 2026-02-28`, leap `2024-02-29`) | B |
| C5 | Routes, bodies, messages, "new in Python" notes complete | `docs/06` 2.12, 4 | holds (N01–N09, S45–S52, S11; 18 planned codes, 3 changes, 2 retirements; none in built §3) | B |
| C6 | 59 rights reconciled, named, role defaults, migration copies | `docs/15` §3, `docs/11` §5 | holds (59 = 40 new + 19 existing; 48 deps; 32 sources; 80 perms; 60+37+11+3=111 role rows) | B |
| C7 | Released clients keep working, deliberate changes listed | `docs/15` §4 | holds (fleet number, low days, today's record by capture-only, S11 wording) | B |
| C8 | Two attacks decided; security ≥ today | `docs/07` 12.14, `docs/12` 2.7/7 | **fails → fixed** (recovery gap V-07b-1; residual distinguisher V-07b-2) | B |
| C9 | The identity routines are concurrency- and trust-safe as specified | `docs/05` 10.1, `docs/07` 12.5/12.8 | **fails → fixed** (deadlock D1-F1; double-count D1-F2; null-token trust D1-F3) | A |

## 3. Findings (all surviving; blockers first — none)

Ordered major, then minor. "Fixed" = corrected in the documents this session; the build
session named owns the code and the failing-first test.

| id | sev | class | where | vector | expected / actual | synthesis |
|---|---|---|---|---|---|---|
| V-07b-1 | major | availability / recovery | `docs/07` 12.5; `docs/05` 10.1 `api.ops_clear_pause` | a has-PIN person with no live trusted device (trust expired at 90 days, or always unticked) whose untrusted scope a stranger locks with five wrong PINs; email unreachable (q53) | the DN-B4-2 operator escape hatch should recover an untrusted-only lock / `clear-pause` cleared only the trusted scope, so no recovery existed | **fixed**: `clear-pause` clears **both** scopes (`docs/07` 12.5, `docs/05` 10.1, `docs/15` DN-B4-2, `docs/09` 4.1 row 157, `docs/12` 2.7 & 7). Safe: audited `xcode_operator` action, no attacker benefit. Owner may revisit (q47) |
| D1-F1 | major | concurrency | `docs/05` 10.1, `docs/07` 12.11 | an admin `save_person`/block of P (`membership FOR UPDATE → user`) races P's logged sign-in event (`user → change_log FOR KEY SHARE on membership` via `fk_change_log_actor`) | no deadlock / 40P01 deadlock (503) | **fixed**: lock-order invariant in `docs/05` 10.1 — people routines take membership `FOR NO KEY UPDATE` (does not conflict with `FOR KEY SHARE`, still serialises writers, still blocks `FOR UPDATE`). D1 builds the two-connection test |
| D1-F2 | major | enumeration | `docs/05` 10.1 `identity.unknown_pin_tries` | N02 on an unknown number: `auth_account_lookup` writes a `sign_in` row *and* `auth_pin` a `pin` row; the helper counted both | unknown steps like a real one (4,3,2,1) / stepped 3,1,locked — a distinguisher (opposite of DEC-2) | **fixed**: the helper counts only the lookup's `sign_in` attempt row (one per A01/A02/N02); the `pin` row is the trail. `docs/09` 4.1 row 145 already pins the 4,3,2,1 countdown |
| D1-F3 | major | trust / auth | `docs/05` 10.1 `identity.device_trusted`; `docs/07` 12.8 | a new-route call omitting `deviceToken` passes `p_token_hash` null → the legacy "no token → trust by `deviceId`" branch | a leaked `deviceId` must not buy PIN-only trust on a new route (DEC-5) / it did | **fixed**: new routines pass `coalesce(hash,'')`; null is reserved for the old routes (`docs/05` 10.1, `docs/07` 12.8); added `docs/09` 4.1 test `test_a_new_route_with_no_token_does_not_trust_a_legacy_row_by_device_id` |
| V-07b-2 | minor | enumeration (residual) | `docs/07` 12.14 a | lock a set of numbers at the PIN step, re-probe over days; a real account's untrusted scope resets on a verified new device / PIN change and re-opens to `pin_required`; an unknown's simulated lock never clears | "an account with a PIN cannot be told from an unknown number" / holds only short-term | **recorded** as a residual risk (`docs/07` 12.14 a, `docs/12` §7); reveals only existence; cannot be closed without an owner to mimic resets. Owner: product |
| V-07b-3 | minor | migration robustness | `docs/05` 10.4 `setup.split_week`; `docs/10` 3.1; `docs/04` 13.4 | a legacy weekly target with `weekly − 6·round(weekly/7,2) ≤ 0` (e.g. 0.06, or a 0/unset target) | the seven split cents each `> 0` / Sunday becomes 0.00 or negative and the `> 0` CHECK aborts the load | **recorded + doc note** (`docs/10` 3.1): the B20 migration flags such vehicles for owner entry instead of aborting. Owner: prompt 10 / D3 |
| V-07b-4 | minor | test coverage (D10) | `docs/09` 4.1 | — | every register rule has a dedicated pinning row / DN-B1-2 (trusted device → PIN step, no name before trust) and DN-B1-7 (N02 `new_device` `maskedEmail`; resend/back wire facts) have none | **note**: adjacent tests cover them partly; D1 should add explicit rows |

## 4. Per domain

**D1 Sign-in** — probes: enumeration byte-equality (holds, with V-07b-2 residual + D1-F2
fixed); lock concurrency (holds after D1-F1 fix; `identity.lock_user` serialises, two-at-once
both count); device trust (holds after D1-F3 fix); code caps/flood (holds; replacement exempt
from the minute, counts to hour/day; resend only after a right PIN); mail content (holds,
q62). Recovery (holds after V-07b-1 fix). Timing: one derivation per PIN step for everyone
(dummy hash), mail after the reply — uniform.

**D2 People/access** — rights count (holds, all tallies reconcile); anti-escalation for
`people.sign_in` on S45/S46/S11 (`check_person_grant`, `people_self_sign_in`,
`people_owner_edit` — holds); legacy/hidden keys never granted, derived for v2.11 (holds);
back-dating limit read after permission, before version (holds — a 403 never leaks the
limit). Hardest attacks that failed: grant `people.sign_in` without holding it (refused);
use it on self (refused); a scoped viewer removing a device of a person not in view (XC404).

**D3 Setup** — target sets: started set immutable, future set replaceable/removable, equal
set refused, two saves serialised by the vehicle lock (holds); fleet number required on
S18/S19 only, retire/restore exempt (holds, V-D11-1); investment optional/stored null
(holds); main categories regroup via item→category→main pointer (holds). V-07b-3 is the one
migration-robustness gap.

**D4 Revenue** — low-day reason rule, `revenue.gap_band` edges (`−gap ≤ target·amber%/100`),
`below_threshold_days` counts reason-only and below-threshold records but not missing days
(holds); `expected` = day target, no /7 (holds); back-dating 72h clamp
`greatest(least(capturedAt,now),now−72h)` (holds, DEC-12); identical replay precedes every
check (holds).

**D5 Calendar** — month-back clamp correct (C4); limit turns at midnight in the org zone via
`business_date`; target set "starts today" uses the same business date. No findings. Hardest:
one month from 31 March in a leap vs non-leap year (clamps to 29/28 Feb); 00:01 vs 23:59
Africa/Nairobi; a held business date (limit counts from it).

**D6 Database craft** — V-D6-1 (migration computes old grant sets with its own query, never a
routine) re-verified present (`docs/04` 13.2). Indexes: the unknown-number partial index, the
fleet-number unique index, the target-set start-date index all named per query. D1-F1 is the
one concurrency gap (fixed).

**D10 Tests** — 4.1 has one-or-more failing-first rows per rule at the owning layer; row 145
already catches D1-F2, row 157 updated for V-07b-1, DEC-5 row updated for D1-F3. Gap: V-07b-4.

**D11 Documents** — route/message/count cross-references all reconcile; the planned message
codes stay out of the built §3 catalogue (test_messages 372 passed per the board); the
§1–11 vs §12 (and §2.1 vs §2.7) "current vs target" convention is internally consistent.

## 5. Per mode (strongest surviving challenges)

- **Assumptions inventory**: (a) "an unknown number is indistinguishable from a real one"
  (false long-term → V-07b-2); (b) "the two lock scopes keep the owner working" (assumes a
  live trusted device → V-07b-1); (c) "null `p_token_hash` means the old route" (false for a
  new route with no token → D1-F3); (d) "each identity routine locks only the user row"
  (the change-log FK also locks the membership → D1-F1); (e) "a weekly target always splits
  into seven positive cents" (false near zero → V-07b-3).
- **Falsification (graded)**: D1-F2 grade A (byte-level, reproducible from the row-count
  logic); D1-F3 grade A (trust bypass from a known `deviceId`); D1-F1 grade A (deterministic
  deadlock); V-07b-1 grade B (reachable, needs no-trusted-device + no-email); V-07b-2 grade C
  (slow, owner-activity dependent).
- **Pre-mortem**: "D1 ships and the first week shows intermittent 503s on people edits" →
  D1-F1 deadlock. "Support cannot unlock a crew member with a shared office email" → V-07b-1.
  "A pentester reports the number step leaks account existence" → V-07b-2 (already partly
  recorded). Inversion: if clear-pause already cleared both, V-07b-1 would not arise — it is
  an incidental carry-over from the current untrusted *cap*, not a deliberate choice.
- **Red-team vectors (own machine only)**: stranger-lockout (V-07b-1, DEC-1 residual);
  enumeration sweep (V-07b-2, D1-F2); stolen/leaked `deviceId` on a new route (D1-F3);
  mail-flood (held by caps + resend-after-PIN); stolen device token (held — needs the PIN,
  five wrong lock, stored only as SHA-256).
- **Dialectic**: DEC-1 two scopes — kept, but the clear-pause asymmetry it inherited is the
  bug (V-07b-1). DEC-2 simulated unknowns — kept; the simulation's non-resetting lock is the
  residual (V-07b-2). DEC-5 token-vs-legacy — kept; needs the non-null sentinel to hold on
  new routes (D1-F3).

## 6. Conceded challenges (the guard that held)

- "Six-digit PIN holder on the new web locks themselves on every device" — no: a new web
  device is untrusted until a first success, so its wrong PINs are the untrusted scope; the
  phone keeps working (DEC-1/DEC-7).
- "Right PIN on a trusted device resets the stranger's untrusted guesses" — no:
  `untrusted_failed_attempts` is never cleared by a trusted-device success (`docs/07` 12.5),
  defeating the "four guesses per owner sign-in" attack.
- "Every-device lock bypassable via the new-device code path" — no: the locked-device check
  (12.3 step 5) precedes the right-PIN-untrusted path (step 7).
- "Back-dating limit leaks through a 403 ordering" — no: checked after the permission
  (`docs/05` 10.2).
- "A migration calls the new resolver mid-swap" — no: it uses its own query (V-D6-1,
  `docs/04` 13.2).
- "`below_threshold` counts missing days" — no: it requires a record ("whose record has no
  amount or an amount below the threshold").

## 7. Fixes (files changed)

| id | files | the assertion that now holds |
|---|---|---|
| V-07b-1 | `docs/07` 12.5; `docs/05` 10.1; `docs/15` DN-B4-2; `docs/09` 4.1 row 157; `docs/12` 2.7 & §7 | `api.ops_clear_pause` clears both counters; an untrusted-only lock with no live trusted device recovers through it |
| D1-F1 | `docs/05` 10.1 (lock-order note) | people routines lock membership `FOR NO KEY UPDATE`; no deadlock with the sign-in path's `FOR KEY SHARE` |
| D1-F2 | `docs/05` 10.1 (`identity.unknown_pin_tries`) | one try counts once; N02 no longer double-counts |
| D1-F3 | `docs/05` 10.1 (`identity.device_trusted`); `docs/07` 12.8; `docs/09` 4.1 (DEC-5 row) | a new route with no `deviceToken` is not trusted by `deviceId` on a legacy row |
| V-07b-2 | `docs/07` 12.14 a; `docs/12` §7 | the long-term real-vs-unknown distinguisher is recorded |
| V-07b-3 | `docs/10` 3.1 | the split-week migration flags unsplittable targets instead of aborting |

All edits are confined to the 07b design sections (not the current §1–11 / §2.1 material),
so they do not touch the `src/`/`db/`/`tests/` freeze or another session's held doc sections.

## 8. Commands and outputs

- Session start `date +%H:%M` 21:44 EAST (board clocks ran ~1h ahead; corrected on the
  board). `git status --short`: the pre-existing `fix/web-dropdowns` working set (unrelated
  .NET/web changes); of my scope, only `docs/*` under `apps/api-python/` edited this session.
- `ListAgents`: peers revenue-6b (verify-05), revenue-e2 (verify-04, done), revenue-c2
  (verify-03, running shared run 1), revenue-17 (D1 build-auth). Shared run 1 (template
  `xcode_template_v03e`) in progress; freeze on `src/`/`db/`/`tests/` until its "ended" cell.
- .NET parity spot-check: `SignInService.cs:9` = `UntrustedAttemptLimit = 10`, `:35–42` the
  pause via `policy.LockoutMinutes` and `RecordUntrustedFailedAttempt` — matches the register
  (D0 report's re-measured `:9`/`:33–41`). **Not checked**: the remaining ~90 .NET citations
  were taken from the register (measured by the D0 session on 2026-10-11), not re-opened here.
- No pytest / ruff / mypy / `db verify` run: documents-only scope under the full-run freeze.

Versions measured: PostgreSQL 16 (dev cluster, per `docs/09` §5; not queried this session, no
DB work). No code executed.

## 9. Regressions and misses vs the D0 report

The D0 report's nine challenge-pass findings (V-D1-1 counts, V-D2-1 device-name filter,
V-D2-2 `maskedEmail`, V-D3-1 `weeklyTarget`, V-D4-1 below-threshold, V-D6-1 migration
resolver, V-D10-1 permission-keys test, V-D11-1 fleet-required, V-D5-1 no trigger) were each
re-verified and **hold** in the current documents. No regression.

Misses by the D0 challenge pass, found here: V-07b-1 (clear-pause recovery gap), V-07b-2
(unknown-number non-resetting distinguisher), V-07b-3 (split-week robustness), V-07b-4 (two
missing test rows) — plus the three D1 findings (deadlock, double-count, null-token trust),
which the D0 pass also did not surface. The D0 pass's §6.4 argued the other side of DEC-1 but
did not reach the clear-pause asymmetry, and its D1 probes did not model the change-log FK
lock or the new-route null token.

## 10. For the user

- **V-07b-1 (decided here, you may overrule under question 47):** I changed the design so the
  operator's `clear-pause` clears **both** lock scopes, not just the trusted one. Reason: the
  design already provides `clear-pause` as the only recovery for a person whose email is not
  on their phone (question 53), but the untrusted-scope lock could brick exactly such a person
  (when they have no live trusted device), and the exclusion was an incidental carry-over from
  the current model's untrusted *cap*. The change is safe (an audited `xcode_operator` CLI
  action an attacker cannot invoke). If you prefer the literal single-lock model (question 47),
  this becomes moot.
- **V-07b-2 (product):** the v2.33 number step separates a real account from an unknown number
  slowly over time (recorded, not closable without an owner to mimic resets). Accept, or narrow
  what the number step reveals.
- **V-07b-3 (product/ops, prompt 10):** decide the floor for a day target — the design requires
  each of the seven `> 0`, so a vehicle with no real target cannot be migrated automatically
  and is flagged for entry.
