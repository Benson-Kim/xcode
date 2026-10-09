using System.Globalization;
using Auth.Application.PettyCash;
using Auth.Application.Setup;
using Auth.Domain;

namespace Auth.Application.Reports;

// Fleet reports need reports.view (Investment also invest.view); petty cash reports also need pettycash.spend (your
// own float) or pettycash.view_all (every float). Every figure is cut to the vehicles the person can see.
public sealed class ReportUseCases(ISetupExecution execution, IReportRepository reports, IFleetPostings postings,
    IPettyCashRepository pettyCash, ISetupRepository setup, IReportPdf writer)
{
    private const string View = PermissionKeys.ReportsView;
    private const string ExportPermission = PermissionKeys.ReportsExport;

    public Task<ReportsAccessDto> Access(CancellationToken ct) => execution.Read(View, async actor =>
    {
        var holders = SeesPettyCash(actor) ? await Holders(actor, ct) : [];
        return new ReportsAccessDto(actor.Today, await setup.FirstDayOfWeek(ct),
            [.. ReportIds.FleetReports.Where(id => id != "investment" || Holds(actor, PermissionKeys.InvestView))],
            SeesPettyCash(actor) ? ReportIds.PettyCashReports : [], holders, Holds(actor, ExportPermission));
    }, ct);

    // The server searches and pages every report: a page holds only its rows, with the footer over all that match.
    public Task<ReportTableDto> Fleet(string report, DateOnly? from, DateOnly? to, Guid? companyId, string? q, int page, int pageSize,
        CancellationToken ct) =>
        execution.Read(View, async actor =>
        {
            var text = Search(q, page, pageSize);
            return Tables.Page(await Build(actor, ReportIds.Fleet, report, from, to, null, companyId, ct), text, page, pageSize);
        }, ct);

    public Task<ReportTableDto> PettyCash(string report, DateOnly? from, DateOnly? to, Guid? holderId, string? q, int page, int pageSize,
        CancellationToken ct) =>
        execution.Read(View, async actor =>
        {
            var text = Search(q, page, pageSize);
            return Tables.Page(await Build(actor, ReportIds.PettyCash, report, from, to, holderId, null, ct), text, page, pageSize);
        }, ct);

    // The table as shown, narrowed by the same search as the screen, as an Excel or PDF file; every export is written
    // to the change log.
    public Task<ReportExport> Export(string group, string report, DateOnly? from, DateOnly? to, Guid? holderId, Guid? companyId,
        string? q, string? format, CancellationToken ct) =>
        execution.Write(ExportPermission, async actor =>
        {
            var pdf = format?.Trim() switch
            {
                null or "" or "xlsx" => false,
                "pdf" => true,
                _ => throw new ArgumentException("Choose Excel (xlsx) or PDF.")
            };
            var text = Search(q, 1, 1);
            var table = await Build(actor, group, report, from, to, holderId, companyId, ct);
            var rows = Tables.Search(table, text);
            var period = Period(table);
            var document = new ReportDocument(table, rows, await reports.OrganizationName(ct), period,
                await Filters(actor, group, holderId, companyId, text, ct),
                (await pettyCash.Names([actor.UserId], ct)).GetValueOrDefault(actor.UserId, ""), actor.Today, await setup.Currency(ct));
            var (bytes, kind, extension, contentType) = pdf
                ? (writer.Write(document), "PDF", "pdf", "application/pdf")
                : (ReportWorkbook.Write(document), "Excel", "xlsx", ReportWorkbook.ContentType);
            var searched = string.IsNullOrEmpty(text) ? "" : $", searched for \"{text}\"";
            await setup.RecordChange(actor, "reports", Guid.NewGuid(), null,
                new { group, report, table.From, table.To, holderId, companyId, q = text, Rows = rows.Count, Format = extension },
                SetupPagination.Automatic($"Exported {table.Title}{(period is null ? "" : $" for {period}")}{searched} to {kind}"), ct);
            return new ReportExport(bytes, $"{table.Title}{(period is null ? "" : $" {period}")}.{extension}", contentType);
        }, ct);

    // What narrowed the report, in words, for the file's subtitle.
    private async Task<string> Filters(SetupActor actor, string group, Guid? holderId, Guid? companyId, string? text, CancellationToken ct)
    {
        var parts = new List<string>();
        if (companyId is not null && (await reports.Vehicles(actor, companyId, ct)).FirstOrDefault() is { } vehicle)
            parts.Add(vehicle.CompanyName);
        if (group == ReportIds.PettyCash)
            parts.Add(holderId is { } holder ? (await Holders(actor, ct)).FirstOrDefault(h => h.Id == holder)?.Name ?? "" : "All managers");
        if (!string.IsNullOrEmpty(text))
            parts.Add($"Search: {text}");
        return string.Join("  ·  ", parts.Where(p => p.Length > 0));
    }

    private static string? Search(string? q, int page, int pageSize)
    {
        SetupPagination.Validate(page, pageSize);
        var text = q?.Trim();
        if (text?.Length > 200)
            throw new ArgumentException("Search for 200 characters or fewer.");
        return string.IsNullOrEmpty(text) ? null : text;
    }

    private async Task<ReportTable> Build(SetupActor actor, string group, string report, DateOnly? from, DateOnly? to, Guid? holderId,
        Guid? companyId, CancellationToken ct)
    {
        if (group == ReportIds.Fleet && ReportIds.FleetReports.Contains(report))
            return await BuildFleet(actor, report, from, to, companyId, ct);
        if (group == ReportIds.PettyCash && ReportIds.PettyCashReports.Contains(report))
            return await BuildPettyCash(actor, report, from, to, holderId, ct);
        throw new KeyNotFoundException();
    }

    private async Task<ReportTable> BuildFleet(SetupActor actor, string report, DateOnly? from, DateOnly? to, Guid? companyId,
        CancellationToken ct)
    {
        var vehicles = await reports.Vehicles(actor, companyId, ct);
        if (report == "investment")
        {
            if (!Holds(actor, PermissionKeys.InvestView))
                throw PermissionCatalog.Refusal("The investment report", PermissionKeys.InvestView);
            var since = Earliest(vehicles, actor.Today);
            var data = await Load(actor, vehicles, since, actor.Today, ct);
            return FleetReports.Investment(data, await reports.Invested([.. vehicles.Select(v => v.Id)], ct));
        }

        var (start, end) = Period(actor, from, to);
        if (report == "savings")
        {
            var history = await Load(actor, vehicles, Earliest(vehicles, start), end, ct);
            return FleetReports.Savings(history with { From = start });
        }
        var loaded = await Load(actor, vehicles, start, end, ct);
        return report switch
        {
            "net" => FleetReports.Net(loaded),
            "target" => FleetReports.Target(loaded),
            "gaps" => FleetReports.Gaps(loaded),
            _ => FleetReports.MoneyOut(loaded, await reports.ItemNames(
                [.. loaded.Postings.Where(p => p.Source == PostingSource.Scheduled && p.ExpenseItemId is not null)
                    .Select(p => p.ExpenseItemId!.Value).Distinct()], ct))
        };
    }

    private async Task<FleetReportData> Load(SetupActor actor, IReadOnlyList<ReportVehicle> vehicles, DateOnly from, DateOnly to,
        CancellationToken ct)
    {
        var active = vehicles.Where(v => v.Window(from, to, actor.Today) is not null).ToList();
        var ids = active.Select(v => v.Id).ToList();
        var revenue = ids.Count == 0 ? [] : await reports.Revenue(ids, from, to, ct);
        var posted = ids.Count == 0 ? [] : await postings.Load(actor, [.. active.Select(v => v.Vehicle)], from, to, ct);
        return new FleetReportData(from, to, actor.Today, vehicles, revenue, posted);
    }

    private async Task<ReportTable> BuildPettyCash(SetupActor actor, string report, DateOnly? from, DateOnly? to, Guid? holderId,
        CancellationToken ct)
    {
        if (!SeesPettyCash(actor))
            throw PermissionCatalog.Refusal("Petty cash reports", PermissionKeys.PettyCashViewAll);
        var holders = await Holders(actor, ct);
        if (holderId is { } one)
            holders = holders.Where(h => h.Id == one).ToList() is { Count: > 0 } chosen ? chosen : throw new KeyNotFoundException();
        var ids = holders.Select(h => h.Id).ToList();

        if (report == "waiting")
        {
            var waiting = await pettyCash.ReportRows(actor, ids, null, actor.Today, PettyCashStatus.Waiting, ct);
            return PettyCashReports.Waiting(new(actor.Today, actor.Today, actor.Today, holders, waiting, [],
                await VehicleNames(actor, waiting, ct)));
        }

        var (start, end) = Period(actor, from, to);
        var rows = await pettyCash.ReportRows(actor, ids, start, end, null, ct);
        var tallies = await pettyCash.Tallies(actor, ids, start, end, ct);
        var data = new PettyCashReportData(start, end, actor.Today, holders, rows, tallies, await VehicleNames(actor, rows, ct));
        return report switch
        {
            "cashBook" => PettyCashReports.CashBook(data),
            "managers" => PettyCashReports.Managers(data),
            "vehicles" => PettyCashReports.Vehicles(data),
            "items" => PettyCashReports.Items(data),
            _ => PettyCashReports.SentBack(data)
        };
    }

    // Registrations for every row, and the company for the vehicles the person can see. A person's own float can
    // hold spending on a vehicle outside their scope; it keeps its registration and shows no company.
    private async Task<IReadOnlyDictionary<Guid, (string Registration, string Company)>> VehicleNames(SetupActor actor,
        IReadOnlyList<PettyCashReportRow> rows, CancellationToken ct)
    {
        var ids = rows.Where(r => r.VehicleId is not null).Select(r => r.VehicleId!.Value).Distinct().ToList();
        if (ids.Count == 0) return new Dictionary<Guid, (string, string)>();
        var registrations = await pettyCash.Registrations(ids, ct);
        var companies = (await reports.Vehicles(actor, null, ct)).ToDictionary(v => v.Id, v => v.CompanyName);
        return ids.ToDictionary(id => id, id => (registrations.GetValueOrDefault(id, ""), companies.GetValueOrDefault(id, "")));
    }

    private async Task<IReadOnlyList<PettyCashHolderDto>> Holders(SetupActor actor, CancellationToken ct)
    {
        var holders = await pettyCash.Holders(ct);
        return Holds(actor, PermissionKeys.PettyCashViewAll) ? holders : [.. holders.Where(h => h.Id == actor.UserId)];
    }

    private static bool SeesPettyCash(SetupActor actor) =>
        Holds(actor, PermissionKeys.PettyCashSpend) || Holds(actor, PermissionKeys.PettyCashViewAll);

    private static bool Holds(SetupActor actor, string permission) => actor.Permissions.Contains(permission);

    private static DateOnly Earliest(IReadOnlyList<ReportVehicle> vehicles, DateOnly before)
    {
        var joined = vehicles.Count == 0 ? before : vehicles.Min(v => v.Vehicle.JoinedOn);
        return joined < before ? joined : before;
    }

    // A dated report covers [from, to] with to cut back to the business date.
    private static (DateOnly From, DateOnly To) Period(SetupActor actor, DateOnly? from, DateOnly? to)
    {
        if (from is not { } start || to is not { } end)
            throw new ArgumentException("Choose the first and last day.");
        if (start > end)
            throw new ArgumentException("The first date cannot be after the last date.");
        if (end.DayNumber - start.DayNumber + 1 > ReportIds.MaxDays)
            throw new ArgumentException($"Choose at most {ReportIds.MaxDays} days.");
        if (start > actor.Today)
            throw new ArgumentException("Choose a period that starts on or before today.");
        return (start, end < actor.Today ? end : actor.Today);
    }

    private static string? Period(ReportTable table) =>
        table.From is { } from && table.To is { } to ? from == to ? Day(from) : $"{Day(from)} to {Day(to)}" : null;

    private static string Day(DateOnly date) => date.ToString("d MMM yyyy", CultureInfo.InvariantCulture);
}
