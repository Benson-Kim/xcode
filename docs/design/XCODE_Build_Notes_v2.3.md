# XCODE Web, running change notes for the developer

Running record of every change made after the last notes sent to the developer (Web v2.28, see `developer-notes-v2.28.md`). Newest version first. Where a later version overrules an earlier one, the earlier entry is corrected in place and marked. Mobile is parked at v2.11 and has none of this.

Prototype: XCODE Web, same link as before. The prototype is the reference for layout and behaviour; this file is the reference for rules and data.

---

## v2.33, 10 October 2026

### 1. Sign in

A person signs in with a mobile number and a 4 digit PIN. Email carries a 6 digit code whenever the system needs proof beyond the PIN.

| Case | Steps |
|---|---|
| Trusted device | The device remembers its person and shows their name. PIN only. |
| Known person, new device | Mobile number, PIN, then a code sent to their email. "Trust this device" is ticked by default. |
| First sign in | Mobile number, code, choose a PIN, repeat it. No PIN exists before this. |
| Forgotten PIN | "Forgot PIN", code, new PIN, repeat it. |
| Forced reset | Same as forgotten PIN; the mobile number step goes straight to the code. |
| Five wrong PINs | The PIN is locked on every device. Only a reset with a code unlocks it. |
| Blocked person | Refused at the mobile number step. |

Screen rules:

- Mobile number comes first, alone, with "Continue". The system then decides the next step.
- The PIN field submits itself on the fourth digit; the code field on the sixth. Enter also submits.
- On a device that is not trusted, the PIN step shows the number only, never the person's name.
- The code step shows the email with the middle hidden, "Send a new code" and "Back".
- No helper text on any step.

Rules to enforce on the server:

| Rule | Value |
|---|---|
| PIN | 4 digits, stored hashed with a per person salt. Never returned by any API. |
| Refused PINs | One digit four times, a run up or down such as 1234 or 4321, the last four digits of the person's own number, and the PIN being replaced. |
| Wrong PIN limit | 5 in a row, counted per person across all devices. Then locked until reset. Reset to zero on a correct PIN. |
| Code | 6 digits, single use, valid 10 minutes, tied to the person, the purpose and the device that asked. |
| Wrong code limit | 3, then the code is void and a new one is sent. |
| New code | Not more than one a minute and five an hour per person. |
| Trusted device | A long random token kept on the device, stored hashed on the server with device name, date trusted and last used. Expires after 90 days unused. |
| After a PIN reset | Every trusted device of that person is removed. The device used for the reset can be trusted again in the same step. |
| After a block | Trusted devices removed and open sessions ended at once. |
| Idle | Ask for the PIN again after 15 minutes without activity. Work typed but not sent is kept. |
| Unknown number | Same wording and timing as a wrong PIN where possible, and limit tries per device and per address. |

- A new person is created with no PIN. Remove the default PIN of 0000.
- "Email for codes" on the person is required and must be unique.
- The code email holds the code, the purpose and the device name, nothing else.

Change log entries: "PIN set at first sign in", "PIN reset with a code", "PIN changed", "PIN locked after 5 wrong tries", "Device trusted", "Trusted device removed", "PIN reset required". Ordinary sign ins are not logged there; keep them in a separate sign in history.

### 2. Profile menu

- "Change PIN": current PIN, new PIN, repeat. Same PIN rules.
- "Trusted devices": the person's own devices with date trusted and last used, "This device" marked, and Remove on each.
- "Sign out" on a trusted device returns to the PIN screen for that person.

### 3. People and access

- Person form has a fourth menu item, "Sign in": PIN status, last sign in, where codes go, and the trusted devices.
- New right `ppl.signin`, "Reset a PIN and remove devices". 59 rights in all. With it: "Make [name] reset the PIN" (removes their devices and forces a new PIN at the next sign in), Remove on a device, Remove all. These act at once and are logged; they do not wait for Save.
- People list status is now one of: Active, Not signed in yet, PIN reset due, Locked, Blocked.
- Saving a new person says they set a PIN at first sign in.

### 4. Review aids in the prototype, not to be built

- The prototype opens already signed in as the owner. "Sign out" in the profile menu leads to the sign in screens.
- The dashed box on the sign in screen lists people with their numbers and PINs, and shows the code that would be in the email. It exists only so the flows can be clicked through.
- "Viewing as" in the profile menu, as before.

---

## v2.32, 10 October 2026

### 1. Targets are dated and never roll back

