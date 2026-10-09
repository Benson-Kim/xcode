using System.Globalization;
using Auth.Application.Setup;
using Auth.Domain;

namespace Auth.Application.PettyCash;

public sealed class PettyCashUseCases(ISetupExecution execution, IPettyCashRepository repository, ISetupRepository setup, IClock clock)
{
    private const string Spend = PermissionKeys.PettyCashSpend;
    private const string ViewAll = PermissionKeys.PettyCashViewAll;
    private const string ApproveItem = PermissionKeys.PettyCashApproveItem;
    private const string ApproveWholeDay = PermissionKeys.PettyCashApproveDay;
    private const string Issue = PermissionKeys.PettyCashIssue;
    private const string IssueNegative = PermissionKeys.PettyCashIssueNegative;
    private static readonly string[] ReadPermissions = [Spend, ViewAll];
    private static readonly string[] RecordPermissions = [Spend, Issue];
    private static readonly string[] ChangePermissions = [Spend, Issue, ApproveItem];
    private static readonly string[] DashboardPermissions = [PermissionKeys.DashFloat, PermissionKeys.DashPettyCash];

    // A week starts on the organization's first day of the week, as revenue weeks do. A first and last day show any
    // period instead: opening at the start of the first day, closing at the end of the last.
    public Task<PettyCashOverviewDto> Overview(DateOnly? date, string? period, Guid? holderId, DateOnly? first, DateOnly? last,
        CancellationToken ct) =>
        execution.ReadAny(ReadPermissions, async actor =>
        {
            DateOnly day, from, to;
            string shown;
            if (first is not null || last is not null)
            {
                (from, to) = Range(actor, first, last);
                (day, shown) = (to, from == to ? "day" : "range");
            }
            else
            {
                day = Day(actor, date);
                var week = period?.Trim() switch
                {
                    null or "" or "day" => false,
                    "week" => true,
                    _ => throw new ArgumentException("Choose a day or a week.")
                };
                from = week ? StartOfWeek(day, await setup.FirstDayOfWeek(ct)) : day;
                to = week ? from.AddDays(6) : day;
                shown = week ? "week" : "day";
            }
            var holders = await VisibleHolders(actor, ct);
            var selected = Selected(holders, holderId);
            var tallies = await repository.Tallies(actor, [.. selected.Select(h => h.Id)], from, to, ct);
            var limit = await repository.ApprovalLimit(actor.UserId, ct);
            return new PettyCashOverviewDto(actor.Today, day, shown, from, to, Permissions(actor, limit), holders,
                Figures(tallies), [.. selected.Select(h => Float(h, tallies))]);
        }, ct);

    // Both days or neither, at most 367 days, starting no later than the business date.
    private static (DateOnly From, DateOnly To) Range(SetupActor actor, DateOnly? first, DateOnly? last)
    {
        if (first is not { } from || last is not { } to)
            throw new ArgumentException("Choose the first and last day.");
        if (from > to)
            throw new ArgumentException("The first date cannot be after the last date.");
        if (to.DayNumber - from.DayNumber + 1 > 367)
            throw new ArgumentException("Choose at most 367 days.");
        if (from > actor.Today)
            throw new ArgumentException("Choose a period that starts on or before today.");
        if (from < actor.Today.AddDays(-3650))
            throw new ArgumentException("Choose a date in the last ten years.");
        return (from, to);
    }

