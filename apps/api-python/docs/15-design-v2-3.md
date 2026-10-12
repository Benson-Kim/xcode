# The design notes v2.29 to v2.33, built ahead of .NET

The product rules of `docs/design/XCODE_Build_Notes_v2.3.md` (repository root; cited as
`v2.33 s1` for version 2.33 section 1) that change the API, with the prototype
`docs/design/XCODE_Web_v2.3.html` for layout and behaviour. The owner decided on
2026-10-11 that Python builds them before .NET has them (`docs/13-open-questions.md`
question 46), so for these rows the notes decide behaviour, not the .NET code. Released
clients still hold (question 54): a v2.11 phone and today's web requests keep getting
answers they understand.

This document is the register: one id per rule, the notes section, the .NET behaviour it
replaces (`apps/api/`, measured on 2026-10-11 in the working tree of `fix/web-dropdowns`),
the document section that specifies it, and the build session of
`docs/prompts/07b-design-v2-3.md` that builds it (D1 sign-in, D2 people and access, D3
setup, D4 revenue; 08, 08b and 10 for the parts they own). The specifications live in the
usual documents:

| Topic | Where |
|---|---|
| Sign-in model, PIN rules, lock, codes, devices, history, threats | `docs/07-auth.md` section 12 |
| Tables and columns | `docs/04-schema.md` section 13 |
| Helpers and routines, check orders, statement budgets | `docs/05-routines.md` section 10 |
| Routes, bodies, messages, client facts | `docs/06-http-contract.md` sections 2.12 (messages in 2.12.5, moved into section 3 by the session that builds each code) and 4 (last bullets) |
| The rights catalogue | section 3 below; naming in `docs/11-naming.md` section 5 |
| Security decisions and residual risks | `docs/12-security.md` sections 2.7 and 7 |
| Tests | `docs/09-testing.md` section 4.1 |
| Data changes | `docs/10-data-migration.md` section 3.1 |
| Owner questions | `docs/13-open-questions.md` 47 and 59 to 66 |

Section 4 of v2.33 lists review aids that are not built: the prototype opening signed in,
the dashed box of people, PINs and codes on the sign-in screen, and "Viewing as".

## 1. Rule register

Status words: **new** (no .NET behaviour), **replaces** (the .NET behaviour named is
retired for this rule), **built** (Python already does it; kept and pinned), **client**
(the screen does it; the API only has to allow it).

### B1 Number-first sign-in (v2.33 s1)

| Id | Rule | .NET today | Spec | Build |
|---|---|---|---|---|
| DN-B1-1 | The mobile number comes first, alone; the server decides the next step: PIN, a code (first sign-in, forced reset) or blocked | replaces: number and PIN in one request (`Api/AuthEndpoints.cs:28-31`, `Application/AuthContracts.cs:19-26`, `Application/Authentication/SignInService.cs:13`) | `docs/07` 12.2; `docs/06` N01 | D1 |
| DN-B1-2 | A trusted device remembers its person and starts at the PIN step | replaces: trust keyed by the client's `deviceId` (`Domain/Entities.cs:83-99`, `Application/Authentication/AuthAccounts.cs:30`) | `docs/07` 12.8 | D1 |
| DN-B1-3 | On a device that is not trusted, nothing before trust names the person | built: no `/auth` answer carries a name; kept for the new routes | `docs/06` 2.12 | D1 |
| DN-B1-4 | A blocked person is refused at the number step | replaces: a blocked (removed) person gets the uniform 401 only after a PIN (`SignInService.cs:13`, `AccessUseCases.cs:232-242`) | `docs/07` 12.2 | D1 |
| DN-B1-5 | An unknown number gets the same wording and timing as a wrong PIN where possible; tries are limited per device and per address | replaces: uniform 401 after a PIN and the per-address limiter; no per-device limit | `docs/07` 12.2, 12.14; `docs/12` 2.7 | D1 |
| DN-B1-6 | The PIN field submits on the fourth digit, the code field on the sixth, Enter submits; no helper text | client | `docs/06` 4 | web |
| DN-B1-7 | The code step shows the email with the middle hidden, "Send a new code" and "Back" | replaces: `maskedEmail` only on a new-device challenge; resend by repeating the sign-in with the PIN | `docs/06` N01, N04 | D1 |
| DN-B1-8 | Ask for the PIN again after 15 minutes without activity; typed work is kept | replaces: `IdleUnlockSeconds` 300, not served to clients (`Domain/Organization.cs:291`, `Application/Settings/OrganizationSettingsUseCases.cs:74-93`) | `docs/07` 12.1; `docs/06` 2.12 (appearance) | D1 |

### B2 First sign-in (v2.33 s1)

| Id | Rule | .NET today | Spec | Build |
|---|---|---|---|---|
| DN-B2-1 | A new person is created with no PIN; there is no default `0000` | built in .NET and Python (no PIN at create) | `docs/07` 12.6 | kept |
| DN-B2-2 | First sign-in: number, code, choose a PIN, repeat it | replaces: the setup-pin routes without a number step (A04 to A06) | `docs/07` 12.2, 12.6 | D1 |
| DN-B2-3 | "Email for codes" is required and unique | built (`people_email_invalid`, unique `identity.users.email`) | `docs/04` 3.1 | kept |
| DN-B2-4 | Saving a new person says they set a PIN at first sign-in | client | | web |

### B3 Forced reset, people sign-in actions, statuses (v2.33 s1, s3)

| Id | Rule | .NET today | Spec | Build |
|---|---|---|---|---|
| DN-B3-1 | Forced reset: like a forgotten PIN; the number step goes straight to the code; only a new PIN ends it | new | `docs/07` 12.7 | D1 |
| DN-B3-2 | Right `ppl.signin` ("Reset a PIN and remove devices"). "Make [name] reset the PIN" removes their devices and forces a new PIN at the next sign-in; it acts at once and is logged | new; the only related action is "sign out of every device" under `people.manage` (`Application/AccessUseCases.cs:249-260`, `:581-587`) | `docs/06` S45; `docs/05` 10.3 | D2 |
| DN-B3-3 | Remove one trusted device, or all of them, at once, logged | replaces: all only (`AccessUseCases.cs:581-587`) | `docs/06` S11, S46 | D2 |
| DN-B3-4 | People status: Active, Not signed in yet, PIN reset due, Locked, Blocked | replaces: `active` and `hasPin` (`Application/AccessContracts.cs:15-18`) and the filter `active`, `waiting`, `none` (`AccessUseCases.cs:68-82`) | `docs/06` S05, S06 | D2 |
| DN-B3-5 | The person's "Sign in" pane: PIN status, last sign-in, where codes go, trusted devices | new | `docs/06` S06 | D2 |

### B4 The lock after five wrong PINs (v2.33 s1)

| Id | Rule | .NET today | Spec | Build |
|---|---|---|---|---|
| DN-B4-1 | Five wrong PINs in a row, counted per person across devices, lock the PIN until a reset with a code; a correct PIN resets the count. Decided here: two scopes (a lock reached from trusted devices holds on every device; one reached from untrusted devices holds on every untrusted device) | replaces: a timed pause on trusted devices (`SignInService.cs:33-41`, policy threshold 3..10 and minutes 1..60, `Domain/Organization.cs:287-288`) and an untrusted cap of 10 (`SignInService.cs:9`, `:28-29`, `:42`) | `docs/07` 12.5, 12.14; `docs/12` 2.7 | D1 |
| DN-B4-2 | Only a reset with a code unlocks; the operator's `clear-pause` clears both scopes (a person without email on the phone has no other way back, question 53; it is also the only lever for a new-devices lock on a person with no live trusted device) | replaces: the pause lapses after `LockoutMinutes` | `docs/07` 12.5 | D1 |
| DN-B4-3 | The lock is written to the change log: "PIN locked after 5 wrong tries" | new | `docs/07` 12.11 | D1 |

### B5 PIN rules (v2.33 s1)