- A vehicle holds a list of target sets. Each set is a start date and seven day figures, Monday to Sunday. A set applies from its start date until the next set starts.
- The target for any day is read from the set in force on that day. Every gap, report and export uses this, so a new target never changes an earlier week.

| Rule | Detail |
|---|---|
| Start date | Today or later. Never in the past. The pop up opens on next Monday; the arrows move it. |
| A set that has started | Cannot be edited or removed, by anyone. To correct it, add a new set from today. |
| A set that has not started | Can be replaced (save again on the same date) or removed. |
| Same as the set in force | Refused, so no empty changes are logged. |
| Log | "Target set, [registration]": the figures before, the figures after and the start date. Removal of a future set is logged too. |

- Screens: Vehicles has a "Targets" action per row, with its own right `veh.target` ("Set targets"). The pop up carries the start date first, the seven figures, the week total, then the history, newest first, with "Now" on the set in force and "Remove" on any that has not started.
- The Vehicles table shows the weekly target in force, and under it the next one with its start date when one is waiting.
- New vehicle: the seven figures are entered on the form and start today. Edit vehicle no longer holds targets: fleet number, PSV company and initial investment only.
- This replaces the single set of day targets in v2.31 section 1 and closes its note on target history.
- "Revenue against target" in Reports now sums the day targets across the period, using the set in force on each day.

### 2. Initial investment is optional

- It may be left empty on a new vehicle and cleared on an existing one. Store it as empty, not zero.
- Vehicles table shows a blank. The Investment report lists the vehicle last with no "Recovered" figure and leaves it out of nothing else.

### 3. How far back a person may change records

Each person has a limit on the dates they may add, change or delete records for.

| Setting | Meaning |
|---|---|
| No rolling limit | Any date, unless a fixed date is set |
| A number of days back | Today and N days before it. 0 is today only. Moves forward every day. |
| A number of months back | The same day N months ago. If that day does not exist, use the last day of that month. |
| Never before a date | A fixed date that does not move. Use it to close the books up to a date. |

- A rolling limit and a fixed date can both be set. The later of the two is the earliest date allowed.
- New people start on 7 days back.
- Applies to: capturing or changing revenue; adding, editing, deleting or reopening a petty cash expense; adding or editing a central expense; issuing cash, credit notes and deleting a cash entry.
- Does not apply to: viewing, reports and exports; approving, rejecting or sending back, so old entries can still be decided; schedules, savings and setup.
- On screen: the date arrows in a pop up stop at the limit. A new record started from an older day opens on the earliest date allowed. Edit, Delete and Reopen do not show on rows older than the limit, and revenue cells older than it are not buttons.
- Enforce it on the server on every write, using the record's date, not the date of the request. Offline entries that sync late are checked against the limit at the time they were captured.
- Stored on the person as mode (none, days, months), the number, and the optional fixed date. Changes are logged with access changes.

### 4. People and access redesign

List, one row a person:

| Column | Shows |
|---|---|
| Person | Initials, name, a "Float" or "Default float" tag, then job and mobile number |
| Access | One chip per module the person can reach. Filled when they hold every right in it; outlined with "4 of 20" when partial. "Everything" for all 58. |
| Vehicles | All vehicles, or the count |
| Can change | The limit in words: "Any date", "2 days back", "1 month back, not before 14 September 2026" |
| Status | Active or Blocked, with the last sign in under it |
| Actions | Edit, Block |

Person form, a wide pop up with a side menu and one pane at a time:

| Menu item | Pane |
|---|---|
| Details | Names, job, mobile number, email for codes, petty cash float |
| Vehicles and dates | Vehicles the person can see; how far back they can change records. The menu shows the summary of both. |
| Access | The tick cards, one per module, unchanged in content. The menu lists every module with a live count: "All", "4 of 20" or "Off". Choosing a module jumps to its card. |

- A save error opens the pane that holds the problem.
- The rights catalogue is unchanged apart from `veh.target`. Total is 58.

---

## v2.31, 10 October 2026

### 1. Vehicle form: targets per day (target storage replaced in v2.32)

| Field | Rule |
|---|---|
| Registration | New vehicle only. Format KDN 204B. Unique. |
| Fleet number | Required. Unique within a PSV company. |
| PSV company | Choose one. |
| Initial investment, KES | As before. |
| Target per day, KES | Seven figures, Monday to Sunday. All seven required, because vehicles work every day. "Same every day" copies the first figure typed into all seven. |
| Target for the week | Shown, never typed: the sum of the seven. |