    public Task<Page<PettyCashEntryDto>> Entries(DateOnly? from, DateOnly? to, Guid? holderId, string? kind, string? status, string? q,
        int page, int pageSize, CancellationToken ct) =>
        execution.ReadAny(ReadPermissions, async actor =>
        {
            SetupPagination.Validate(page, pageSize);
            var text = q?.Trim();
            if (from is not null && to is not null && from > to)
                throw new ArgumentException("The first date cannot be after the last date.");
            if (text?.Length > 200)
                throw new ArgumentException("Search for 200 characters or fewer.");
            var filter = new PettyCashFilter(from, to, holderId, PettyCashWords.ParseKinds(kind), PettyCashWords.ParseStatus(status),
                string.IsNullOrEmpty(text) ? null : text);
            var selected = Selected(await VisibleHolders(actor, ct), holderId);
            var rows = await repository.Entries(actor, [.. selected.Select(h => h.Id)], filter, page, pageSize, ct);
            var limit = await repository.ApprovalLimit(actor.UserId, ct);
            return new Page<PettyCashEntryDto>([.. rows.Items.Select(r => Dto(actor, r, limit))], rows.PageNumber, rows.PageSize, rows.Total);
        }, ct);

    public Task<PettyCashOptionsDto> Options(DateOnly? date, CancellationToken ct) =>
        execution.ReadAny(ChangePermissions, async actor =>
        {
            var day = Day(actor, date);
            IReadOnlyList<VehicleOption> vehicles = Holds(actor, Spend) || Holds(actor, ApproveItem) ? await setup.VehicleOptions(actor, ct) : [];
            IReadOnlyList<PettyCashHolderDto> holders = Holds(actor, Issue) ? [.. (await repository.Holders(ct)).Where(h => h.Active)] : [];
            return new PettyCashOptionsDto(vehicles, await setup.ExpenseItemOptions(day, ct), holders);
        }, ct);

    public Task<PettyCashDashboardDto> Dashboard(CancellationToken ct) =>
        execution.ReadAny(DashboardPermissions, async actor =>
        {
            PettyCashDashboardFloat? own = null;
            if (Holds(actor, PermissionKeys.DashFloat))
            {
                var monthStart = new DateOnly(actor.Today.Year, actor.Today.Month, 1);
                var tallies = await repository.Tallies(actor, [actor.UserId], monthStart, actor.Today, ct);
                var state = Float(new PettyCashHolderDto(actor.UserId, "", true), tallies);
                own = new PettyCashDashboardFloat(state.Balance, state.WaitingCount, state.Waiting,
                    tallies.Where(t => t.Status == PettyCashStatus.SentBack).Sum(t => t.Count),
                    tallies.Where(t => t.Status == PettyCashStatus.Approved && t.Period == PettyCashTally.Within).Sum(t => t.Total));
            }

            PettyCashDashboardApprovals? approvals = null;
            if (Holds(actor, PermissionKeys.DashPettyCash))
            {
                var limit = await repository.ApprovalLimit(actor.UserId, ct);
                var holders = await VisibleHolders(actor, ct);
                var names = holders.ToDictionary(h => h.Id, h => h.Name);
                var waiting = await repository.Waiting(actor, [.. holders.Select(h => h.Id)], null, false, ct);
                var byHolder = waiting
                    .GroupBy(e => e.HolderId)
                    .Select(g => new PettyCashDashboardHolder(g.Key, names.GetValueOrDefault(g.Key, ""), g.Count(), g.Sum(e => e.Total), g.Min(e => e.Date)))
                    .OrderBy(h => h.Oldest).ThenBy(h => h.Name, StringComparer.Ordinal)
                    .ToList();
                approvals = new PettyCashDashboardApprovals(waiting.Count, waiting.Sum(e => e.Total), limit,
                    waiting.Count(e => !WithinLimit(e.Total, limit)), byHolder);
            }
            return new PettyCashDashboardDto(own, approvals);
        }, ct);

