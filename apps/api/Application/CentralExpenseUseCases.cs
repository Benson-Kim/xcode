using System.Globalization;
using Auth.Application.Setup;
using Auth.Domain;
using Auth.Domain.Setup;

namespace Auth.Application.CentralExpenses;

public sealed class CentralExpenseUseCases(ISetupExecution execution, ICentralExpenseRepository repository, ISetupRepository setup,
    IFleetPostings postings, IClock clock)
{
    private const string View = PermissionKeys.ExpensesView;
    private const string Capture = PermissionKeys.ExpensesCapture;
    private const string Correct = PermissionKeys.ExpensesCorrect;
    private static readonly string[] ChangePermissions = [Capture, Correct];

    // The database counts, sums and cuts the stored rows (central and approved petty cash); only the scheduled rows, which
    // are worked out from the schedules, are held here. The page is found from per-day counts of both, so the stored rows
    // read are the page's own and the number of reads does not depend on how many rows the period holds.
    public Task<ExpenseLedgerDto> Ledger(DateOnly? from, DateOnly? to, string? source, string? q, int page, int pageSize, CancellationToken ct) =>
        execution.Read(View, async actor =>
        {
            SetupPagination.Validate(page, pageSize);
            var start = from ?? throw new ArgumentException("Choose the first and the last date.");
            var end = to ?? throw new ArgumentException("Choose the first and the last date.");
            if (start > end)
                throw new ArgumentException("The first date cannot be after the last date.");
            if (end.DayNumber - start.DayNumber > 366)
                throw new ArgumentException("Choose a period of at most 367 days.");
            var only = PostingSources.Parse(source);
            var text = q?.Trim();
            if (text?.Length > 200)
                throw new ArgumentException("Search for 200 characters or fewer.");

            // Nothing is posted after the business date.
            var through = end < actor.Today ? end : actor.Today;
            if (through < start)
                return new ExpenseLedgerDto(actor.Today, start, end, Permissions(actor), new(0m, 0m, 0m, 0m), [], page, pageSize, 0, 0m);

            var vehicles = await repository.Vehicles(actor, start, through, ct);
            var registrations = vehicles.ToDictionary(v => v.Id, v => v.Registration);
            IReadOnlyList<FleetPosting> everyScheduled = vehicles.Count == 0
                ? []
                : [.. (await postings.Scheduled(actor, vehicles, start, through, ct)).Where(p => p.Kind == RecurringKind.Cost)];
            var totals = await repository.StoredTotals(actor, start, through, ct);
            decimal Stored(PostingSource sourceOf) => totals.Where(t => t.Source == sourceOf).Sum(t => t.Total);
            var (central, pettyCash, scheduledSum) = (Stored(PostingSource.Central), Stored(PostingSource.PettyCash), everyScheduled.Sum(p => p.Amount));
            var figures = new ExpenseFiguresDto(central + pettyCash + scheduledSum, central, pettyCash, scheduledSum);

            // Scheduled rows have no recorder or holder, so only what they show is searched.
            var scheduled = only is null or PostingSource.Scheduled
                ? everyScheduled.Where(p => string.IsNullOrEmpty(text) || Matches(p, text, registrations[p.VehicleId], NoNames)).ToList()
                : [];
            var scheduledByDay = scheduled.GroupBy(p => p.Date).ToDictionary(g => g.Key, g => g
                .OrderBy(p => registrations[p.VehicleId], StringComparer.Ordinal).ThenBy(RowId, StringComparer.Ordinal).ToList());
            var filter = new LedgerFilter(start, through, only, string.IsNullOrEmpty(text) ? null : text);
            var days = only == PostingSource.Scheduled ? [] : await repository.StoredDays(actor, filter, ct);
            var storedByDay = days.ToDictionary(d => d.Date);

            // Each day lists its stored rows, then its scheduled ones. Walking the days newest first finds the part of the
            // page that is stored (a contiguous run of the stored rows) and the scheduled rows that fall in the page.
            var (low, high) = ((page - 1) * pageSize, page * pageSize);
            int? skip = null;
            var take = 0;
            var position = 0;
            var storedBefore = 0;
            var pageScheduled = new List<FleetPosting>();
            foreach (var day in storedByDay.Keys.Union(scheduledByDay.Keys).OrderByDescending(d => d))
            {
                var storedCount = storedByDay.TryGetValue(day, out var tally) ? tally.Count : 0;
                var scheduledOfDay = scheduledByDay.GetValueOrDefault(day) ?? [];
                var (storedStart, scheduledStart) = (position, position + storedCount);
                var dayEnd = scheduledStart + scheduledOfDay.Count;
                var (storedFrom, storedTo) = (Math.Max(low, storedStart), Math.Min(high, scheduledStart));
                if (storedFrom < storedTo)
                {
                    skip ??= storedBefore + storedFrom - storedStart;
                    take = storedBefore + storedTo - storedStart - skip.Value;
                }
                var (scheduledFrom, scheduledTo) = (Math.Max(low, scheduledStart), Math.Min(high, dayEnd));
                if (scheduledFrom < scheduledTo)
                    pageScheduled.AddRange(scheduledOfDay.Skip(scheduledFrom - scheduledStart).Take(scheduledTo - scheduledFrom));
                storedBefore += storedCount;
                position = dayEnd;
                if (position >= high) break;
            }

            var stored = skip is null ? [] : await repository.StoredRows(actor, filter, skip.Value, take, ct);
            var entries = stored.Select(r => (Posting: Posting(r), r.Registration))
                .Concat(pageScheduled.Select(p => (Posting: p, Registration: registrations[p.VehicleId])))
                .OrderByDescending(e => e.Posting.Date).ThenBy(e => e.Posting.Source)
                .ToList();
            var names = await repository.Names(PeopleOf(entries.Select(e => e.Posting)), ct);
            return new ExpenseLedgerDto(actor.Today, start, end, Permissions(actor), figures,
                [.. entries.Select(e => Row(actor, e.Posting, e.Registration, names))], page, pageSize,
                days.Sum(d => d.Count) + scheduled.Count, days.Sum(d => d.Total) + scheduled.Sum(p => p.Amount));
        }, ct);

    public Task<ExpenseOptionsDto> Options(DateOnly? date, CancellationToken ct) =>
        execution.ReadAny(ChangePermissions, async actor =>
        {
            var day = date ?? actor.Today;
            ValidateDate(actor, day);
            return new ExpenseOptionsDto(await repository.VehicleOptions(actor, day, ct), await setup.ExpenseItemOptions(day, ct));
        }, ct);

    public Task<ExpenseRecorded> Record(RecordExpense input, CancellationToken ct) =>
        execution.Write(Capture, async actor =>
        {
            var purchase = input.Purchase();
            purchase.Validate();
            var id = input.Id is { } given && given != Guid.Empty ? given : Guid.NewGuid();
            // A retried save answers with what the first attempt made, even if it has changed since.
            var existing = await repository.Purchase(id, ct);
            if (existing.Count > 0)
            {
                if (existing.Any(e => e.GroupId != id || e.RecordedBy != actor.UserId))
                    throw new CentralExpenseConflictException(null, "This expense was already saved by someone else. Reload and try again.");
                return new ExpenseRecorded([.. existing.OrderBy(e => e.Id).Select(e => e.Id)], existing[0].GroupTotal);
            }

            ValidateDate(actor, purchase.Date);
            var vehicles = await repository.VehiclesById(actor, purchase.Allocations.Select(a => a.VehicleId), ct);
            foreach (var allocation in purchase.Allocations)
            {
                var vehicle = vehicles.GetValueOrDefault(allocation.VehicleId) ?? throw new ArgumentException("Choose one of your vehicles.");
                if (!vehicle.ActiveOn(purchase.Date))
                    throw new ArgumentException($"{vehicle.Registration} was not in the fleet on that day.");
            }
            var item = await setup.ActiveExpenseItem(purchase.ExpenseItemId, purchase.Date, ct)
                ?? throw new ArgumentException("Choose an item that is in use.");

            var currency = await setup.Currency(ct);
            var rows = CentralExpense.Record(id, actor.OrganizationId, purchase, clock.UtcNow, actor.UserId);
            foreach (var row in rows)
            {
                repository.Add(row);
                await repository.RecordChange(actor, row, null, Snapshot(row),
                    SetupPagination.Automatic($"Recorded {Describe(row, vehicles[row.VehicleId].Registration, item.Name, currency)}"), ct);
            }
            return new ExpenseRecorded([.. rows.Select(r => r.Id)], purchase.Total);
        }, ct);

    public Task<ExpenseSaved> Change(Guid id, ChangeExpense input, CancellationToken ct) =>
        execution.WriteAny(ChangePermissions, async actor =>
        {
            var line = input.Line();
            var entry = await repository.Entry(actor, id, ct) ?? throw new KeyNotFoundException();
            if (entry.Matches(line))
                return Saved(entry);

            AuthorizeChange(actor, entry);
            if (line.Date != entry.Date && !Holds(actor, Correct))
                throw PermissionCatalog.Refusal("Changing the date of an expense", Correct);
            if (RequiredVersion(input.Version) != entry.Version)
                throw await Conflict(actor, entry, ct);
            var dateChanged = line.Date != entry.Date;
            if (dateChanged)
                ValidateDate(actor, line.Date);
            var vehicles = await repository.VehiclesById(actor, [entry.VehicleId, line.VehicleId], ct);
            if (dateChanged || entry.VehicleId != line.VehicleId)
            {
                var vehicle = vehicles.GetValueOrDefault(line.VehicleId) ?? throw new ArgumentException("Choose one of your vehicles.");
                if (!vehicle.ActiveOn(line.Date))
                    throw new ArgumentException($"{vehicle.Registration} was not in the fleet on that day.");
                if (entry.VehicleId != line.VehicleId && await repository.PurchaseHasVehicle(entry.GroupId, line.VehicleId, entry.Id, ct))
                    throw new ArgumentException($"This purchase already has a row for {vehicle.Registration}.");
            }
            if ((dateChanged || entry.ExpenseItemId != line.ExpenseItemId) &&
                await setup.ActiveExpenseItem(line.ExpenseItemId, line.Date, ct) is null)
                throw new ArgumentException("Choose an item that is in use.");

            var before = Snapshot(entry);
            entry.Change(line, clock.UtcNow, actor.UserId);
            await repository.RecordChange(actor, entry, before, Snapshot(entry),
                SetupPagination.Automatic($"Changed {await Describe(entry, vehicles[entry.VehicleId].Registration, ct)}"), ct);
            return Saved(entry);
        }, ct);

    public Task<ExpenseSaved> Remove(Guid id, RemoveExpense input, CancellationToken ct) =>
        execution.WriteAny(ChangePermissions, async actor =>
        {
            var reason = SetupPagination.Reason(input.Reason);
            var entry = await repository.Entry(actor, id, ct) ?? throw new KeyNotFoundException();
            AuthorizeChange(actor, entry);
            if (RequiredVersion(input.Version) != entry.Version)
                throw await Conflict(actor, entry, ct);

            var before = Snapshot(entry);
            var registration = (await repository.VehiclesById(actor, [entry.VehicleId], ct))[entry.VehicleId].Registration;
            var what = await Describe(entry, registration, ct);
            entry.Remove(reason, clock.UtcNow, actor.UserId);
            await repository.RecordChange(actor, entry, before, Snapshot(entry), SetupPagination.Automatic($"Removed {what}", reason), ct);
            return Saved(entry);
        }, ct);

    private static bool Holds(SetupActor actor, string permission) => actor.Permissions.Contains(permission);

    // Anyone who corrects changes any central row; someone who only captures changes their own, on the day they made them.
    private static bool CanChange(SetupActor actor, Guid recordedBy, DateOnly date) =>
        Holds(actor, Correct) || (Holds(actor, Capture) && recordedBy == actor.UserId && date == actor.Today);

    private static void AuthorizeChange(SetupActor actor, CentralExpense entry)
    {
        if (CanChange(actor, entry.RecordedBy, entry.Date)) return;
        if (entry.RecordedBy != actor.UserId)
            throw PermissionCatalog.Refusal("Changing someone else's expense", Correct);
        throw PermissionCatalog.Refusal("Changing an expense from an earlier day", Correct);
    }

    private static long RequiredVersion(long? version) =>
        version ?? throw new ArgumentException("Send the version of the expense you opened.");

    private static ExpensePermissionsDto Permissions(SetupActor actor) => new(Holds(actor, Capture), Holds(actor, Correct));

    private static void ValidateDate(SetupActor actor, DateOnly date)
    {
        if (date > actor.Today)
            throw new ArgumentException("An expense cannot be recorded for a future date.");
        if (date < actor.Today.AddDays(-3650))
            throw new ArgumentException("Choose a date in the last ten years.");
    }

    private static readonly IReadOnlyDictionary<Guid, string> NoNames = new Dictionary<Guid, string>();

    private static FleetPosting Posting(LedgerStoredRow r) => new(r.Source, RecurringKind.Cost, r.Date, r.VehicleId, r.Id, null, r.ItemName,
        r.ExpenseItemId, r.CategoryName, r.Bucket, r.Units, r.UnitAmount, r.Total, r.Note, r.RecordedBy, r.HolderId,
        r.GroupId is { } group ? new PostingGroup(group, r.GroupSize, r.GroupTotal, r.GroupUnits, r.GroupUnitAmount) : null, r.Version);

    private static string RowId(FleetPosting posting) => posting.Source == PostingSource.Scheduled
        ? $"{posting.Id}:{posting.Date.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture)}:{posting.VehicleId}"
        : posting.Id.ToString();

    private static IEnumerable<Guid> PeopleOf(IEnumerable<FleetPosting> rows) =>
        rows.SelectMany(p => new[] { p.RecordedBy, p.HolderId }).Where(id => id is not null).Select(id => id!.Value).Distinct();

    private static bool Matches(FleetPosting posting, string text, string registration, IReadOnlyDictionary<Guid, string> names)
    {
        bool Has(string? value) => value?.Contains(text, StringComparison.OrdinalIgnoreCase) == true;
        return Has(registration) || Has(posting.Name) || Has(posting.CategoryName) || Has(posting.Note) ||
            (posting.RecordedBy is { } by && Has(names.GetValueOrDefault(by))) ||
            (posting.HolderId is { } holder && Has(names.GetValueOrDefault(holder)));
    }

    private static ExpenseLedgerRowDto Row(SetupActor actor, FleetPosting p, string registration, IReadOnlyDictionary<Guid, string> names)
    {
        var canChange = p.Source == PostingSource.Central && CanChange(actor, p.RecordedBy!.Value, p.Date);
        return new ExpenseLedgerRowDto(RowId(p), PostingSources.Word(p.Source), p.Date, p.VehicleId, registration, p.ExpenseItemId, p.Name,
            p.CategoryName, p.Bucket!.Value, p.Units, p.UnitAmount, p.Amount, p.Note,
            p.RecordedBy is { } by ? names.GetValueOrDefault(by, "") : null,
            p.HolderId is { } holder ? names.GetValueOrDefault(holder, "") : null,
            p.Source == PostingSource.Scheduled ? p.Id : null,
            p.Group is { Size: > 1 } g ? new ExpenseGroupDto(g.Id, g.Size, g.Total, g.Units, g.UnitAmount) : null,
            p.Version, canChange, canChange);
    }

    private async Task<CentralExpenseConflictException> Conflict(SetupActor actor, CentralExpense entry, CancellationToken ct)
    {
        var vehicles = await repository.VehiclesById(actor, [entry.VehicleId], ct);
        var posted = (await postings.Load(actor, [.. vehicles.Values], entry.Date, entry.Date, ct))
            .SingleOrDefault(p => p.Source == PostingSource.Central && p.Id == entry.Id);
        if (posted is null)
            return new CentralExpenseConflictException(null);
        var names = await repository.Names(PeopleOf([posted]), ct);
        return new CentralExpenseConflictException(Row(actor, posted, vehicles[entry.VehicleId].Registration, names));
    }

    private static ExpenseSaved Saved(CentralExpense entry) => new(entry.Id, entry.Version);

    private async Task<string> Describe(CentralExpense row, string registration, CancellationToken ct) =>
        Describe(row, registration, (await repository.ItemNames([row.ExpenseItemId], ct)).GetValueOrDefault(row.ExpenseItemId, "an item"),
            await setup.Currency(ct));

    // The change log names the vehicle, the day and what the money was for, as in "Recorded central expense on KDA 482M
    // for 28 Sep 2026: Tyres, KES 16,800".
    private static string Describe(CentralExpense row, string registration, string item, string currency) =>
        $"central expense on {registration} for {row.Date.ToString("d MMM yyyy", CultureInfo.InvariantCulture)}: {item}, " +
        $"{currency} {row.Total.ToString(decimal.Truncate(row.Total) == row.Total ? "#,##0" : "#,##0.00", CultureInfo.InvariantCulture)}";

    private static object Snapshot(CentralExpense row) => new
    {
        row.Id,
        row.Date,
        row.VehicleId,
        row.ExpenseItemId,
        row.Units,
        row.UnitAmount,
        row.Total,
        row.Note,
        row.GroupId,
        row.GroupSize,
        row.GroupTotal,
        row.GroupUnits,
        row.GroupUnitAmount,
        row.RecordedBy,
        row.RecordedAt,
        row.UpdatedBy,
        row.UpdatedAt,
        row.RemovedBy,
        row.RemovedAt,
        row.RemovalReason,
        row.Version
    };
}