- Data: the vehicle stores seven day targets. The weekly target is their sum and is no longer entered. Migration: each existing weekly target ÷ 7 into every day, then the owner adjusts.
- Keep a history of targets with the date each set took effect, so a past week is always judged against the targets that applied then. The prototype does not model this.
- A change is logged as "Target per day, [registration]" with the seven figures before and after.
- Remove from the build: "It shows on reports and the dashboard straight away.", "Kenyan format, for example KDA 482M.", "Revenue you expect in a Monday to Sunday week.", "Missing revenue days are only counted from this date."
- "In the fleet from" is not in the prototype. Still open with the owner.

### 2. Revenue: gap as a coloured figure

- The gap is a signed figure with no words: "+3,050", "−16,100", "0". The sign carries the meaning; colour reinforces it.

| Colour | When |
|---|---|
| Green | Revenue at or above target |
| Amber | Below target by up to 10 per cent of the target |
| Red | Below target by more than 10 per cent |

- 10 per cent is a system setting, not a constant in code.
- The gap for a vehicle and week = revenue − the sum of the day targets for the days that count so far (every day up to yesterday, plus today once it has a record). A finished week uses all seven.
- The pop up shows the target of the day on screen, so Friday and Sunday can differ.
- Headline bar and export use the same signed figure.

### 3. Expense categories: three levels, nothing built in

Main category → Category → Item. All three are set up by the owner. The system ships with none.

- Remove "Counts as" and the three built in groups (Repairs and maintenance, Recurring charges, Loan repayments) as fixed system values. They may exist only as ordinary records the owner created.
- Setup, Expense items has three tabs: Main categories, Categories, Items.

| Form | Fields |
|---|---|
| Main category | Name. Unique. |
| Category | Name. Main category, with "No main category" as the first choice. |
| Item | Name. Category. Unchanged. |

- A category may have no main category. This is how expenses migrated from the old system arrive: import the item and category, leave main category empty, set it later. Setting it later regroups every past expense under it at once, because expenses point to the item, the item to the category, and the category to the main category. Nothing is stored on the expense itself.
- Categories with no main category show "Not set", and the Categories tab counts them.
- Reports: "Net by vehicle" has one money out column per main category, plus "No main category" when it holds money. "Money out" lists main category, category, item, and its headline figures are the main category totals. No report may depend on a fixed list of categories.
- Rights are unchanged: the Expense items rights cover all three levels.

---

## v2.30, 10 October 2026

### 1. Revenue: the week grid is the chosen design

Decided by the owner: the week grid with a pop up for one vehicle and one day (Option B in v2.29). The day sheet and the review switch are removed. Build this one only.

| Part | Rule |
|---|---|
| Page | The week, one row a vehicle, one column a day, then Week total and Gap to target. No Actions column. |
| Cell | Amount, with the reason in small type under it when below 4,000. Reason chip for a no revenue day. "Missing" for a past day with no record, "Due" for today. |
| Capture | "Capture revenue" opens the oldest missing day, or today, on the first vehicle with no record. A tap on a cell opens that vehicle and day. |
| Pop up | Title is registration and fleet number. Date with previous and next arrows. Day target. Revenue, KES. Reason buttons, shown only while the amount is below 4,000. Cancel, Save. |
| After Save | A new capture moves to the next vehicle with no record for that day and closes when none is left. A correction closes. |
| Rights | `rev.capture` to fill a day with no record, `rev.edit` to change a saved one. A cell the person cannot change is not a button. |

### 2. Revenue: target shown as a gap (display and day target corrected in v2.31)

- The target progress bar is gone. The grid shows one figure per vehicle, "Gap to target". See v2.31 section 2 for how it is written and coloured.
- Vehicles work all seven days. Day targets are set per day on the vehicle; see v2.31 section 1.
- The gap is measured against the target for the days that count so far: every day of the week up to yesterday, plus today once it has a record. A missing day and a no revenue day both count against the vehicle.
- Headline bar: Revenue, then "Gap to target so far" (or "Gap to target" for a finished week), Below 4,000, Missing days. "Target" and "Reached %" are removed from the bar.
- Pop up shows "Day target" in place of "Same day last week".
- Export of the week: columns end Week total, Target to date (or Target), Gap. Gap is a signed number in Excel.
- Not changed: the Reports page "Revenue against target" still compares against the full target for its period.

### 3. Savings split from Scheduled expenses