    public Task<PettyCashSaved> Create(SavePettyCashEntry input, CancellationToken ct) =>
        execution.WriteAny(RecordPermissions, async actor =>
        {
            var line = input.Line();
            var id = input.Id is { } given && given != Guid.Empty ? given : Guid.NewGuid();
            // A retried create answers with what the first attempt saved, even if it has changed since.
            if (await repository.AnyEntry(id, ct) is { } existing)
            {
                if (existing.RecordedBy != actor.UserId)
                    throw new PettyCashConflictException(null, "This entry was already saved by someone else. Reload and try again.");
                return new PettyCashSaved(existing.Id, existing.Version, PettyCashWords.Status(existing.Status), await repository.Balance(existing.HolderId, ct));
            }

            var holderId = await HolderFor(actor, line.Kind, input.HolderId, ct);
            ValidateDate(actor, line.Date);
            await ValidateExpense(actor, line, null, ct);
            var after = await CheckFloat(actor, holderId, line.Kind, line.Effect, ct);
            var entry = new PettyCashEntry(id, actor.OrganizationId, holderId, line, clock.UtcNow, actor.UserId);
            repository.Add(entry);
            await repository.RecordChange(actor, entry, null, Snapshot(entry), SetupPagination.Automatic($"Recorded {await Describe(entry, ct)}"), ct);
            return Saved(entry, after);
        }, ct);

    public Task<PettyCashSaved> Update(Guid id, SavePettyCashEntry input, CancellationToken ct) =>
        execution.WriteAny(ChangePermissions, async actor =>
        {
            var line = input.Line();
            var entry = await repository.Entry(actor, id, ct) ?? throw new KeyNotFoundException();
            if (line.Kind != entry.Kind)
                throw new ArgumentException("An entry cannot change between expense, credit note and cash. Remove it and record it again.");
            if (input.HolderId is { } holder && holder != entry.HolderId)
                throw new ArgumentException("An entry cannot move to another float. Remove it and record it again.");
            // Saving a sent-back entry unchanged sends it for approval again; anything else unchanged is a replay.
            if (entry.Matches(line) && entry.Status != PettyCashStatus.SentBack)
                return Saved(entry, await repository.Balance(entry.HolderId, ct));

            AuthorizeChange(actor, entry);
            if (input.Version != entry.Version)
                throw await Conflict(actor, entry.Id, ct);
            if (line.Date != entry.Date)
                ValidateDate(actor, line.Date);
            await ValidateExpense(actor, line, entry, ct);
            var after = await CheckFloat(actor, entry.HolderId, entry.Kind, line.Effect - entry.Effect, ct);

            var before = Snapshot(entry);
            entry.Change(line, clock.UtcNow, actor.UserId);
            await repository.RecordChange(actor, entry, before, Snapshot(entry), SetupPagination.Automatic($"Changed {await Describe(entry, ct)}"), ct);
            return Saved(entry, after);
        }, ct);

    public Task<PettyCashSaved> Approve(Guid id, ReviewPettyCashEntry input, CancellationToken ct) =>
        execution.Write(ApproveItem, async actor =>
        {
            var entry = await repository.Entry(actor, id, ct) ?? throw new KeyNotFoundException();
            if (entry.Status == PettyCashStatus.Approved && entry.ReviewedBy == actor.UserId)
                return Saved(entry, await repository.Balance(entry.HolderId, ct));

            AuthorizeReview(actor, entry, await repository.ApprovalLimit(actor.UserId, ct));
            if (input.Version != entry.Version)
                throw await Conflict(actor, entry.Id, ct);
            var before = Snapshot(entry);
            entry.Approve(clock.UtcNow, actor.UserId);
            await repository.RecordChange(actor, entry, before, Snapshot(entry), SetupPagination.Automatic($"Approved {await Describe(entry, ct)}"), ct);
            return Saved(entry, await repository.Balance(entry.HolderId, ct));
        }, ct);

    public Task<PettyCashSaved> SendBack(Guid id, SendBackPettyCashEntry input, CancellationToken ct) =>
        execution.Write(ApproveItem, async actor =>
        {
            var comment = input.Comment?.Trim();
            var entry = await repository.Entry(actor, id, ct) ?? throw new KeyNotFoundException();
            if (entry.Status == PettyCashStatus.SentBack && entry.ReviewedBy == actor.UserId && entry.SentBackNote == comment)
                return Saved(entry, await repository.Balance(entry.HolderId, ct));

            AuthorizeReview(actor, entry, await repository.ApprovalLimit(actor.UserId, ct));
            if (input.Version != entry.Version)
                throw await Conflict(actor, entry.Id, ct);
            var before = Snapshot(entry);
            entry.SendBack(comment ?? "", clock.UtcNow, actor.UserId);
            await repository.RecordChange(actor, entry, before, Snapshot(entry),
                SetupPagination.Automatic($"Sent back {await Describe(entry, ct)}", entry.SentBackNote), ct);
            return Saved(entry, await repository.Balance(entry.HolderId, ct));
        }, ct);