| Id | Rule | .NET today | Spec | Build |
|---|---|---|---|---|
| DN-B5-1 | Every new PIN is exactly four digits | replaces: 4 to 8 digits with an organization minimum (`Application/AuthContracts.cs:39-51`, `Application/Authentication/PinSetupService.cs:27`, `:32-36`) | `docs/07` 12.4 | D1 |
| DN-B5-2 | Refused: one digit four times; a run up or down (1234, 4321); the last four digits of the person's own number; the PIN being replaced | replaces: the first two only (`AuthContracts.cs:47-50`) | `docs/07` 12.4 | D1 |
| DN-B5-3 | Stored hashed with a per-person salt; never returned by any API | built (PBKDF2 with a random salt, `docs/07` section 1) | | kept |
| DN-B5-4 | Decided here: PINs longer than four digits keep verifying until their holder changes them; the organization `pin_length` is no longer read | new | `docs/07` 12.4 | D1 |

### B6 Codes (v2.33 s1)

| Id | Rule | .NET today | Spec | Build |
|---|---|---|---|---|
| DN-B6-1 | Six digits, single use, valid 10 minutes, tied to the person, the purpose and the device that asked | built (`Application/Authentication/AuthCodes.cs:37`) | `docs/07` section 1 | kept |
| DN-B6-2 | Three wrong tries void the code and a new one is sent | replaces: void after five, nothing sent (`Domain/Entities.cs:64-70`) | `docs/07` 12.6 | D1 |
| DN-B6-3 | Not more than one a minute and five an hour per person | replaces: 60 s per person and purpose, 5 an hour, 10 a day (`AuthCodes.cs:13-14`, `:20`, `:24-25`) | `docs/07` 12.6 | D1 |
| DN-B6-4 | The code email holds the code, the purpose and the device name, nothing else | replaces: `Your {purpose} code is {code}. It expires in 10 minutes.` (`Infrastructure/Security.cs:120-121`) | `docs/07` 12.6 | D1 |

### B7 Trusted devices and the profile menu (v2.33 s1, s2)

| Id | Rule | .NET today | Spec | Build |
|---|---|---|---|---|
| DN-B7-1 | A long random token kept on the device, stored hashed, with device name, date trusted and last used | replaces: trust keyed by the client's `deviceId` (`Entities.cs:83-99`) | `docs/07` 12.8 | D1 |
| DN-B7-2 | A trusted device expires after 90 days unused | replaces: an optional fixed lifetime from the trust date (`AuthAccounts.cs:39-52`, `AuthContracts.cs:16`) | `docs/07` 12.8 | D1 |
| DN-B7-3 | After a PIN reset every trusted device of that person is removed; the device used for the reset can be trusted again in the same step | replaces: refresh tokens revoked, devices kept (`PinSetupService.cs:41-45`, `Application/Authentication/SessionTokens.cs:65-72`) | `docs/07` 12.9 | D1 |
| DN-B7-4 | After a block, trusted devices are removed and open sessions end at once | built (`AccessUseCases.cs:232-242`; `api.people_set_active`) | `docs/07` 12.9 | kept |
| DN-B7-5 | "Trust this device" is ticked by default and may be unticked | replaces: every verified device is trusted (`SignInService.cs:69`, `PinSetupService.cs:45`) | `docs/07` 12.8 | D1 |
| DN-B7-6 | Profile "Change PIN": current PIN, new PIN, repeat; the same PIN rules | new | `docs/06` N07 | D1 |
| DN-B7-7 | Profile "Trusted devices": the person's own devices with date trusted and last used, "This device" marked, Remove on each | replaces: revoke the current device only (A12) | `docs/06` N08, N09 | D1 |
| DN-B7-8 | "Sign out" on a trusted device returns to the PIN screen for that person | built (A11 keeps the trust) | `docs/07` 3.7 | kept |

### B8 History and change log (v2.33 s1)

| Id | Rule | .NET today | Spec | Build |
|---|---|---|---|---|
| DN-B8-1 | Change-log entries: "PIN set at first sign in", "PIN reset with a code", "PIN changed", "PIN locked after 5 wrong tries", "Device trusted", "Trusted device removed", "PIN reset required" | new | `docs/07` 12.11 | D1 (sign-in events), D2 (people actions) |
| DN-B8-2 | Ordinary sign-ins are kept in a separate sign-in history, not the change log | new in .NET (counters only, `Entities.cs:13-16`); Python has `identity.sign_in_attempts` | `docs/07` 12.10 | D1 |

### B9 Dated target sets (v2.32 s1, replacing v2.31 s1)

| Id | Rule | .NET today | Spec | Build |
|---|---|---|---|---|
| DN-B9-1 | A vehicle holds target sets: a start date and seven day figures, Monday to Sunday; a set applies until the next starts | replaces: dated weekly targets (`Domain/Setup/FleetVehicle.cs:126-142`) | `docs/04` 13.4 | D3 |
| DN-B9-2 | The target of a day is the figure for that weekday in the set in force that day; every gap, report and export uses it | replaces: the weekly target in force (`FleetVehicle.cs:114-123`) divided by 7 (`Application/RevenueContracts.cs:60`) | `docs/05` 10.4 | D3 (helpers), D4 (revenue) |
| DN-B9-3 | A set starts today or later, never in the past | replaces: an update appends a target from `max(today, joinedOn)` (`FleetVehicle.cs:75-80`) | `docs/05` 10.4 | D3 |
| DN-B9-4 | A set that has started cannot be edited or removed; it is corrected by a new set from today | new | `docs/05` 10.4 | D3 |
| DN-B9-5 | A set that has not started can be replaced (saved again on the same date) or removed | new | `docs/05` 10.4 | D3 |
| DN-B9-6 | A set equal to the one in force is refused, so no empty change is logged | new | `docs/05` 10.4 | D3 |
| DN-B9-7 | Logged as "Target set, [registration]" with the figures before, after and the start date; removing a future set is logged | replaces: `changed the weekly target of {reg} to {cur} {amount} from {date}` (`Application/Setup/VehicleUseCases.cs:58-60`, `:67`) | `docs/05` 10.4 | D3 |
| DN-B9-8 | Its own right, `veh.target` ("Set targets") | replaces: part of `vehicles.manage` | section 3 | D2 (key), D3 (routes) |
| DN-B9-9 | The vehicles list shows the weekly target in force and, under it, the next set with its start date | new | `docs/06` S17 | D3 |
| DN-B9-10 | A new vehicle's seven figures are entered on its form, all required, starting today; editing a vehicle no longer holds targets (fleet number, PSV company, initial investment only) | replaces: one weekly target on create and update (`VehicleUseCases.cs:58-60`) | `docs/06` S18, S19 | D3 |
| DN-B9-11 | The weekly target is the sum of the seven and is never typed | new | `docs/06` S17 | D3 |
| DN-B9-12 | "Revenue against target" in Reports sums the day targets across the period | new | prompt 08b | 08b |

### B10 Fleet number (v2.29 s4, v2.31 s1)

| Id | Rule | .NET today | Spec | Build |
|---|---|---|---|---|
| DN-B10-1 | A vehicle has a fleet number: text, required, unique within a PSV company. Required on every save of the vehicle (S18, S19); retiring and restoring do not ask for it, so a vehicle saved before the number existed can still leave the fleet | new (`FleetVehicle.cs:16-31` has none) | `docs/04` 13.4 | D3 |
| DN-B10-2 | It can be edited after the registration; changes are logged | new | `docs/05` 10.4 | D3 |
| DN-B10-3 | Every vehicle drop-down shows registration and fleet number only ("KDG 412M · 14"); the registration alone until a number is set | new | `docs/06` 2.12 (option bodies) | D3 |
| DN-B10-4 | Revenue search matches registration or fleet number | new | `docs/06` R01 | D4 |

### B11 Optional initial investment (v2.32 s2)

| Id | Rule | .NET today | Spec | Build |
|---|---|---|---|---|
| DN-B11-1 | The initial investment may be left empty on a new vehicle and cleared on an existing one; stored empty, not zero; the vehicles table shows a blank | new: .NET has dated investment entries only (`Domain/Setup/VehicleInvestment.cs:4-43`, `Api/SetupEndpoints.cs:177-184`) and no vehicle field (`Application/Setup/SetupContracts.cs:69`) | `docs/04` 13.4; `docs/06` S17 to S19 | D3 |
| DN-B11-2 | The Investment report lists such a vehicle last with no "Recovered" figure | new | prompt 08b | 08b |

### B12 How far back a person may change records (v2.32 s3)