- Two pages and two menu items. "Scheduled expenses" stays under Expenses. "Savings" is its own item between Expenses and Reports. The two tabs are gone.
- Each page has a headline bar. Scheduled expenses: "Due in [month]", Running, Paused. Savings: "Savings balance", "Saved in [month]", Running, Paused.
- Rights split, 57 in all:

| Key | Right |
|---|---|
| `sched.view` | View scheduled expenses |
| `sched.add` | Add a scheduled expense |
| `sched.edit` | Edit a scheduled expense |
| `sched.pause` | Pause or resume |
| `sav.view` | View savings |
| `sav.add` | Add a saving |
| `sav.edit` | Edit a saving |
| `sav.pause` | Pause or resume |

- Migration: anyone holding a `sched.*` right gets the matching `sav.*` right, so nobody loses access. After that the two are set apart.
- Data model is unchanged: one schedule record with `kind` expense or saving. Change log entries now read "Saving, [name]" or "Scheduled expense, [name]".

### 4. Saving and scheduled expense pop ups: no explanation

The pop up carries labels, fields and figures only. From the build, remove:

- "It posts to the vehicles you choose on every due date."
- "Optional. Up to 200 characters." and the optional field it belongs to.
- "The total. Split it across vehicles below"
- "Savings are set aside every week or every month."
- "On or after 1 Oct 2026. A start before today also adds the earlier postings."
- "Split the amount across one or more vehicles. It must add up exactly."
- "Enter the amount and select vehicles to enable Split equally."
- "Enter the amount and choose vehicles to see the postings."
- The "What will post" block.

Saving pop up, field by field, as in the prototype: Name. Amount per vehicle. Runs (every day, week, month, year) with its day or date. Save (every run, or only when revenue reaches a target, then the revenue figure and the period measured). Vehicles (all, or tick). Opening balance tick, then the date and an amount per vehicle. One line at the foot: next run date, vehicle count and the total per run. Removed in v2.30: the sentence describing the next revenue check, and the words "Brought in from another system".

The build departs from the locked model in three ways. Follow the model unless the owner says otherwise:

| Build | Locked model |
|---|---|
| One total, split across vehicles to balance | An amount per vehicle. Nothing to split, nothing to balance. |
| "Starts" date, and a past start adds earlier postings | No start date and no back posting. A schedule runs from its next run date. Balances from before come in through the opening balance. |
| "No end date" tick | No end date exists yet. Open question with the owner. |

---

## v2.29, 10 October 2026

### 1. Revenue: a low day needs a reason

- Rule: a day's revenue for a vehicle below KES 4,000 cannot be saved without a reason. Zero or blank with a reason is a no revenue day, as before.
- Reasons are the same list as no revenue: Garage, Arrest, No Crew, Other. One list, not two.
- 4,000 is one figure for the whole fleet. Build it as a system setting, not a constant in code.
- Record shape per vehicle per day:

| Case | Stored |
|---|---|
| 4,000 or more | `amt` |
| 1 to 3,999 | `amt` and `reason` |
| Nothing came in | `reason` only |
| Not captured | no record |

- Display everywhere revenue is shown per day: the amount, with the reason in small type under it. A no revenue day keeps its reason chip.
- Validate on the server as well: reject `amt < threshold` with no reason.
- A low day still counts as revenue in every total. It is counted in a new figure, "Below 4,000" (low days plus no revenue days), which replaces "No revenue days" on the Revenue bar and in the export.
- Savings revenue rule is unchanged: it sums `amt`; a reason only day counts as zero.
- Change log: a new capture logs once; changing a saved figure or reason logs before and after, for example "KES 7,900" to "KES 2,500, Garage".

### 2. Revenue module (settled in v2.30)

Two options were built for review. The owner chose the week grid; see v2.30 section 1. The day sheet is dropped. The old capture pop up and the row edit on the week grid are removed. Search matches registration or fleet number.

### 3. Pop ups