    public Task<PettyCashSaved> Remove(Guid id, RemovePettyCashEntry input, CancellationToken ct) =>
        execution.WriteAny(ChangePermissions, async actor =>
        {
            var reason = SetupPagination.Reason(input.Reason);
            var entry = await repository.Entry(actor, id, ct) ?? throw new KeyNotFoundException();
            AuthorizeChange(actor, entry);
            if (input.Version != entry.Version)
                throw await Conflict(actor, entry.Id, ct);
            var after = await CheckFloat(actor, entry.HolderId, entry.Kind, -entry.Effect, ct);

            var before = Snapshot(entry);
            var what = await Describe(entry, ct);
            entry.Remove(reason, clock.UtcNow, actor.UserId);
            await repository.RecordChange(actor, entry, before, Snapshot(entry), SetupPagination.Automatic($"Removed {what}", reason), ct);
            return Saved(entry, after);
        }, ct);

    // Approves what this person could approve one by one, and counts the rest as skipped.
    public Task<PettyCashDayApproved> ApproveDay(ApprovePettyCashDay input, CancellationToken ct) =>
        execution.Write(ApproveWholeDay, async actor =>
        {
            var day = Day(actor, input.Date);
            var selected = Selected(await VisibleHolders(actor, ct), input.HolderId);
            var limit = await repository.ApprovalLimit(actor.UserId, ct);
            var waiting = await repository.Waiting(actor, [.. selected.Select(h => h.Id)], day, true, ct);
            var approved = waiting.Where(e => CanReview(actor, e, limit)).ToList();
            var labels = await Labels(approved, ct);
            foreach (var entry in approved)
            {
                var before = Snapshot(entry);
                entry.Approve(clock.UtcNow, actor.UserId);
                await repository.RecordChange(actor, entry, before, Snapshot(entry), SetupPagination.Automatic($"Approved {Describe(entry, labels)}"), ct);
            }
            return new PettyCashDayApproved(approved.Count, approved.Sum(e => e.Total), waiting.Count - approved.Count);
        }, ct);

    private static bool Holds(SetupActor actor, string permission) => actor.Permissions.Contains(permission);

    private static bool WithinLimit(decimal total, decimal? limit) => limit is null || Math.Abs(total) <= limit.Value;

    // Cash is changed by issuers only. The person whose float it is changes their own entries until they are approved,
    // and so does an issuer for a credit note they recorded. Someone who approves changes anyone else's at any time,
    // except an approved entry they recorded themselves.
    private static bool CanChange(SetupActor actor, PettyCashEntry entry)
    {
        if (entry.Kind == PettyCashKind.Cash) return Holds(actor, Issue);
        var approved = entry.Status == PettyCashStatus.Approved;
        var own = !approved &&
            ((entry.HolderId == actor.UserId && Holds(actor, Spend)) ||
             (entry.Kind == PettyCashKind.Credit && entry.RecordedBy == actor.UserId && Holds(actor, Issue)));
        return own || (Holds(actor, ApproveItem) && entry.HolderId != actor.UserId && !(approved && entry.RecordedBy == actor.UserId));
    }

    // Nobody reviews their own float or an entry they recorded, or an entry above their approval limit.
    private static bool CanReview(SetupActor actor, PettyCashEntry entry, decimal? limit) =>
        entry.Reviewed && entry.Status == PettyCashStatus.Waiting && Holds(actor, ApproveItem) &&
        entry.HolderId != actor.UserId && entry.RecordedBy != actor.UserId && WithinLimit(entry.Total, limit);