| Id | Rule | .NET today | Spec | Build |
|---|---|---|---|---|
| DN-B12-1 | A limit per person: no rolling limit, N days back, or N months back, plus an optional fixed date; with both, the later date is the earliest allowed | new: writes only refuse the future (`Application/RevenueUseCases.cs:109-110`, `Application/PettyCashUseCases.cs:371-377`, `Application/CentralExpenseUseCases.cs:225-231`) | `docs/05` 10.2 | D2 |
| DN-B12-2 | N days back: today and the N days before it; 0 is today only; it moves forward every day | new | `docs/05` 10.2 | D2 |
| DN-B12-3 | N months back: the same day N months ago; when that day does not exist, the last day of that month | new | `docs/05` 10.2 | D2 |
| DN-B12-4 | New people start on 7 days back | new | `docs/05` 10.3 | D2 |
| DN-B12-5 | Applies to capturing or changing revenue; adding, editing, deleting or reopening a petty-cash expense; adding or editing a central expense; issuing cash, credit notes and deleting a cash entry. Not to viewing, reports, exports, approving, rejecting, sending back, schedules, savings or setup | new | `docs/05` 10.2 | D4 (revenue), 08, 08b |
| DN-B12-6 | Checked on the server on every write, on the record's date; an offline entry that syncs late is checked against the limit at the time it was captured | new | `docs/05` 10.5 | D4, 08, 08b |
| DN-B12-7 | Stored on the person as mode, number and optional date; changes are logged with access changes | new | `docs/04` 13.2 | D2 |
| DN-B12-8 | "Can change" in words: "Any date", "2 days back", "1 month back, not before 14 September 2026" | new | `docs/06` S05 | D2 |

### B13 People and access (v2.32 s4, v2.33 s3)

| Id | Rule | .NET today | Spec | Build |
|---|---|---|---|---|
| DN-B13-1 | 59 rights in 12 modules (58 in v2.32 plus `ppl.signin`); every right of a module needs the module's view right | replaces: 40 keys in 8 groups (`Domain/PermissionKeys.cs:6-52`, `Application/AccessContracts.cs:28-94`, dependencies `Domain/Access.cs:55-89`, role defaults `AccessContracts.cs:104-125`) | section 3 | D2 |
| DN-B13-2 | People list: one chip per module (filled when every right is held, "n of m" when partial, "Everything" for all), vehicles, "Can change", status with the last sign-in | new | `docs/06` S05 | D2 |
| DN-B13-3 | Person form with panes Details, Vehicles and dates, Access, Sign in; a save error opens the pane that holds the problem | client; the server's refusal codes name the field (`docs/06` section 3) | | web |
| DN-B13-4 | Block or unblock is its own right (`ppl.block`) | replaces: `people.manage` (`AccessUseCases.cs:212-247`) | section 3 | D2 |

### B14 Low-day reasons and the revenue rights (v2.29 s1, v2.30 s1)

| Id | Rule | .NET today | Spec | Build |
|---|---|---|---|---|
| DN-B14-1 | A day's revenue below the threshold cannot be saved without a reason; the reasons are the no-revenue list (Garage, Arrest, No Crew, Other) | replaces: an amount cannot carry a reason (`Domain/Revenue.cs:17-25`) | `docs/05` 10.5 | D4 |
| DN-B14-2 | The threshold (4,000) is one figure for the fleet, a setting | new | `docs/04` 13.5 | D4 |
| DN-B14-3 | Stored: an amount at or above the threshold; an amount and a reason below it; a reason alone when nothing came in; no record when not captured | replaces: amount or reason (`Domain/Revenue.cs:17-36`) | `docs/04` 13.5 | D4 |
| DN-B14-4 | A low day counts as revenue in every total; "Below 4,000" counts low days and no-revenue days and replaces "No revenue days" | new | `docs/06` R01 | D4 |
| DN-B14-5 | `rev.capture` fills a day with no record; `rev.edit` changes a saved one | replaces: `revenue.no_earnings` for any reason (`Application/RevenueUseCases.cs:117-118`), capture for a new record (`:121-122`), correct only for a past saved day (`:123-124`, `Application/RevenueContracts.cs:50-59`) | `docs/05` 10.5 | D4 |
| DN-B14-6 | A cell the person cannot change is not a button | replaces: `canEdit` by the old rights | `docs/05` 10.5 (`can_edit`) | D4 |
| DN-B14-7 | A new capture logs once; changing a saved figure or reason logs before and after ("KES 7,900" to "KES 2,500, Garage") | built (snapshots of every capture and change) | `docs/05` 4.7 | kept |
| DN-B14-8 | The savings revenue rule sums the amounts; a reason-only day counts as zero | new | prompt 08b | 08b |

### B15 The gap to target (v2.30 s2, v2.31 s2)

| Id | Rule | .NET today | Spec | Build |
|---|---|---|---|---|
| DN-B15-1 | Gap = revenue minus the day targets of the days that count so far: every day up to yesterday, plus today once it has a record; a finished week uses all seven; a missing day and a no-revenue day count against the vehicle | replaces: `Percent` only (`Application/RevenueContracts.cs:77`, `:90`; `Infrastructure/RevenueRepository.cs:260`, `:329-330`) | `docs/05` 10.5 | D4 |
| DN-B15-2 | A signed figure; green at or above target, amber below it by up to the band, red beyond; the band (10 per cent of the target) is a setting | new | `docs/05` 10.5 | D4 |
| DN-B15-3 | The headline bar: Revenue, "Gap to target so far" (or "Gap to target" for a finished week), Below 4,000, Missing days; the export uses the same signed figure | new | `docs/06` R01; the export in 08b | D4, 08b |
| DN-B15-4 | The pop-up shows the day target of that day | replaces: `expected` = weekly target / 7 (`RevenueContracts.cs:60`) | `docs/06` R01 | D4 |

### B16 Three-level expense categories (v2.31 s3)

| Id | Rule | .NET today | Spec | Build |
|---|---|---|---|---|
| DN-B16-1 | Main category, category, item; all set up by the owner; none built in | replaces: the built-in `ExpenseBucket` (`Domain/Setup/ExpenseCatalog.cs:5-10`) | `docs/04` 13.4 | D3 |
| DN-B16-2 | "Counts as" and the three built-in groups go as system values; they may exist only as ordinary records | replaces: a required bucket on every category (`ExpenseCatalog.cs:43`, `:46`; `Application/Setup/SetupContracts.cs:118`) | `docs/05` 10.4 | D3 |
| DN-B16-3 | A main category has a name, unique | new | `docs/04` 13.4 | D3 |
| DN-B16-4 | A category has a name and a main category or none ("No main category" first) | new | `docs/06` S34 | D3 |
| DN-B16-5 | Setting a main category later regroups every past expense under it at once: expenses point to the item, the item to the category, the category to the main category; nothing is stored on the expense | new | `docs/04` 13.4 | D3 |
| DN-B16-6 | Categories with no main category show "Not set"; the Categories tab counts them | new | `docs/06` S31 | D3 |
| DN-B16-7 | The Expense items rights cover all three levels | new | section 3 | D2, D3 |
| DN-B16-8 | Reports per main category, with "No main category" when it holds money; no report depends on a fixed list | new | prompt 08b | 08b |

### B17 Savings apart from scheduled expenses (v2.30 s3)

| Id | Rule | .NET today | Spec | Build |
|---|---|---|---|---|
| DN-B17-1 | Rights split: `sched.view/add/edit/pause` and `sav.view/add/edit/pause` | replaces: `commitments.view` and `commitments.manage` (`Application/Setup/RecurringUseCases.cs:10`, `:18`, `:22`, `:30`, `:45`, `:47`, `:90`, `:111`) | section 3; `docs/05` 10.4 | D2 (keys), D3 (routes) |
| DN-B17-2 | Whoever holds a scheduled-items right gets the matching savings right; after that the two are apart | new | section 3.5 | D2 (development data), 10 |
| DN-B17-3 | Change-log entries read "Saving, [name]" or "Scheduled expense, [name]" | replaces: `Added scheduled saving {name}`, `Changed the {parts} of {name}`, `Paused/Resumed {name} from {date}`, `Stopped {name} from {date}`, `Cancelled the stop of {name}` (`RecurringUseCases.cs:84`, `:156`, `:40`, `:105`, `:121`) | `docs/05` 10.4 | D3 |
| DN-B17-4 | Two pages and two menu items, each with a headline bar | client and 08b (summary figures) | | 08b |