- Any pop up with a date carries the date first, as previous, date, next. No date field or date list lower in the form. Applies to Record spending, Edit spending, Record expense, Edit expense, Issue cash, Credit note, and the revenue pop up. Earliest date is the first day with records, latest is today.
- A petty cash expense can now have its date changed in the pop up; the change is logged.
- Exception: the savings opening balance date stays as day, month, year lists, because it can be years back.
- No helper sentences under fields and no optional note fields, on any pop up. Remove: "Use a minus sign for a refund.", "Use a minus sign for money coming back.", "Why the money was paid out.", "What the vehicle handed in for the day, after the crew settle fuel and their own pay.", "No record yet from ... You can fill it when you have it.", the optional Note on Record spending.
- Kept, because they are figures and not instructions: totals, the balance check on a split, "Cash on hand" beside the manager, "Day target" on revenue (corrected in v2.30, was "Same day last week").
- Credit note: fields are date, manager, amount, reason. Reason is no longer forced. No "The payee should pay this back" tick box. No "Paid to" field; a credit note belongs to a manager's float and reduces cash, as in the v2.28 notes.
- Money is whole shillings with thousands separators. "Expected KES 16,857.14" is wrong; show "KES 16,857".

### 4. Vehicles: fleet number

- New field `fleet` on a vehicle, text, required, unique within a PSV company.
- Vehicle form: Fleet number sits after Registration and can be edited; changes are logged. Vehicles table has a Fleet number column.
- Every vehicle drop down shows registration and fleet number only, for example "KDG 412M · 14". No company or SACCO name.
- Migration: existing vehicles need a fleet number before the drop down reads well; until then show the registration alone.

### 5. Petty cash: rights and three new actions

Rights are now 20 for petty cash. "Edit" and "Delete" rights apply before approval (waiting or sent back). After approval only `pc.delete_approved` and `pc.reopen` apply. Enforce every right on the server and cut every list to the vehicles the person can see, as before.

| Key | Right | New |
|---|---|---|
| `pc.see` | View petty cash | |
| `pc.view` | See every manager's float | |
| `pc.reports` | View petty cash reports | |
| `pc.export` | Export petty cash | |
| `pc.spend` | Add an expense | relabelled |
| `pc.spend_other` | Add for another manager | yes |
| `pc.edit_own` | Edit own expense | yes, was implied by `pc.spend` |
| `pc.edit` | Edit any expense | |
| `pc.delete_own` | Delete own expense | yes |
| `pc.delete` | Delete any expense | yes |
| `pc.delete_approved` | Delete after approval | yes |
| `pc.sendback` | Send an expense back | yes |
| `pc.approve_item` | Approve an expense | |
| `pc.approve_day` | Approve a whole day | |
| `pc.reject` | Reject an expense | |
| `pc.reopen` | Reopen an approved or rejected expense | |
| `pc.issue` | Issue cash | |
| `pc.negative` | Issue cash to a float below zero | |
| `pc.credit` | Record a credit note | |
| `pc.cash_delete` | Delete a cash entry | yes |

Migration of existing people: anyone with `pc.spend` gets `pc.edit_own`, so nobody loses what they could do. Everything else new starts off.

Rules for the new actions:

- Send back. Needs a reason. The expense stays waiting, shows "Sent back" with the reason, still counts as spent, cannot be approved or ticked, and is left out of "Approve day". Saving an edit clears it and sends it for approval again. Reopen also clears it. Stored as a reason on the waiting entry (`back`), not a new status, so no total changes.
- Reject stays the final no: the manager carries the cost and it leaves the Expenses figure.
- Delete before approval: confirm only, no reason. Delete after approval: reason required, and the expense leaves Central expenses. A rejected expense cannot be deleted; reopen it first. Every delete is written to the change log with the amount, status and reason. Keep deleted rows in the database, flagged, not removed.
- Delete a cash entry (cash issued or credit note): reason required, logged, balances recalculate.
- Add for another manager: without it a person records only against their own float, so a person with no float and without this right cannot add. With it, and "See every manager's float", the expense goes to the manager on screen, or the form asks.
- Deleting or editing one part of a shared purchase leaves the other parts; their "Shared by N vehicles" note is recounted.

Layout: on a row, Edit and Approve stay as buttons. Send back, Reject and Delete sit under "More" when two or more apply; a single one shows as a button. The Cash received table has an Actions column for people with `pc.cash_delete`. In the person form the Petty cash card spans the full width with four sections: View, Expenses, Approval, Cash.

---

## Not done, flagged

- Central expenses has no delete yet.
- Schedules have no end date. Owner to decide.
- "In the fleet from" date on a vehicle. Owner to decide.
- Whether the limit on how far back should also stop approving, rejecting and sending back. Today it does not.
- Main categories and categories cannot be deleted or merged yet.
- Codes go by email only. A person with no email on their phone cannot do a first sign in or a reset. SMS is not built.
- Mobile has none of v2.19 to v2.33.