    private static void AuthorizeChange(SetupActor actor, PettyCashEntry entry)
    {
        if (CanChange(actor, entry)) return;
        if (entry.Kind == PettyCashKind.Cash)
            throw PermissionCatalog.Refusal("Changing cash given to a float", Issue);
        if (entry.Status == PettyCashStatus.Approved && (entry.HolderId == actor.UserId || entry.RecordedBy == actor.UserId))
            throw new UnauthorizedAccessException("An approved entry can only be changed by someone else who approves petty cash.");
        if (entry.HolderId == actor.UserId)
            throw PermissionCatalog.Refusal("Changing your own entries", Spend);
        throw PermissionCatalog.Refusal("Changing someone else's entry", ApproveItem);
    }

    private static void AuthorizeReview(SetupActor actor, PettyCashEntry entry, decimal? limit)
    {
        if (!entry.Reviewed)
            throw new ArgumentException("Cash given is not approved.");
        if (entry.HolderId == actor.UserId)
            throw new UnauthorizedAccessException("You cannot approve or send back entries on your own float.");
        if (entry.RecordedBy == actor.UserId)
            throw new UnauthorizedAccessException("You cannot approve or send back an entry you recorded.");
        if (!WithinLimit(entry.Total, limit))
            throw new UnauthorizedAccessException("This entry is above your approval limit.");
    }

    private async Task<Guid> HolderFor(SetupActor actor, PettyCashKind kind, Guid? holderId, CancellationToken ct)
    {
        switch (kind)
        {
            case PettyCashKind.Expense:
                if (!Holds(actor, Spend))
                    throw PermissionCatalog.Refusal("Recording spending", Spend);
                if (holderId is { } other && other != actor.UserId)
                    throw new ArgumentException("Spending is recorded on your own float.");
                return actor.UserId;
            case PettyCashKind.Credit when holderId is null || holderId == actor.UserId:
                if (!Holds(actor, Spend))
                    throw PermissionCatalog.Refusal("Recording a credit note on your own float", Spend);
                return actor.UserId;
            case PettyCashKind.Credit:
                if (!Holds(actor, Issue))
                    throw PermissionCatalog.Refusal("Recording a credit note on someone else's float", Issue);
                return await ActiveHolder(holderId!.Value, ct);
            default:
                if (!Holds(actor, Issue))
                    throw PermissionCatalog.Refusal("Giving cash to a float", Issue);
                return await ActiveHolder(holderId ?? throw new ArgumentException("Choose who the cash goes to."), ct);
        }
    }

    private async Task<Guid> ActiveHolder(Guid holderId, CancellationToken ct) =>
        (await repository.Holders(ct)).Any(h => h.Id == holderId && h.Active)
            ? holderId
            : throw new ArgumentException("Choose someone who keeps a petty cash float.");

    private static void ValidateDate(SetupActor actor, DateOnly date)
    {
        if (date > actor.Today)
            throw new ArgumentException("Petty cash cannot be recorded for a future date.");
        if (date < actor.Today.AddDays(-3650))
            throw new ArgumentException("Choose a date in the last ten years.");
    }

    private static DateOnly Day(SetupActor actor, DateOnly? date)
    {
        var day = date ?? actor.Today;
        ValidateDate(actor, day);
        return day;
    }

    // A vehicle or item is checked when it or the date changes, so an old entry can still be corrected after its
    // vehicle has left or its item was turned off.
    private async Task ValidateExpense(SetupActor actor, PettyCashLine line, PettyCashEntry? previous, CancellationToken ct)
    {
        if (line.Kind != PettyCashKind.Expense) return;
        var dateChanged = previous is null || previous.Date != line.Date;
        if (dateChanged || previous!.VehicleId != line.VehicleId)
        {
            var vehicle = await repository.Vehicle(actor, line.VehicleId!.Value, ct)
                ?? throw new ArgumentException("Choose one of your vehicles.");
            if (!vehicle.ActiveOn(line.Date))
                throw new ArgumentException("The vehicle was not in the fleet on that day.");
        }
        if ((dateChanged || previous!.ExpenseItemId != line.ExpenseItemId) &&
            await setup.ActiveExpenseItem(line.ExpenseItemId!.Value, line.Date, ct) is null)
            throw new ArgumentException("Choose an item that is in use.");
    }

