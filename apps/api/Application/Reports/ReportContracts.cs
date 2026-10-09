using Auth.Application.PettyCash;
using Auth.Domain.Setup;

namespace Auth.Application.Reports;

// The words reports travel as, the ones the web reads (packages/shared/src/reports.ts).
public static class ReportIds
{
    public const string Fleet = "fleet";
    public const string PettyCash = "pettycash";

    public static readonly string[] FleetReports = ["net", "target", "moneyOut", "gaps", "savings", "investment"];
    public static readonly string[] PettyCashReports = ["cashBook", "managers", "vehicles", "items", "waiting", "sentBack"];
    // Investment covers each vehicle since it joined; Waiting lists everything still waiting.
    public static readonly string[] Undated = ["investment", "waiting"];

    public const int MaxDays = 367;
    public const int PageSize = 50;
}

public static class CellKinds
{
    public const string Text = "text";
    public const string Vehicle = "vehicle";
    public const string Date = "date";
    public const string Money = "money";
    public const string Net = "net";
    public const string Count = "count";
    public const string Quantity = "quantity";
    public const string Percent = "percent";
}

public sealed record ReportColumnDto(string Key, string Label, string Kind, bool Sum = false);

public sealed record ReportFigureDto(string Label, decimal Value, string Kind);

// A whole report as built, before search and paging. A cell is a string, a number or null; a date cell is
// "yyyy-MM-dd". From and To are null for an undated report.
public sealed record ReportTable(string Group, string Report, string Title, DateOnly? From, DateOnly? To, DateOnly BusinessDate,
    ReportFigureDto Headline, IReadOnlyList<ReportFigureDto> Figures, IReadOnlyList<ReportColumnDto> Columns,
    IReadOnlyList<IReadOnlyList<object?>> Rows);

// One page of a report. Total counts the rows matching the search; Totals adds up each summed column over all of
// them (null for the others). Headline and Figures cover the whole report, whatever the search.
public sealed record ReportTableDto(string Group, string Report, string Title, DateOnly? From, DateOnly? To, DateOnly BusinessDate,
    ReportFigureDto Headline, IReadOnlyList<ReportFigureDto> Figures, IReadOnlyList<ReportColumnDto> Columns,
    IReadOnlyList<IReadOnlyList<object?>> Rows, int PageNumber, int PageSize, int Total, IReadOnlyList<decimal?> Totals);

public sealed record ReportsAccessDto(DateOnly BusinessDate, int FirstDayOfWeek, IReadOnlyList<string> Fleet,
    IReadOnlyList<string> PettyCash, IReadOnlyList<PettyCashHolderDto> Holders, bool CanExport);

public sealed record ReportExport(byte[] Content, string FileName, string ContentType);

// An exported file: the table and the rows the search left, with what the file says about them.
public sealed record ReportDocument(ReportTable Table, IReadOnlyList<IReadOnlyList<object?>> Rows, string Organization, string? Period,
    string Filters, string ExportedBy, DateOnly ExportedOn, string Currency)
{
    public string Stamp => $"Exported {ExportedOn.ToString("d MMM yyyy", System.Globalization.CultureInfo.InvariantCulture)} by {ExportedBy}";
}

public interface IReportPdf
{
    byte[] Write(ReportDocument document);
}

// A vehicle the person can see, with what the reports read off it: its company, targets and days away.
public sealed record ReportVehicle(FleetVehicle Vehicle, string CompanyName)
{
    public Guid Id => Vehicle.Id;
    public string Registration => Vehicle.Registration;

    // Its days inside [from, through], never after the business date: from its join date up to the day before it left.
    public (DateOnly First, DateOnly Last)? Window(DateOnly from, DateOnly through, DateOnly today)
    {
        var first = from < Vehicle.JoinedOn ? Vehicle.JoinedOn : from;
        var last = through < today ? through : today;
        if (Vehicle.LeftOn is { } left && left <= last) last = left.AddDays(-1);
        return first <= last ? (first, last) : null;
    }
}

// One day's revenue record: an amount, or none with a reason.
public sealed record ReportRevenueDay(Guid VehicleId, DateOnly Date, decimal? Amount);

public interface IReportRepository
{
    // Vehicles in the actor's data scope, with targets and days away; a company narrows them to that company.
    Task<IReadOnlyList<ReportVehicle>> Vehicles(SetupActor actor, Guid? companyId, CancellationToken ct);
    Task<IReadOnlyList<ReportRevenueDay>> Revenue(IReadOnlyCollection<Guid> vehicleIds, DateOnly from, DateOnly through, CancellationToken ct);
    Task<IReadOnlyDictionary<Guid, string>> ItemNames(IReadOnlyCollection<Guid> itemIds, CancellationToken ct);
    Task<IReadOnlyDictionary<Guid, decimal>> Invested(IReadOnlyCollection<Guid> vehicleIds, CancellationToken ct);
    // The name the organization shows on its pages and files.
    Task<string> OrganizationName(CancellationToken ct);
}
