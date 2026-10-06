# XCODE backlog

Requests and observed problems waiting to be scheduled, newest first. Each entry says what is needed, why, a proposed first version, the decisions still open, and notes for developers.

---

## 2. Revenue capture jumps to another vehicle without warning

*Observed 6 Oct 2026 on staging (web app).*

### What happens
Someone is entering revenue for **vehicle 2** for a date. As soon as they save, the capture window switches to **vehicle 1**, because vehicle 1 is also missing that date. Nothing says the vehicle has changed. It is easy to type vehicle 2's next figure into vehicle 1.

If vehicle 1 also has an older missing day, the window opens that older day instead ("Fill … first"). So the vehicle and the date change together.

### Why it happens
This is how capture was designed, not a coding mistake. After each save the app moves to the next vehicle that is still missing the same day. It goes in grid order and wraps round to the top, so a whole day can be filled across the fleet in one pass. The design is reasonable, but doing it silently is surprising and risks wrong entries.

### What we want
**Decided 6 Oct 2026: let the person choose how to work.** The two ways are:

| Way of working | After a save, the window moves to |
|---|---|
| **One day, all vehicles** (today's behaviour) | The next vehicle still missing the same day. |
| **One vehicle, all its days** | The same vehicle's next missing day, oldest first. It never moves to another vehicle on its own. |

- **Visible choice.** The choice sits in the capture window, so it can be changed mid-way. The app remembers each person's last choice.
- **Never silent.** In either way, the window says what it is moving to before or as it opens. For example, "Saved KDA 123A. Next: KDB 456B, Fri 3 Oct", with a way to stop.
- **Clear end.** When nothing is left in the chosen way (the day is complete for every vehicle, or the vehicle has no missing days), the window closes and says so.
- **Vehicle shown prominently.** The registration appears prominently in the capture window, so it is obvious which vehicle is being filled.
- **Same in both apps.** The web and phone apps behave the same.

Options considered and not chosen:
- Always stay on the same vehicle, with an explicit "Next vehicle" button.
- Keep the fleet-wide pass with a confirmation before each switch.

### Notes for developers
- Web: `advance()` in `apps/web/components/RevenuePage.tsx` (around lines 198–211) runs after every save.
  - It calls `nextMissing()` (around 75–81) to find the next vehicle missing `saved.target`, wrapping round the grid.
  - It then calls `openAt()` (around 67–73), which sends the person to that vehicle's earliest gap when one exists.
- Mobile keeps its own copy of the capture rules in `apps/mobile/src/shell/RevenueScreen.tsx`. Check whether it behaves the same, and change both together. Remediation Phase 5, item 2, plans to move these rules into the shared package; doing it after that move avoids fixing it twice.
- Some existing tests assert the automatic move to the next vehicle. Update them deliberately. Do not delete them.

---

## 1. Bulk import and export of vehicle data

*Requested 6 Oct 2026.*

### The problem
Fleets moving to XCODE from another application bring their history with them. Picture a vehicle with 8 months of records in the old system. Today every one of those days has to be typed in by hand, one at a time.

XCODE only lets a vehicle's days be filled in date order, oldest gap first. That makes 8 months about 240 entries for that one vehicle, entered strictly in sequence. It is not feasible for one vehicle, let alone a fleet.

### What we need
- **Import** vehicles and their history from a file: vehicle details plus each day's revenue or the reason there was none.
- **Update** existing vehicles' details from a file, not one form at a time.
- **Export** the same data to a file, for backups, reporting, or moving data out.
- File types requested: Excel (.xlsx), CSV, plain text (delimited .txt), and SQL.

### Proposed first version
- **Template.** Download a template, fill it in (or paste in the old system's export), then upload it.
- **Preview first.** Before anything is saved, show which rows will be added, updated or skipped, and which have problems, with the reason for each.
- **All or nothing.** Nothing is saved until the person confirms, and then the whole file is saved together. A failure part-way through leaves nothing half-imported.
- **Safe to repeat.** Uploading the same file again must not create duplicates. Vehicles are matched by registration, and daily records by vehicle and date.
- **Traceable.** The change history records who imported which file and when.
- **Export.** Vehicles, and revenue for a chosen date range, to Excel or CSV.

### Decisions needed
- **SQL files.** Running an SQL file from another system is a serious risk: it could change or delete anything in the database. Choose one:
  - Accept Excel, CSV and txt only, and export the old system's data to CSV first.
  - Accept .sql files as data only: read the rows out of INSERT statements, never run them.
- **Conflicts.** When the file and XCODE both have a record for the same vehicle and day, should the import overwrite it, keep XCODE's, or flag it for review?
- **Fields.** Which vehicle details are needed (registration, company, joined and left dates, targets, investment)? Which daily fields (amount, reason such as off-road, note)?
- **Who may import.** Owners only, or anyone allowed to manage vehicles or capture revenue?
- **Limits.** The largest file or number of rows accepted in one go.

### Notes for developers
- Nothing for import or export exists today: there is no CSV or Excel handling in the API or the web app.
- An import must respect, or deliberately and visibly bypass, the rules capture enforces:
  - The API refuses a day while an earlier day for the same vehicle is missing (`RevenueEarlierDayMissingException`, `apps/api/Application/RevenueContracts.cs`). Write each vehicle's records in date order, or validate the whole range together.
  - No records before a vehicle's joining date, after its leaving date, or after the organization's business date.
- Go through the domain model, not raw SQL. Keep the strengths listed in `CLAUDE.md`:
  - RevenueRecord's validating constructor, version checks and repeat-safe saves;
  - tenant isolation (rows only go into the importer's organization and data scope);
  - change-log entries.
- Large imports grow the history tables quickly. The Phase 4 scalability work (paging the revenue grid, the change-log query) becomes more important once imports exist.