    // A float may go below zero when someone spends their own money before cash reaches them. Taking cash back is
    // different: leaving the float below zero that way needs its own permission.
    private async Task<decimal> CheckFloat(SetupActor actor, Guid holderId, PettyCashKind kind, decimal delta, CancellationToken ct)
    {
        var after = await repository.Balance(holderId, ct) + delta;
        if (kind == PettyCashKind.Cash && delta < 0 && after < 0 && !Holds(actor, IssueNegative))
            throw new PettyCashBelowZeroException(after);
        return after;
    }

    private static DateOnly StartOfWeek(DateOnly date, int firstDay) =>
        date.AddDays(-(((int)date.DayOfWeek - firstDay + 7) % 7));

    private async Task<IReadOnlyList<PettyCashHolderDto>> VisibleHolders(SetupActor actor, CancellationToken ct)
    {
        var holders = await repository.Holders(ct);
        return Holds(actor, ViewAll) ? holders : [.. holders.Where(h => h.Id == actor.UserId)];
    }

    private static IReadOnlyList<PettyCashHolderDto> Selected(IReadOnlyList<PettyCashHolderDto> holders, Guid? holderId)
    {
        if (holderId is null) return holders;
        var one = holders.Where(h => h.Id == holderId.Value).ToList();
        return one.Count > 0 ? one : throw new KeyNotFoundException();
    }

    private static PettyCashPermissionsDto Permissions(SetupActor actor, decimal? limit) => new(
        Holds(actor, Spend) ? actor.UserId : null, Holds(actor, Spend), Holds(actor, ViewAll), Holds(actor, Issue),
        Holds(actor, IssueNegative), Holds(actor, ApproveItem), Holds(actor, ApproveWholeDay), limit);

    private static decimal Sum(IEnumerable<PettyCashTally> tallies, PettyCashKind kind) => tallies.Where(t => t.Kind == kind).Sum(t => t.Total);

    private static PettyCashFiguresDto Figures(IReadOnlyList<PettyCashTally> tallies)
    {
        var before = tallies.Where(t => t.Period == PettyCashTally.Before).ToList();
        var within = tallies.Where(t => t.Period == PettyCashTally.Within).ToList();
        var opening = Sum(before, PettyCashKind.Cash) - Sum(before, PettyCashKind.Credit) - Sum(before, PettyCashKind.Expense);
        var (cash, expenses, credit) = (Sum(within, PettyCashKind.Cash), Sum(within, PettyCashKind.Expense), Sum(within, PettyCashKind.Credit));
        return new PettyCashFiguresDto(opening, cash, expenses, credit, expenses + credit, opening + cash - expenses - credit);
    }

    private static PettyCashFloatDto Float(PettyCashHolderDto holder, IReadOnlyList<PettyCashTally> tallies)
    {
        var own = tallies.Where(t => t.HolderId == holder.Id).ToList();
        var reviewed = own.Where(t => t.Kind != PettyCashKind.Cash).ToList();
        decimal Status(PettyCashStatus status) => reviewed.Where(t => t.Status == status).Sum(t => t.Total);
        var (cash, credit, expenses) = (Sum(own, PettyCashKind.Cash), Sum(own, PettyCashKind.Credit), Sum(own, PettyCashKind.Expense));
        var lastCash = own.Where(t => t.Kind == PettyCashKind.Cash).Select(t => (DateOnly?)t.Latest).Max();
        return new PettyCashFloatDto(holder.Id, holder.Name, holder.Active, cash, credit, expenses, Status(PettyCashStatus.Waiting),
            reviewed.Where(t => t.Status == PettyCashStatus.Waiting).Sum(t => t.Count), Status(PettyCashStatus.Approved),
            Status(PettyCashStatus.SentBack), cash - credit - expenses, lastCash);
    }

