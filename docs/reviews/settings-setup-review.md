# Settings and setup — detailed review

Scope: organization settings, personal preferences, people and access, PSV companies, vehicles,
recurring costs and savings, and the change log, across the API (`apps/api`) and web
(`apps/web`). Reviewed on `settings` on 2026-09-26, after the PR #3 Codex fixes
(`pr-3-codex-review.md`). S1 and S2 were then fixed here. Everything else is findings only.

A parallel session redesigned the web pages while this was written. The web findings were
re-checked against its final code (see "Re-check after the web redesign"). Line numbers in the
details below come from the first read and may have moved, so function and file names are the
stable reference.

Status key: **Open** · **Fixed** · **Partly fixed** · **Question** (needs a product decision
before fixing). "(parallel session)" marks changes made by the redesign. Its code was re-read
and the web tests re-run here.

## Summary

| # | Sev | Area | Finding | Status |
|---|-----|------|---------|--------|
| S1 | P1 | API / access | A `people.manage` holder can deactivate or sign out an **Owner** | Fixed |
| S2 | P1 | API / access | Changing someone's email and mobile lets a `people.manage` holder take over their account | Fixed |
| S3 | P1 | Web / setup | Every list loads only its first 25 rows (people, companies, vehicles, recurring, history) | Partly fixed (parallel session): 100 rows, no paging |
| S4 | P1 | Web / setup | Validation messages are hidden: users see "Invalid setup change" instead of the reason | Fixed (parallel session) |
| S5 | P1 | Web / setup | The required change reason is hardcoded, so the change log is boilerplate | Partly fixed (parallel session): setup reasons name the record, settings reasons name the section; nobody types a reason |
| S6 | P2 | Settings | Locale, currency, branding and personal preferences are saved but never applied | Open (re-checked: `lib/format.ts` hardcodes `en-GB`/`KES` and the browser's time zone) |
| S7 | P2 | Settings | The security section offers switches that do nothing (`Allow PIN sign-in`, password rules) | Fixed (parallel session) |
| S8 | P2 | Web / preferences | Overrides the organization disallows are still offered, and "12-hour time" can't go back to the default | Open (re-checked) |
| S9 | P2 | API / access | Role permissions have two sources: enforcement reads the DB, the UI and overrides read the catalog | Open |
| S10 | P2 | Access | A scoped admin can't save anyone whose scope reaches beyond their own | Open (re-checked) |
| S11 | P2 | Recurring | Items shared with out-of-scope vehicles look editable, show a partial total, and fail with 403 on save | Open (re-checked) |
| S12 | P2 | API / recurring | The recurring list pages by GUID, so each page is an arbitrary subset | Open; only bites above 100 items now that lists load 100 |
| S13 | P2 | Change log | No entity, actor or before/after; access changes aren't in it at all | Partly fixed (parallel session): shows who and when, and reasons name the record; still no before/after or access changes |
| S14 | P2 | Web / people | View-only users see Add, Edit, Deactivate and Sign-out buttons that all return 403 | Fixed (parallel session) |
| S15 | P2 | Vehicles | Vehicles can't leave the fleet; recurring shares keep posting to them | Question |
| S16 | P3 | API / settings | Settings history stores the raw request as "after", and no-op saves create versions | Open |
| S17 | P3 | API / setup | Every setup write bumps one org-wide version, so unrelated concurrent edits conflict | Open |
| S18 | P3 | API / setup | All reads run in serializable transactions; `GET access/roles` writes; deadlocks surface as 500 | Open |
| S19 | P3 | Web / proxy | The setup proxy allowlist likely can be sidestepped with encoded `..` segments (not tried) | Open (re-checked) |
| S20 | P3 | Recurring | New items and pending edits can be backdated without limit | Question |
| S21 | P3 | Settings | A lockout threshold of 1 lets anyone lock a user out for up to a day with one wrong PIN | Question |
| S22 | P3 | Web | Small correctness issues | Partly fixed (parallel session): see S22 |

---

## P1

### S1. Owners can be deactivated by anyone with `people.manage`
`apps/api/Application/AccessUseCases.cs:139-168` (`SetActive`, `SignOut`)

`Save` refuses to assign or edit an Owner unless the actor is an Owner (lines 70-74).
`SetActive` and `SignOut` don't check this at all. An Office admin has `people.manage` and, when
provisioned, all-company scope, so an Owner is visible to them. They can deactivate every Owner.
That bumps `SecurityVersion`, revokes sessions and locks the Owners out of the organization. No
test covers it (the only deactivate test runs as the Owner).

**Fixed:** `Save`, `SetActive` and `SignOut` now share one `EnsureMayManage` check, so only an
Owner can act on an Owner. Covered by
`AccessLifecycleTests.OnlyOwnersCanDeactivateOrSignOutAnOwner`.

### S2. Identity changes allow account takeover
`apps/api/Application/AccessUseCases.cs:112-116`; codes are sent to `user.Email`
(`AuthService.cs:56`)

`Save` lets a `people.manage` holder rewrite a person's email and mobile number. PIN-reset and
new-device codes go to that email. So the editor can point a colleague's account at their own
email and phone, run "Forgot PIN" and sign in as them. The Owner check stops this for Owners
only. Anyone else who holds more than the editor (for example `access.manage` or
`organization.manage` granted by override) is exposed, so this is a privilege escalation path.
The change also leaves the person's existing sessions and trusted devices in place.

**Fixed** in `AccessUseCases.Save`:
- Changing a person's email or mobile is allowed only for someone who could have granted them
  everything they hold: an Owner, or an editor whose own permissions plus the non-Owner role
  defaults cover all of the person's. A person with an approval limit also needs the editor to
  hold `access.manage`. This applies whether or not the person has set a PIN yet, because
  first-time setup codes also go to the email on file.
- When the change goes through, `SecurityVersion` is bumped and the person's trusted devices and
  refresh tokens are revoked, so their sessions end right away. The next sign-in verifies the
  device with a code sent to the email now on file. The PIN is kept.
- The change is audited as `person.sign_in_details_changed`, with the old and new email and
  mobile.

Covered by `AccessLifecycleTests.SignInDetailsOfSomeoneHoldingMoreThanTheEditorCanGrantNeedAnOwner`
and `ChangingSignInDetailsEndsSessionsButKeepsThePin`.

**Deliberately not changed:** a rule that you can't manage anyone holding a permission you lack.
Roles aren't nested (an Office admin lacks the Fleet manager's and Revenue clerk's capture and
float permissions), so that rule would stop Office admins from managing the people they
onboard. The remaining known gap is by design (#9): a `people.manage` holder can create a
second account for themselves with any non-Owner role, and role assignment ignores the editor's
own deny overrides. Closing that means deciding which roles each role may assign.

### S3. Only the first page of every list is ever loaded
`CompaniesPage.tsx:26`, `VehiclesPage.tsx:27-28`, `RecurringPage.tsx:26`, `HistoryPage.tsx:14`,
`PeopleAccessView.tsx:27`

Every list endpoint pages at 25 by default. No page requests more, and none offers paging. A
fleet with 30 vehicles shows 25, and the count ("25 vehicles", "25 people in your scope") is
wrong. The vehicle editor's company dropdown lists only the first 25 companies. Client-side
filters and sorting run on that partial set.

**Fix:** add paging (or "load more") to each table. Option lists (companies for the vehicle
editor) should come from an unpaged options endpoint, like `recurring/vehicle-options` and
`access/scope-options` already do.

### S4. Users never see why a change was rejected
`apps/web/components/requestSetup.ts:6`; `apps/api/Api/SetupEndpoints.cs:30`

The setup error filter maps `ArgumentException` to a ProblemDetails with
`title: "Invalid setup change"` and the real message in `detail`. `requestSetup` shows
`body.title || body.detail`, so the title always wins. Messages like "This registration already
exists.", "Use the registration format KDA 482M." or "Vehicle shares must equal the total
exactly." never reach the user. Also, a non-JSON error body (a proxy 502 page) makes
`response.json()` throw a SyntaxError that is shown as the message.

**Fix:** prefer `detail`, then `title`, and parse JSON defensively. Add a web test that a 400
shows the API's detail.

### S5. The required reason is always boilerplate
`CompaniesPage.tsx:44,79`, `VehiclesPage.tsx:199-200` (no input is rendered for
`form.reason`), `RecurringEditor.tsx:288,315`, `OrganizationSettingsView.tsx:82`

The API requires a reason for every setup and settings change (#24 made sure it's stored). The
UI never asks for one. It sends "Updated vehicle", "Updated organization settings" and so on, so
the change log records nothing a reviewer can use.

**Fix:** a reason field in each save and stop flow (a short prompt or dialog is enough), with
Save disabled until it's filled. Keep the 1–500 limit client-side too.

---

## P2

### S6. Most settings have no visible effect
`OrganizationEndpoints.cs:19-31`; `recurringPresentation.ts:34`, `RecurringEditor.tsx:50`,
`ui.tsx:99`

Nothing in the web app reads effective settings. Dates are formatted as `en-GB`, money as `KES`,
and the theme, font scale and reduced motion are never applied. Organization locale, time zone,
currency, date pattern and branding can be edited, and so can every personal preference, but
changing them changes nothing on screen. Only `organization.manage` can read the effective
settings (the settings GET), so ordinary members have no way to get them.

**Fix:** expose effective settings to every active member (in `/auth/session`, or a
`GET /setup/effective-settings`), put them in a context near `AppShell`, and route all date,
number and money formatting through it. Apply theme, font scale and reduced motion at the root.
Until then, consider hiding the sections that do nothing.

### S7. Security switches that don't do anything
`OrganizationSettingsView.tsx:266-281`

The pass-1 follow-up already listed `AllowPinSignIn`, password length, complexity and history as
not enforced. They are still on screen. "Allow PIN sign-in" is the risky one: turning it off
looks like it disables PIN sign-in, but nothing changes. The settings that *are* enforced now
(PIN length, lockout, refresh days) sit beside them with no distinction.

**Fix:** remove or hide the unenforced controls until a feature exists behind them.
`AccessTokenMinutes` is enforced but has no input; add one or leave it out on purpose.

### S8. Preferences offer overrides the organization forbids
`PreferencesView.tsx:61-65, 90`; `Organization.cs:263-276`

`AllowTimeZoneOverride` defaults to **false**, yet the time-zone field is always shown. It saves,
and the resolver then ignores it. The same applies to locale, 12-hour time and theme when their
flags are off. The 12-hour checkbox saves `hour12 ?? false`, so after the first save it always
overrides the organization default, with no way back to "use default". Clearing the font scale
sends 0, which the API rejects with a generic "Invalid accessibility preferences".

**Fix:** have the GET return the `Allow*Override` flags (or the effective values) and hide or
disable fields the organization doesn't allow. Use a three-state control for 12-hour time
(default / on / off).

### S9. Two sources of truth for role permissions
Enforcement: `OrganizationRepository.cs:16-23` (DB `RolePermissions`). Display and overrides:
`AccessUseCases.cs:195-196, 276-288` (`PermissionCatalog.DefaultsFor`). Sync:
`UserProvisioning.EnsureRoles` (add-only).

The rows `EnsureRoles` writes only ever grow, and only when it runs (on a roles GET, a person
save, or provisioning). When the catalog changes:
- a permission removed from a role stays enforced from the DB, while the UI says it's gone
- a permission added to a role shows in the UI straight away, but isn't enforced until something
  calls `EnsureRoles`

Overrides are computed against the catalog, so they can disagree with what's enforced.
Separately, `EffectivePermissionResolver.Dependencies` (`Access.cs:58-65`) knows five
dependencies while the catalog's `Needs` defines many more. So a DB grant without its
prerequisite (for example `commitments.manage` without `commitments.view`) is enforced as-is.

**Fix:** pick one source. The simplest is enforcing `PermissionCatalog.DefaultsFor(role)` plus
overrides, and dropping or ignoring `RolePermissions`. Derive the resolver's dependencies from
the catalog's `Needs`.

### S10. Scoped admins can't save people who reach outside their scope
`PeopleAccessView.tsx:198` (`scopeChoices`); `AccessUseCases.cs:234-242` (`ValidateScope`)

A company-scoped admin sees anyone sharing at least one company with them. The editor only
renders checkboxes for the admin's own companies, but the person's other company ids stay in
the form and are sent on save. `ValidateScope` then rejects them, so any save of that person
fails with "Not permitted…". Nothing on screen explains why, and no change is possible (not even
a name fix).

**Fix:** decide the rule. Either keep out-of-scope assignments untouched on save (merge
server-side and validate only the in-scope delta), or list them read-only in the editor with an
explanation.

### S11. Partly-visible recurring items fail with 403 when saved
`SetupRepository.cs:20-22, 124-143`; `RecurringUseCases.cs:30-32`

A scoped user sees an item if any version allocates to any vehicle in their scope. The list
returns only the visible shares and sums them as the item's amount. So a shared cost of 30,000
split over three companies shows as 10,000 and looks editable. Saving is rejected, correctly,
because the full allocation must be in scope. The user just gets a bare 403.

**Fix:** add `partial: true` (or the full total with a "shared with other scopes" note) to
`RecurringDto`, and open such items read-only in the editor.

### S12. Recurring pages are random subsets
`SetupRepository.cs:115`

Items are paged `OrderBy(i => i.Id)` (a GUID), and the rows for the page come back in database
order. Once S3 adds paging, page 1 is an arbitrary 25 items, not the next ones due or A–Z.

**Fix:** order by a meaningful key (current version name, then id) before `Skip`/`Take`, and
keep that order in the returned rows.

### S13. The change log is thin, and access changes are missing
`SetupRepository.cs:173-186`; `HistoryPage.tsx:28-40`; `AccessUseCases.cs:320-330`

- Rows show section, reason and a raw ISO timestamp. There is no record name (only an
  `EntityId`), and the page doesn't show the actor even though `HistoryEntry` now carries
  `ActorName`.
- `HistoryEntry` no longer returns before/after, so "what changed" isn't shown anywhere.
- People and access changes (role, overrides, scope, approval limit, deactivation) are written
  only to `AuditEvents`. The person audit records just the role name, and no page reads
  `AuditEvents`. The most sensitive changes are the ones `audit.view` can't see.

**Fix:** record access changes as `OrganizationSettingsVersion` rows (section `people`) with
before/after snapshots, and audit the full delta. In the log, show actor, record name, local
time and a readable diff.

### S14. View-only people see management actions
`PeopleAccessView.tsx:94` and row actions

`people.view` is enough to open the page, but Add person, Edit, Deactivate and Sign-out are
shown to everyone and fail with 403 for view-only users. Deactivate and sign-out also run with
no confirmation step, and are offered on your own row, where the API refuses them.

**Fix:** pass `canManagePeople` like `canManageAccess`. Hide actions on your own row, and
confirm the destructive ones.

### S15. Vehicles can't leave the fleet — *Question*
`FleetVehicle.cs`; `SetupRepository.Report`

Vehicles have `JoinedOn` but no leave or retire date. Companies and vehicles can't be archived.
A sold vehicle keeps its recurring shares posting and stays in every picker.

**Question:** should a vehicle get a `LeftOn` date (which ends its targets and shares and hides
it from pickers), and should companies be archivable?

---

## P3

### S16. Settings history accuracy
`OrganizationEndpoints.cs:58-63`

`after` is `input.Value.GetRawText()`, the client's JSON, not what was saved. Omitted fields are
saved with their defaults but don't appear in the snapshot, and any extra fields the client sent
do. Saving with no changes still bumps the version and writes a history row. The setup use
cases already skip no-op saves.

**Fix:** serialize the saved entity for `after`, and skip the write when `before == after`.

### S17. One version counter for all setup writes
`SetupRepository.cs:197`; `OrganizationModel.cs:23`

Every company, vehicle, recurring and settings write increments `Organization.SettingsVersion`,
which is a concurrency token. Two people editing different vehicles at the same moment collide,
and one gets "Settings changed. Reload before saving." It's safe, but the message is misleading
and conflicts grow with the number of admins.

**Fix:** keep a separate history sequence (identity column, or a per-section counter), and put
concurrency tokens on the edited aggregates instead.

### S18. Serializable reads, and a GET that writes
`Infrastructure/Setup/SetupExecution.cs:12-18`; `UnitOfWork.Execute`;
`AccessUseCases.cs:16`

Reads go through the same serializable transaction and `SaveChanges` as writes. List queries
take range locks, so under concurrent writes SQL Server picks deadlock victims. The resulting
`SqlException` isn't a `DbUpdateException`, so it surfaces as a 500. `GET access/roles` calls
`EnsureRoles`, which inserts rows, so a read has side effects.

**Fix:** run reads without a transaction (or at read-committed snapshot). Move role seeding to
startup or provisioning. Consider EF's retrying execution strategy for writes.

### S19. Proxy path hardening
`apps/web/app/api/setup/[...path]/route.ts:45, 62`

The regex checks only the joined path, and each segment matches `[^/]+`, which includes `..`.
Route params arrive URL-decoded, so a request like `people/..%2F..%2Fauth%2F…` can pass the
regex and then have its `..` normalised away by `fetch`, reaching an API route outside `/setup`
with the user's bearer token. This wasn't tried at runtime. The API still authorizes every
route, so it isn't exploitable today, but the allowlist doesn't hold.

**Fix:** reject `.`/`..` segments and `encodeURIComponent` each segment when building the
upstream URL.

### S20. Unlimited backdating — *Question*
`RecurringItem.cs:36`; `RecurringUseCases.Save`

New items and not-yet-started edits can start any time in the past. Reports for closed weeks
then change without notice.

**Question:** should backdating be limited (for example to the current month, or to a locked
period once one exists)?

### S21. Lockout threshold can be 1 — *Question*
`Organization.cs:195`

With threshold 1 and 1440 minutes, one wrong PIN from anyone who knows a mobile number locks
that person out for a day.

**Question:** raise the minimum to 3 (and maybe cap the lockout at a few hours)?

### S22. Smaller web issues
Fixed by the redesign (parallel session): the duplicate list fetch in `AppShell`, the raw
`firstName`/`lastName`/`email` labels, Owner offered to non-Owners, and the settings banners
(errors are now per section).

Still open:
- `RecurringPage` and the vehicle editor take "today" from the browser's local date
  (`todayDateOnly`), while the server uses the organization's business date. They can disagree
  near midnight for users in other time zones.
- The API still returns generic messages for localization and security ("Invalid format
  settings", "Invalid security policy."), which don't say which field is wrong.
- Naming debt that reaches the schema: `UseGroupping`, `OccuredAt`; code-only:
  `CurrentOganizationId`, `organizationContext`. Renaming the columns needs a migration, so
  it's worth doing before production data exists.

Found in the re-check:
- After saving a vehicle, the editor reopens with a locally assembled copy
  (`VehiclesPage.tsx`, `onSaved`). Its "Target history" doesn't show the target just added
  until the vehicle is reopened.
- A vehicle manager without `companies.manage` only gets companies that already have vehicles
  (`companyChoices`), so they can't add the first vehicle to an empty company. Default roles
  aren't affected (Office admins have both permissions). A company-options endpoint under
  `vehicles.manage`, like `recurring/vehicle-options`, would fix it.
- "Add company" is shown to company-scoped editors, and the API always refuses it (only
  organization-wide editors can create companies).
- The weekly target hint says "a Monday to Sunday week" whatever the organization's first day
  of the week is.

---

## What's solid

- **Tenant isolation** is enforced twice: global query filters, plus a `SaveChanges` guard that
  rejects cross-organization writes and edits to the organization row.
- **History is append-only by construction.** Targets and recurring versions are never
  overwritten. `DueOn` picks the latest revision effective on a date, so reports stay
  reproducible.
- **Data scope is kept separate from permissions**, and writes check scope (vehicles for
  company-scoped editors, the full existing allocation for recurring edits).
- **Money** is validated to two decimal places and positive. Recurring shares must sum exactly.
- **Concurrency tokens** on the organization and memberships, with unique indexes on history
  versions, names and registrations. Conflicts come back as 409, not duplicates.
- **After pass 1**, the access rules for single permissions and approval limits are coherent,
  and the roles endpoint is the one place the UI gets role defaults.

## Re-check after the web redesign (2026-09-26)

The parallel session finished its redesign (new `components/ui/` library, `useSetupData` with
loading skeletons, session context). The web findings above were re-read against that final
code, and the statuses in the summary reflect it. Results, run in this session:

- **API:** 65 tests, 63 pass. The 2 failures are the known SQL Server environment tests. The 3
  new `AccessLifecycleTests` pass.
- **Web:** 37 of 37 tests pass. `tsc --noEmit` is clean.
- **Lint:** no web or shared problems. The 4 remaining errors are the old `no-require-imports`
  ones in `apps/mobile`.

## Suggested order

1. **S1, S2** (security; small API changes plus tests). Done.
2. **S4, S14, S7**: done in the redesign. **S3, S5, S13**: partly done. What's left is real
   paging, and deciding whether people type their own reasons.
3. **S10, S11** (scoped-admin experience).
4. **S6, S8** (decide whether to wire settings through now or hide the inert parts).
5. **S9**, the access half of **S13**, then the P3 items.

S15, S20 and S21 need a product decision first. So does which roles each role may assign (see
S2).