### B18 The saving model (v2.30 s3 and s4, v2.28 s1; designed by prompt 08b D0, 2026-10-12)

The .NET column was read on 2026-10-12 at `HEAD` 493bf82 plus the working tree
(`docs/inventory/inventory-expenses-reports.md`). The v2.3 prototype (`condCheck`, `postRun`, `settleSavings`,
`saveBal`, `reportData`) settles what the notes leave to the screen. Tables `docs/04-schema.md` 14.3; routines
`docs/05-routines.md` 11.1 and 11.3; routes `docs/06-http-contract.md` 2.13.4.

| Id | Rule | .NET today | Spec | Build |
|---|---|---|---|---|
| DN-B18-1 | An amount per vehicle; nothing to split or balance | one total split across the shares, which must add up (`RecurringItem.cs:139-144`) | `docs/06` S26 (each share is the vehicle's amount) | 08b |
| DN-B18-2 | A saving runs every day, week, month or year | weekly or monthly only (`RecurringItem.cs:154-155`) | `docs/05` 11.3 | 08b |
| DN-B18-3 | A revenue rule `{min, days}` with days 1, 7 or 30: the vehicle saves only when its own revenue over the days ending on the run date reaches `min`; a reason-only day counts zero | none | `docs/05` 11.1 (`setup.saving_window_revenue`) | 08b |
| DN-B18-4 | Each run and vehicle is saved, skipped or held; held until every day of its window has a record; once decided, final; after any revenue save the held runs are decided again | none | `docs/04` 14.3 (`setup.saving_runs`); `DEC-31`, `DEC-34` | 08b |
| DN-B18-5 | An optional opening balance: a date and an amount per vehicle; balance = opening amount + saved runs dated after the opening date | none | `docs/04` 14.3; `DEC-35` | 08b |
| DN-B18-6 | No start date: a saving runs from its next run date; no back posting | a start date, and a past start posts the earlier runs (`RecurringItem.cs:158-162`) | `DEC-33` | 08b |
| DN-B18-7 | No end date (question 49) | an optional end date | `DEC-33` | 08b |
| DN-B18-8 | The Savings report: saved, skipped and waiting runs, saved, not saved, balance as at the period's end | runs, saved, balance (`FleetReports.cs:106-129`) | `docs/05` 11.4 | 08b |
| DN-B18-9 | The Savings page bar: savings balance, saved this month, running, paused; the Scheduled expenses bar: due this month, running, paused | `GET /setup/recurring/summary` without the counts | `docs/06` S53 | 08b |
| DN-B18-10 | A saving's runs pop-up: each run and vehicle with its state and the revenue measured | runs without a state | `docs/06` S54 | 08b |

### B19 Petty cash (v2.29 s3 and s5, v2.28 s1; designed by prompt 08 D0, 2026-10-12)

The .NET column was read on 2026-10-12 at `HEAD` 493bf82 plus the working tree (the
feature's last commit is 9276c51); `UseCases` is `apps/api/Application/PettyCashUseCases.cs`.
The v2.3 prototype (`docs/design/XCODE_Web_v2.3.html`, functions `pcStats`, `pcCanEdit`,
`pcCanDel`, `pcMore`, `saveDlg`) settles what the notes leave to the screen. The routes,
gates and refusals are `docs/06-http-contract.md` 2.11; the table `docs/04-schema.md` 6.2;
the routines `docs/05-routines.md` 4.9.

| Id | Rule | .NET today | Spec | Build |
|---|---|---|---|---|
| DN-B19-1 | Twenty rights (section 3.1 rows 12 to 31). `pettycash.view` opens the module (overview, list); `pettycash.view_all` shows every float, cut to the vehicles the person sees, as before | 6 keys; the module opens on `spend` or `view_all` (`UseCases:15`) | `docs/06` 2.11 | 08 |
| DN-B19-2 | Add an expense: on one's own float with `pettycash.spend`; on another manager's float with `pettycash.spend_other` (the target must keep a float). Without `spend_other` a different holder is refused as today | own float only (`UseCases:345-350`) | `docs/05` 4.9 | 08 |
| DN-B19-3 | Edit an expense only while it waits (sent back included): own float with `pettycash.edit_own`, any float with `pettycash.edit`. An approved or rejected expense must be reopened first. The date may change; the edit is logged. Saving clears "sent back" and sends it for approval again | `spend` changes one's own until approved; `approve_item` changes anyone else's in any status, except an approved one they recorded (`UseCases:302-311`) | `docs/05` 4.9 | 08 |
| DN-B19-4 | Delete: a waiting expense with `pettycash.delete_own` (own float) or `pettycash.delete` (any), no reason needed; an approved expense with `pettycash.delete_approved` and a reason, which also takes it out of the vehicle report; a rejected expense cannot be deleted (reopen it first). Rows stay in the table, flagged; every delete is logged with the amount, status and reason (the snapshot) | removal follows the change rule and always needs a reason (`UseCases:224-240`) | `docs/05` 4.9 | 08 |
| DN-B19-5 | Delete a cash entry (cash given or a credit note): `pettycash.delete_cash`, reason required, logged; balances recalculate | removal of cash needs `issue` (`UseCases:317-327`) | `docs/05` 4.9 | 08 |
| DN-B19-6 | Send back: `pettycash.send_back`, a reason (1 to 200) on a waiting expense not already sent back. The expense stays waiting with the reason, still counts as spent, cannot be approved, ticked or approved by day. Saving an edit or reopening clears it | a status `SentBack` under `approve_item` (`UseCases:206-222`) | `docs/04` 6.2 | 08 |
| DN-B19-7 | Reject: `pettycash.reject`, a reason (1 to 200) on a waiting expense (sent back included). Final until reopened. A rejected expense leaves the balance, the Expenses figure and the vehicle report: the manager carries the cost | none | `docs/05` 4.9 | 08 |
| DN-B19-8 | Reopen: `pettycash.reopen`, a reason (1 to 200), an approved or rejected expense goes back to waiting; review, rejection and "sent back" are cleared; an approved one leaves the vehicle report (only approved expenses post, `PC-31`) | none | `docs/05` 4.9 | 08 |
| DN-B19-9 | Approve one entry, the ticked entries, a day or a period: `pettycash.approve_item` (`pettycash.approve_day` for a day or period), a waiting expense not sent back, never on one's own float, never one's own entry, never above one's approval limit | the same reviewer rule, applied to credit notes too (`UseCases:313-339`); ticked and period approval in the working tree (`UseCases:242-291`) | `docs/05` 4.9 | 08 |
| DN-B19-10 | Credit note: `pettycash.credit`; date, manager, amount and an optional reason; no payee field and no "pay back" tick on screen. It reduces the float at once and is never approved, like cash | reviewed like an expense; payee optional in the working tree (`Domain/PettyCash.cs:71`), reason forced (`:73-74`); recorded with `spend` (own float) or `issue` (`UseCases:351-358`) | `docs/04` 6.2 | 08 |
| DN-B19-11 | Balance = cash given - credit notes - expenses that are not rejected (waiting ones count), over entries not deleted. Any period can be shown: opening at the start of the first day, closing at the end of the last | every expense counts whatever its status (`PettyCashRepository.cs:67-75`); periods in the working tree (`UseCases:55-68`) | `docs/05` 4.9 | 08 |
| DN-B19-12 | The back-dating limit (B12) applies to adding, editing (both the old and the new date), deleting and reopening an expense, to cash given, credit notes and the delete of a cash entry; not to approving, sending back or rejecting (question 51) | none | `docs/05` 10.2 | 08 |
| DN-B19-13 | A shared purchase is one row per vehicle with a group reference, and the other parts are recounted when one changes (v2.28 s1, v2.29 s5) | petty cash has no groups; central expenses keep `GroupSize` without a recount (`Domain/CentralExpense.cs:123-148`) | question 68 | 08b (DEC-26) |

The rights' labels (section 3.1) change the permission sentences of the 403 refusals; the
sentences are in `docs/06-http-contract.md` section 3.

B18 (the saving model) is designed above by prompt 08b's D0 (question 49); B19 (petty cash) with prompt
08, which uses the petty-cash keys of section 3; B20 (data) with prompt 10, specified in
`docs/10-data-migration.md` section 3.1.

## 2. Decisions taken here

Where the notes are silent, conflict with a released client, or leave an attack open. Each
is argued in the section named; owner questions are in `docs/13-open-questions.md`.

| Id | Decision | Why (short) | Section |
|---|---|---|---|
| DEC-1 | The lock has two scopes: five wrong PINs in a row on trusted devices lock the PIN on every device; five in a row on untrusted devices lock every untrusted device. Both end only with a code (a reset, or for the untrusted scope also a verified new device) | the literal "every device" lets anyone who knows a number lock that person out everywhere in five taps, and its "reset on a correct PIN" gives a stranger four silent guesses per sign-in of the owner; two scopes keep five guesses per code event and the owner's phone working | `docs/07` 12.5, 12.14 |
| DEC-2 | The number step answers "PIN" for an unknown number too, and simulates its tries and lock from the sign-in history; it answers "code" for a person without a PIN or with a forced reset, and "blocked" for a blocked person | the notes' "where possible": the common case (a real account with a PIN) cannot be told from an unknown number; the two answers that leak are the ones the notes require | `docs/07` 12.2, 12.14 |
| DEC-3 | New routes for the number-first flow; the thirteen `/auth` routes keep their envelope and uniform refusals for v2.11 phones; the server rules (lock, codes, PIN rules, removal of devices) apply on both | question 54; new answers (tries left, locked, blocked) would break the uniform refusals of the old routes | `docs/07` 12.13; `docs/06` 2.12 |
| DEC-4 | The device token is 32 random bytes, stored as its SHA-256 (not the keyed digest) | a signing-key rotation must not untrust every device; 256 random bits need no key or salt | `docs/07` 12.8 |
| DEC-5 | Rows trusted by `deviceId` alone (v2.11) stay trusted on the old routes only; a row that has a token is trusted only with the token | phones keep working; a device trusted the new way cannot be claimed by knowing its id | `docs/07` 12.8 |
| DEC-6 | "Trust this device" unticked gives a session-only device row (`remembered = false`) | sessions are bound to a device row today; the next sign-in on that device needs a code again | `docs/07` 12.8 |
| DEC-7 | PINs longer than four digits keep verifying until changed; every new PIN is four digits; `pin_length` is stored and served but read by nothing | a hash does not reveal its length, so the old PINs cannot be found and forced to reset | `docs/07` 12.4 |
| DEC-8 | The automatic new code after three wrong tries is exempt from the one-a-minute rule, counts toward five an hour and ten a day, and is silent when a cap stops it | three wrong tries inside a minute would otherwise leave no code; caps are silent everywhere (enumeration) | `docs/07` 12.6 |
| DEC-9 | Legacy permission keys: the 20 keys that leave the catalogue are derived from the new rights and still carried in the token and `GET /auth/session`, never granted | v2.11 phones gate their screens on them (`apps/mobile/src/shell/access.ts`, `packages/shared/src/permissions.ts`) | section 3.4 |
| DEC-10 | Organization settings are for the Owner role (hidden key `organization.manage`, a role default of Owner only) | the 59 rights have no settings right; settings include the security policy | section 3.3; question 59 |
| DEC-11 | Existing people get no back-dating limit; new people get 7 days | the notes say what new people get; taking away what existing people can do today is the owner's call | `docs/10` 3.1; question 65 |
| DEC-12 | An offline replay is checked as of `greatest(least(capturedAt, now), now - 72 hours)`; a v2.11 replay (no `capturedAt`) is checked as of now | the server cannot verify a client clock; 72 hours is the phone's offline unlock window (`OFFLINE_UNLOCK_HOURS`) | `docs/05` 10.5; `docs/12` 7 |
| DEC-13 | A new vehicle's first target set starts on its join date (today unless back-dated, question 50); every later set starts today or later | a new vehicle has no past week to change; days between a back-dated join and today need a target | `docs/05` 10.4 |
| DEC-14 | A set that starts today may be replaced on the same day, not removed | it is the notes' own correction path ("add a new set from today") when the set in force began today | `docs/05` 10.4 |
| DEC-15 | `weeklyTarget` on the vehicle saves is ignored; a new vehicle needs `dayTargets` | no released client can use it: today's web is refused on every vehicle save anyway (the fleet number is required, DN-B10-1), and a translation of a weekly figure into a set would be code without a caller | `docs/06` S18, S19 |
| DEC-16 | The note on "Other" becomes optional; a reason with an amount at or above the threshold is refused, not dropped | the prototype has no note field; v2.11 phones still send one; an explicit refusal beats a silent change of what was sent | `docs/05` 10.5 |
| DEC-17 | Existing categories get main categories made from the buckets they use, as ordinary records | keeps today's grouping; the owner can rename or move them | `docs/10` 3.1; question 63 |
| DEC-18 | The dated investment entries (S41 to S44) stay beside the new initial investment | they are today's data and web screens; how the two combine in the report is the owner's | question 61 |
| DEC-19 | Remove-all of a person's devices is the existing S11 route under the new right, logged as "Trusted device removed" | the effect is identical; one route, the notes' wording | `docs/06` S11 |
| DEC-20 | Change-log rows for sign-in events use a new section `signIn`, visible like `people` rows | the actor is the person or an administrator; the subject is a person | `docs/04` 13.3 |
| DEC-21 | "Sent back" is a reason on a waiting expense (`sent_back_note`), not a status; the stored statuses are 1 waiting, 2 approved, 4 rejected (3 stays unused so the .NET `SentBack` code is never read as another state); the wire keeps the word `sentBack` for a waiting expense with a reason, so released clients read the same words | the notes (v2.29 s5) store it on the waiting entry; v2.11 phones and today's web show `sentBack` | `docs/04` 6.2 |
| DEC-22 | Credit notes are not reviewed: status null like cash, never in "waiting", approve, send back and reject refuse them | the notes put credit notes with cash given (v2.28 s1, v2.29 s3); a reviewed credit note would need a right the notes do not have | `docs/05` 4.9 |
| DEC-23 | Cash given and credit notes are not edited: the change route refuses them; they are deleted (with `pettycash.delete_cash`) and recorded again | the notes give the cash table a delete action only and no edit right; delete and record keeps both amounts in the log | `docs/06` 2.11 |
| DEC-24 | Approve, send back and reject share the reviewer rule (not one's own float, not an entry one recorded, within the approval limit); reopen needs only its right and the back-dating limit | one rule for every decision on an entry; a reopened expense needs a reviewer again before it posts anywhere | `docs/05` 4.9 |
| DEC-25 | The dashboard has the one right `dash.pettycash`: the float card when the person keeps a float (`pettycash.spend`), the approvals card when they hold `pettycash.approve_item`; without `dash.pettycash` the route is 403. `dash.float` stays a derived legacy key (section 3.4) | the 59 rights have one petty-cash dashboard right; cards follow what the person can act on | `docs/06` 2.11 |
| DEC-26 | Petty-cash shared purchases (one row per vehicle with a group reference, recounted when a part changes) are built with the group model of central expenses in prompt 08b; the table gets the group columns then, as nullable columns | the create of today's clients takes one vehicle; the group model is the ledger's and is designed once (question 68) | question 68 |
| DEC-27 | A credit note's `payee` and `reimbursable` stay accepted and stored (payee 1 to 80 characters), never required | released clients send them; the notes only drop them from the form | `docs/06` 2.11 |
| DEC-28 | A delete reason is optional for a waiting expense (1 to 500 characters when given); the change-log reason is then `Removed {subject}` | the notes' "confirm only, no reason"; the log still carries the amount and status in the snapshot | `docs/05` 4.9 |
| DEC-29 | New wire fields are appended at the end of their records (`rejected` on a float; `rejectReason`, `reopenReason`, `canSendBack`, `canReject`, `canReopen` on an entry; one flag per new right on `permissions`); `canReview` keeps meaning "may approve it now" | released clients ignore unknown members; the order of the fields they read does not move | `docs/06` 2.11 |
| DEC-30 | The back-dating limit (B12) also applies to removing a central expense, and a change is checked on its old and its new date | "never before a date" closes the books: a delete or a move out of a closed day would reopen them; petty cash does the same (DN-B19-12) | `docs/05` 11.2 |
| DEC-31 | Saving runs with a revenue rule are decided by the writes that can complete a window (revenue capture and day save, the saving's own save, a later join date, a return from time away), under a per-vehicle advisory lock taken after the vehicle row; reads never decide | "after any revenue save, decide the held runs again" (v2.28); deciding on read would make GET requests write and let the first viewer fix an outcome; the lock closes the race in which two saves of two days each miss the other's record | `docs/05` 11.1 |
| DEC-32 | Scheduled cost runs and the runs of savings without a rule stay computed on read; no posting job and no stored posting rows; only decided runs are stored, under (item, run date, vehicle) | .NET stores none; a computed run is unique per (item, day, vehicle) by construction and never stale; a stored outcome is needed only where later revenue must not change it; a job would need a scheduler the API does not have (`docs/01-architecture.md` 10) | `docs/04` 14.6 |
| DEC-33 | A new saving starts on the business date whatever start is sent; a revise keeps its start; a saving with an end date that is new or differs from the stored one is refused (`recurring_savings_end`; a migrated end stands until cleared); savings may run daily to yearly | the notes' locked model (B18, question 49); an explicit refusal beats silently dropping what the client sent (`DEC-16`) | `docs/05` 11.3 |
| DEC-34 | A window's days are the vehicle's active days (joined, not away, not left); only those need a record; a reason-only day counts zero, an amount with a reason counts its amount | a day the vehicle could not work cannot be captured, so requiring it would hold the run forever (question 79); B14-8 | `docs/05` 11.1 |
| DEC-35 | Balance = the opening amounts (when the opening date is on or before the as-at day) + the saved runs dated after the opening date and on or before the as-at day | the notes' formula (v2.28 s1), with the as-at day the reports need | `docs/05` 11.1 |
| DEC-36 | Scheduled expenses keep 06's model (shares, a start no earlier than the first of the month, an optional end) | the locked model is written for savings; a loan must be able to stop (question 75) | `docs/05` 11.3 |
| DEC-37 | A report's target is the day targets of the days that count (before the business date, or recorded), as the vehicle report counts it | reports and the vehicle screens must agree (question 78) | `docs/05` 11.4 |
| DEC-38 | Net by vehicle has one money-out column per main category holding money in the period, then `No main category` when it holds money; Money out lists main category (`Not set`), category, item, entries, quantity, unit costs, amount, share, with one figure per main category | v2.31 s3 (B16-8); quantity and unit costs stay for the true-unit-cost rule (v2.28 s1) | `docs/05` 11.4 |
| DEC-39 | Investment: invested = initial investment + the dated entries; a vehicle with neither is last, with no invested and no recovered figure | question 61's default; v2.32 s2 (B11-2) | `docs/05` 11.4 |
| DEC-40 | Reports: `reports.view` (investment `reports.investment`; petty-cash reports also `pettycash.reports`, every float with `pettycash.view_all`, else one's own); exports: `reports.export`, `revenue.export`, `expenses.export`, `pettycash.export`, each with the screen's read right | the 59 rights (B21); the prototype gates only the investment report (question 73) | `docs/06` 2.13 |
| DEC-41 | Petty-cash reports keep `sentBack` (waiting expenses with a send-back reason) and add `rejected` ("Rejected and reopened"); By manager adds a rejected column; a rejected expense is not spent | released clients ask for `sentBack`; the prototype's report list (`PCREPORTS`); DN-B19-7 | `docs/05` 11.4 |
| DEC-42 | A day save runs the single capture's steps per row (one helper); the entry shape of every row first in the order sent, then the rows in ascending vehicle id | one copy of the revenue rules (the D4 verify's request); one lock order for every multi-row write, so two day saves cannot deadlock on new records' unique entries | `docs/05` 11.5 |
| DEC-43 | Pause and resume are gated by `scheduled.pause` or `savings.pause` by kind and log `Scheduled expense, {name}` / `Saving, {name}`; a pause covers the business date, as .NET | B17 (DN-B17-1, DN-B17-3); drift row 5 is .NET's behaviour (question 80) | `docs/05` 11.3 |
| DEC-44 | The revenue export ends with Week total, Target to date (or Target for a finished week) and the signed Gap; its figures are the gap, `Below {threshold}` and Missing days | B15-3, B14-4 | `docs/05` 11.4 |
| DEC-45 | Every export, reports included, reads its rows and writes its change-log row in one transaction, and is capped at 10 000 rows | an audit row before the file, never a file without one; .NET capped only the screen exports, but a report can be as large (a year of gaps over a fleet) | `docs/12-security.md` 2.8 |
| DEC-46 | Central expenses live in a schema of their own (`expenses`), report helpers in `reports` | as petty cash: a money ledger apart from configuration; `reports` holds functions only | `docs/04` 14.1 |

## 3. Rights catalogue

### 3.1 The 59 rights

Wire keys follow `docs/11-naming.md` section 5: domain words, `<module>.<verb>`; a current
key is kept where the right means what it meant, so v2.11 phones and the token keep them.
"Kept" means the key exists today; "relabelled" means kept with the notes' label; "new"
keys are added. `Needs` lists the direct dependencies (the resolver expands them and drops
a right whose needs are missing, as today). Order is catalogue order (`group_order`,
`item_order`).

| # | Module | Prototype id | Wire key | Label | Needs | |
|---|---|---|---|---|---|---|
| 1 | Dashboard | `dash.net` | `dash.net` | See revenue, money out and net | `revenue.view` | relabelled |
| 2 | Dashboard | `dash.gaps` | `dash.gaps` | See capture gaps | `revenue.view` | relabelled |
| 3 | Dashboard | `dash.pc` | `dash.pettycash` | See petty cash position | `pettycash.view` | relabelled |
| 4 | Revenue | `rev.view` | `revenue.view` | View revenue | | relabelled |
| 5 | Revenue | `rev.capture` | `revenue.capture` | Capture revenue | `revenue.view` | kept |
| 6 | Revenue | `rev.edit` | `revenue.correct` | Change revenue already saved | `revenue.view` | relabelled; now any saved day, today's included |
| 7 | Revenue | `rev.export` | `revenue.export` | Export revenue | `revenue.view` | new |
| 8 | Central expenses | `exp.view` | `expenses.view` | View central expenses | | relabelled |
| 9 | Central expenses | `exp.add` | `expenses.capture` | Record an expense | `expenses.view` | relabelled |
| 10 | Central expenses | `exp.edit` | `expenses.correct` | Edit an expense | `expenses.view` | relabelled |
| 11 | Central expenses | `exp.export` | `expenses.export` | Export central expenses | `expenses.view` | new |
| 12 | Petty cash (View) | `pc.see` | `pettycash.view` | View petty cash | | new |
| 13 | Petty cash (View) | `pc.view` | `pettycash.view_all` | See every manager's float | `pettycash.view` | relabelled |
| 14 | Petty cash (View) | `pc.reports` | `pettycash.reports` | View petty cash reports | `pettycash.view` | new |
| 15 | Petty cash (View) | `pc.export` | `pettycash.export` | Export petty cash | `pettycash.view` | new |
| 16 | Petty cash (Expenses) | `pc.spend` | `pettycash.spend` | Add an expense | `pettycash.view` | relabelled |
| 17 | Petty cash (Expenses) | `pc.spend_other` | `pettycash.spend_other` | Add for another manager | `pettycash.view` | new |
| 18 | Petty cash (Expenses) | `pc.edit_own` | `pettycash.edit_own` | Edit own expense | `pettycash.view` | new |
| 19 | Petty cash (Expenses) | `pc.edit` | `pettycash.edit` | Edit any expense | `pettycash.view` | new |
| 20 | Petty cash (Expenses) | `pc.delete_own` | `pettycash.delete_own` | Delete own expense | `pettycash.view` | new |
| 21 | Petty cash (Expenses) | `pc.delete` | `pettycash.delete` | Delete any expense | `pettycash.view` | new |
| 22 | Petty cash (Expenses) | `pc.delete_approved` | `pettycash.delete_approved` | Delete after approval | `pettycash.view` | new |
| 23 | Petty cash (Approval) | `pc.sendback` | `pettycash.send_back` | Send an expense back | `pettycash.view` | new |
| 24 | Petty cash (Approval) | `pc.approve_item` | `pettycash.approve_item` | Approve an expense | `pettycash.view` | relabelled |
| 25 | Petty cash (Approval) | `pc.approve_day` | `pettycash.approve_day` | Approve a whole day | `pettycash.approve_item` | kept |
| 26 | Petty cash (Approval) | `pc.reject` | `pettycash.reject` | Reject an expense | `pettycash.view` | new |
| 27 | Petty cash (Approval) | `pc.reopen` | `pettycash.reopen` | Reopen an approved or rejected expense | `pettycash.view` | new |
| 28 | Petty cash (Cash) | `pc.issue` | `pettycash.issue` | Issue cash | `pettycash.view` | relabelled |
| 29 | Petty cash (Cash) | `pc.negative` | `pettycash.issue_negative` | Issue cash to a float below zero | `pettycash.issue` | relabelled |
| 30 | Petty cash (Cash) | `pc.credit` | `pettycash.credit` | Record a credit note | `pettycash.view` | new |
| 31 | Petty cash (Cash) | `pc.cash_delete` | `pettycash.delete_cash` | Delete a cash entry | `pettycash.view` | new |
| 32 | Scheduled expenses | `sched.view` | `scheduled.view` | View scheduled expenses | | new |
| 33 | Scheduled expenses | `sched.add` | `scheduled.add` | Add a scheduled expense | `scheduled.view` | new |
| 34 | Scheduled expenses | `sched.edit` | `scheduled.edit` | Edit a scheduled expense | `scheduled.view` | new |
| 35 | Scheduled expenses | `sched.pause` | `scheduled.pause` | Pause or resume | `scheduled.view` | new |
| 36 | Savings | `sav.view` | `savings.view` | View savings | | new |
| 37 | Savings | `sav.add` | `savings.add` | Add a saving | `savings.view` | new |
| 38 | Savings | `sav.edit` | `savings.edit` | Edit a saving | `savings.view` | new |
| 39 | Savings | `sav.pause` | `savings.pause` | Pause or resume | `savings.view` | new |
| 40 | Reports | `rep.view` | `reports.view` | View reports | | kept |
| 41 | Reports | `rep.invest` | `reports.investment` | See the investment report | `reports.view` | new |
| 42 | Reports | `rep.export` | `reports.export` | Export reports | `reports.view` | kept |
| 43 | PSV companies | `see.companies` | `companies.view` | View companies | | new |
| 44 | PSV companies | `co.add` | `companies.add` | Add a company | `companies.view` | new |
| 45 | PSV companies | `co.edit` | `companies.edit` | Edit a company | `companies.view` | new |
| 46 | Vehicles | `see.vehicles` | `vehicles.view` | View vehicles | | new |
| 47 | Vehicles | `veh.add` | `vehicles.add` | Add a vehicle | `vehicles.view` | new |
| 48 | Vehicles | `veh.edit` | `vehicles.edit` | Edit a vehicle | `vehicles.view` | new |
| 49 | Vehicles | `veh.target` | `vehicles.target` | Set targets | `vehicles.view` | new |
| 50 | Expense items | `see.items` | `catalog.view` | View items and categories | | new |
| 51 | Expense items | `item.add` | `catalog.add` | Add an item or category | `catalog.view` | new |
| 52 | Expense items | `item.edit` | `catalog.edit` | Edit an item or category | `catalog.view` | new |
| 53 | Expense items | `item.stop` | `catalog.stop` | Stop or resume an item | `catalog.view` | new |
| 54 | People and access | `see.people` | `people.view` | View people | | kept |
| 55 | People and access | `ppl.add` | `people.add` | Add a person | `people.view` | new |
| 56 | People and access | `ppl.edit` | `people.edit` | Edit a person and their access | `people.view` | new |
| 57 | People and access | `ppl.block` | `people.block` | Block or unblock a person | `people.view` | new |
| 58 | People and access | `ppl.signin` | `people.sign_in` | Reset a PIN and remove devices | `people.view` | new |
| 59 | Change log | `set.log` | `audit.view` | View the change log | | relabelled |

19 keys are kept (5, 25, 40, 42, 54 unchanged; 14 relabelled), 40 are new: 59 in all.
The module name is the catalogue `group_name`; the petty-cash section words (View,
Expenses, Approval, Cash) are a new column `section` (`docs/04-schema.md` 13.2), null
elsewhere. Dependencies: 48 rows (each non-base right on its module's base, the three
dashboard rights on their module, and `pettycash.approve_day -> pettycash.approve_item`,
`pettycash.issue_negative -> pettycash.issue` kept from today).

What each right gates on the routes Python has today is in `docs/06-http-contract.md`
section 2.12 (the permission column of every changed row). Prompt 08 uses keys 12 to 31
(B19); 08b uses 7, 11, 14, 15, 32 to 42.

### 3.2 Role defaults

The four roles keep their names. Their defaults are today's translated by section 3.5, so
a person on a role keeps what they can do; the petty-cash rule of the notes adds
`pettycash.edit_own` where `pettycash.spend` is held.

| Role | Defaults |
|---|---|
| Owner | all 59, plus the hidden `organization.manage` (section 3.3) |
| Office admin | `dash.net`, `dash.gaps`, `revenue.view`, `revenue.correct`, `revenue.export`, `expenses.view`, `expenses.capture`, `expenses.correct`, `expenses.export`, `scheduled.*` (4), `savings.*` (4), `reports.view`, `reports.investment`, `reports.export`, `companies.*` (3), `vehicles.*` (4), `catalog.*` (4), `people.view`, `people.add`, `people.edit`, `people.block`, `people.sign_in`, `audit.view`: 37 |
| Fleet manager | `dash.net`, `dash.gaps`, `dash.pettycash`, `revenue.view`, `revenue.capture`, `revenue.correct`, `expenses.view`, `pettycash.view`, `pettycash.spend`, `pettycash.edit_own`, `reports.view`: 11 |
| Revenue clerk | `dash.gaps`, `revenue.view`, `revenue.capture`: 3 |

Rows: 60 + 37 + 11 + 3 = 111 (`tenancy.role_defaults`).

### 3.3 Hidden keys

`organization.manage` stays in `tenancy.permissions` with `catalogue = false`: not in
`GET /setup/access/catalog`, refused by the person save (`people_permission_unknown`),
granted only as an Owner role default. Organization settings, logo (O01 to O04) keep
requiring it, so only Owners manage them (question 59). An existing override that grants
it to someone else is dropped by the migration of section 3.5.

### 3.4 Legacy keys (derived, for v2.11 phones)

The 20 keys that leave the catalogue for good are rows of `tenancy.permissions` with
`catalogue = false` and no role default; a member holds one when they hold any of its
sources (`tenancy.permission_sources`). `tenancy.effective_permissions` (token, session,
`GET /auth/session`, `GET /setup/access/me`) includes them; `tenancy.assigned_permissions`
(the person document, the anti-escalation checks, the people list chips) does not. No
routine requires a legacy key after D2 to D4: each route's gate moves to the 59 (section
2.12 of `docs/06`). A v2.11 phone therefore shows the same screens as before, and the server
decides with the new rights. The derivation also bridges the build sessions: a routine
that D3 or D4 has not moved yet (for example the vehicle routines gated on
`vehicles.manage`) keeps working after D2's migration for everyone who holds a source of
the old key.

| Legacy key | Held when any of these is held |
|---|---|
| `dash.capture` | `dash.gaps` |
| `dash.float` | `dash.pettycash` |
| `dash.revenue` | `dash.net` |
| `dash.costs` | `dash.net` |
| `dash.commitments` | `dash.net` |
| `dash.investment` | `reports.investment` |
| `dash.edits` | `dash.net` |
| `revenue.no_earnings` | `revenue.capture`, `revenue.correct` |
| `expenses.setup` | `catalog.add`, `catalog.edit`, `catalog.stop` |
| `commitments.view` | `scheduled.view`, `savings.view` |
| `commitments.manage` | `scheduled.add`, `scheduled.edit`, `scheduled.pause`, `savings.add`, `savings.edit`, `savings.pause` |
| `companies.manage` | `companies.add`, `companies.edit` |
| `vehicles.manage` | `vehicles.add`, `vehicles.edit`, `vehicles.target` |
| `invest.view` | `reports.investment` |
| `invest.manage` | `vehicles.edit` |
| `people.manage` | `people.add`, `people.edit`, `people.block`, `people.sign_in` |
| `access.manage` | `people.edit` |
| `bills.view`, `bills.capture`, `bills.approve` | none (office bills are not in the notes; v2.11 already shows them as unavailable) |

`organization.manage` (section 3.3) is the 21st non-catalogue key. Totals:
`tenancy.permissions` 80 rows (59 catalogue, 20 legacy, 1 hidden), `permission_sources`
32 rows. When every installed phone is past v2.11, a migration drops the legacy rows (the
`useGroupping` pattern, question 22).

### 3.5 Translation of today's grants

One table, used by the development migration of D2 and by prompt 10 for the real data
(`tenancy.permission_translations (old_key, new_key)`, kept after the migration so the
data tool reads the same rows). For each membership: the old assigned set (today's
resolver, before the catalogue changes) is translated key by key, dependencies are added,
and the person's overrides are rewritten as the difference between that set and the new
role defaults (granted rows for extra keys, denied rows for missing ones). Every person
therefore keeps what they can do, except where the notes say otherwise.

| Old key | New keys |
|---|---|
| `dash.capture` | `dash.gaps` |
| `dash.float`, `dash.pettycash` | `dash.pettycash` |
| `dash.revenue`, `dash.net`, `dash.costs`, `dash.commitments`, `dash.edits` | `dash.net` |
| `dash.gaps` | `dash.gaps` |
| `dash.investment` | `reports.investment` |
| `revenue.view`, `revenue.capture`, `revenue.correct` | the same key |
| `revenue.no_earnings` | none (reasons are part of capture and change) |
| `expenses.view`, `expenses.capture`, `expenses.correct` | the same key |
| `expenses.setup` | `catalog.view`, `catalog.add`, `catalog.edit`, `catalog.stop` |
| `pettycash.spend` | `pettycash.spend`, `pettycash.edit_own` (v2.29 s5) |
| `pettycash.view_all`, `pettycash.approve_item`, `pettycash.approve_day`, `pettycash.issue`, `pettycash.issue_negative` | the same key (every other new petty-cash right starts off, v2.29 s5; question 60) |
| `bills.*` | none |
| `commitments.view` | `scheduled.view`, `savings.view` (v2.30 s3) |
| `commitments.manage` | `scheduled.add`, `scheduled.edit`, `scheduled.pause`, `savings.add`, `savings.edit`, `savings.pause` (v2.30 s3) |
| `reports.view` | `reports.view` |
| `reports.export` | `reports.export`, `revenue.export`, `expenses.export`, `pettycash.export` (today it also gates the screen exports, drift register row 4) |
| `companies.manage` | `companies.view`, `companies.add`, `companies.edit` |
| `vehicles.manage` | `vehicles.view`, `vehicles.add`, `vehicles.edit`, `vehicles.target` |
| `invest.view` | `reports.view`, `reports.investment`, `vehicles.view` (today it lists the vehicles read-only and opens the investment) |
| `invest.manage` | `vehicles.edit` |
| `people.view` | `people.view` |
| `people.manage` | `people.add`, `people.edit`, `people.block`, `people.sign_in` |
| `access.manage` | `people.edit` |
| `audit.view` | `audit.view` |
| `organization.manage` | kept only for Owners (section 3.3) |

Base rights a translated key needs are added (`pettycash.view` for every petty-cash key,
`revenue.view`, `expenses.view`, and so on), as the resolver would otherwise drop the key.

Built with one addition (D2, 2026-10-12): a right of the person's new role defaults that no
old key translates to and no right needs is added as well. Only the Owner role has such
rights: the petty-cash rights that start off for everyone else. Under the rule above an
organization's only Owner would get denied rows for them that nobody could ever lift (only
an Owner changes an Owner, and nobody changes their own access), so Owners keep every right
of their role. Two consequences of the table, kept as written: an Office admin who held
`reports.export` gains `pettycash.export` and with it `pettycash.view` (question 71), and
whoever held `people.manage` or `access.manage` gets `people.edit`, which also covers single
permissions and approval limits ("Edit a person and their access").

## 4. Released clients under these rules

What a v2.11 phone and today's web send, and what they get once 07b is built. Every row
here is a row of `tests/api/test_contract_released_clients.py` (D1 to D4 add them).

| Request | Answer after 07b | Why it still works |
|---|---|---|
| A01/A02 with number and PIN, trust by `deviceId` | as today for a right PIN on a trusted or untrusted device; a wrong PIN counts toward the scope's five; the fifth on a trusted device answers `423 paused` with `retryAfterSeconds` = the policy's lockout minutes x 60 and stays locked until a reset; every untrusted refusal (unknown, wrong, locked, forced reset, blocked) is the uniform 401 | the phone's paused screen offers the reset (`apps/mobile/src/auth/steps.tsx` `PausedStep`, `onReset`) |
| A03 with a code | as today; the third wrong code voids it and a new one is mailed; the phone's next try with the new code works | the phone retries with whatever code the person types |
| A04 to A09 | as today; a new PIN that is not four digits or is refused by the new rules answers `400 invalid_pin` with `minimumPinLength` 4; a reset removes every other trusted device and trusts the phone | the phone shows "Your organization needs a PIN of at least 4 numbers." and asks again (`authFlowState.ts` `pinTooShort`) |
| A10 to A13 | as today; refresh is refused while the PIN is locked on every device and after 90 days without use | refusal answers are the existing ones |
| `GET /setup/appearance` | adds `idleUnlockSeconds`; `lockoutThreshold` is served as 5 | additive; 5 is inside the phone's accepted 3..10 |
| `GET /setup/access/catalog` | the 59 rights in 12 groups | display only on the phone ("Your access"); the keys its tabs, cards and buttons check reach it through the token (`tests/api/test_contract_released_clients.py::test_the_session_keeps_the_keys_a_v211_phone_gates_on`); its Spend tab no longer shows for an Office admin, who loses `bills.view` (office bills were never served) |
| the token's `permission` claim, `GET /auth/session`, `GET /setup/access/me` | the held catalogue keys plus the legacy keys of section 3.4 | the phone's gates read keys it knows |
| R01 week, R02 dashboard | as today plus the new fields; cell `expected` is now the day target | additive; `expected` keeps its meaning |
| R03 capture: an amount at or above the threshold, or a reason with no amount | as today | |
| R03 capture: an amount below the threshold | `400` with the sentence of `revenue_low_needs_reason` | the phone shows `detail` and keeps the entry as not saved; a v2.11 phone cannot send an amount with a reason, so low days must be captured on the web (question 66) |
| R03 change of a saved record of today by a person with capture only | `403 revenue_correct_permission` | v2.30 s1; the phone shows `detail` |
| S18/S19 vehicle saves from today's web (no `fleetNumber`) | `400 vehicle_fleet_required` | DN-B10-1 requires it on every write; listed as a deliberate change |
| S33/S34 category saves with `bucket` | accepted; `bucket` is ignored | DN-B16-2 |
| S07/S08 people saves with today's keys | `400 people_permission_unknown` for a retired key | the web adopts the catalogue when it moves to the Python API (question 55); phones do not save people |
| P05 credit note from a v2.11 phone or today's web (own float, recorded with `pettycash.spend`) | `403 pettycash_credit_permission` unless the person holds `pettycash.credit`, which starts off (question 60) | the phone and the web show `detail`; the owner grants the right |
| P05 credit note without a payee or a reason | accepted (DN-B19-10) | today's clients send both; nothing they send is refused |
| P06 on cash given or a credit note | `400 pettycash_change_cash` | `canEdit` is false on those rows, so released clients do not offer it |
| P07/P08 on a credit note | `400 pettycash_credit_not_reviewed` | `canReview` is false on credit notes |
| P06/P09 by an approver on someone else's expense | `403` unless the person holds `pettycash.edit` or `pettycash.delete` (question 60) | the clients show `detail` |
| A sent-back expense in P02 and the `status=sentBack` filter | the word `sentBack`, as today (DEC-21) | unchanged wire |