    private static PettyCashEntryDto Dto(SetupActor actor, PettyCashEntryRow row, decimal? limit)
    {
        var e = row.Entry;
        var canChange = CanChange(actor, e);
        return new PettyCashEntryDto(e.Id, PettyCashWords.Kind(e.Kind), e.HolderId, row.HolderName, e.Date, e.VehicleId, row.Registration,
            e.ExpenseItemId, row.ExpenseItemName, row.Bucket, e.Units, e.UnitAmount, e.Total, e.Payee, e.Note, e.Reimbursable,
            PettyCashWords.Status(e.Status), e.SentBackNote, row.ReviewedByName, e.ReviewedAt, row.RecordedByName, e.RecordedAt,
            e.UpdatedAt, e.Version, canChange, canChange, CanReview(actor, e, limit),
            e.Reviewed && e.Status == PettyCashStatus.Waiting && !WithinLimit(e.Total, limit));
    }

    private async Task<PettyCashConflictException> Conflict(SetupActor actor, Guid id, CancellationToken ct)
    {
        var row = await repository.Row(actor, id, ct);
        return new PettyCashConflictException(row is null ? null : Dto(actor, row, await repository.ApprovalLimit(actor.UserId, ct)));
    }

    private static PettyCashSaved Saved(PettyCashEntry entry, decimal balance) =>
        new(entry.Id, entry.Version, PettyCashWords.Status(entry.Status), balance);

    private sealed record EntryLabels(IReadOnlyDictionary<Guid, string> Names, IReadOnlyDictionary<Guid, string> Registrations);

    private async Task<EntryLabels> Labels(IReadOnlyCollection<PettyCashEntry> entries, CancellationToken ct) => new(
        await repository.Names(entries.Select(e => e.HolderId), ct),
        await repository.Registrations(entries.Where(e => e.VehicleId is not null).Select(e => e.VehicleId!.Value), ct));

    private async Task<string> Describe(PettyCashEntry entry, CancellationToken ct) => Describe(entry, await Labels([entry], ct));

    // The change log names the float and what the money was for, as in "Approved Brian Mwangi's petty cash spending
    // on KDA 482M for 28 Sep 2026".
    private static string Describe(PettyCashEntry entry, EntryLabels labels)
    {
        var holder = labels.Names.GetValueOrDefault(entry.HolderId, "someone");
        return entry.Kind switch
        {
            PettyCashKind.Expense => $"{holder}'s petty cash spending on {labels.Registrations.GetValueOrDefault(entry.VehicleId!.Value, "a vehicle")} " +
                $"for {entry.Date.ToString("d MMM yyyy", CultureInfo.InvariantCulture)}",
            PettyCashKind.Credit => $"{holder}'s petty cash credit note paying {entry.Payee}",
            _ => entry.Total < 0 ? $"petty cash taken back from {holder}" : $"petty cash given to {holder}"
        };
    }

    private static object Snapshot(PettyCashEntry entry) => new
    {
        entry.Id,
        entry.HolderId,
        Kind = entry.Kind.ToString(),
        entry.Date,
        entry.VehicleId,
        entry.ExpenseItemId,
        entry.Units,
        entry.UnitAmount,
        entry.Total,
        entry.Payee,
        entry.Note,
        entry.Reimbursable,
        Status = entry.Status?.ToString(),
        entry.SentBackNote,
        entry.ReviewedBy,
        entry.ReviewedAt,
        entry.RecordedBy,
        entry.RecordedAt,
        entry.UpdatedBy,
        entry.UpdatedAt,
        entry.RemovedBy,
        entry.RemovedAt,
        entry.RemovalReason,
        entry.Version
    };
}
