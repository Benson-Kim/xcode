using Auth.Domain;

namespace Auth.Application;

public sealed record PermissionGroup(string Name, IReadOnlyList<PermissionItem> Items);
public sealed record PermissionItem(string Key, string Label)
{
    public IReadOnlyList<string> Needs => PermissionDependencies.DirectFor(Key);
}
public sealed record AccessRole(Guid Id, string Name, IReadOnlyList<string> Permissions);
public sealed record ScopeCompanyOption(Guid Id, string Name);
public sealed record ScopeVehicleOption(Guid Id, string Registration, Guid CompanyId);
public sealed record ScopeOptions(IReadOnlyList<ScopeCompanyOption> Companies, IReadOnlyList<ScopeVehicleOption> Vehicles);
public sealed record PersonDto(Guid Id, string FirstName, string LastName, string Email, string PhoneNumber,
    string Role, bool Active, string ScopeMode, IReadOnlyList<Guid> CompanyIds, IReadOnlyList<Guid> VehicleIds,
    IReadOnlyList<string> Permissions, decimal? ApprovalLimit, bool HasPin, long Version);
public sealed record SavePerson(string FirstName, string LastName, string Email, string PhoneNumber, string Role,
    string ScopeMode, List<Guid> CompanyIds, List<Guid> VehicleIds, List<string> Permissions, decimal? ApprovalLimit,
    long? Version = null);
public sealed record PersonLifecycleRequest(long? Version = null, string? Reason = null);

public static class PermissionCatalog
{
    public static readonly IReadOnlyList<PermissionGroup> Groups =
    [
        new("Dashboard",
        [
            new("dash.capture", "See today's capture for my vehicles"),
            new("dash.float", "See my petty cash float"),
            new("dash.revenue", "See revenue totals"),
            new("dash.net", "See net contribution and weakest vehicles"),
            new("dash.costs", "See cost totals"),
            new("dash.gaps", "See missing revenue days"),
            new("dash.pettycash", "See petty cash waiting for approval"),
            new("dash.commitments", "See renewals due"),
            new("dash.investment", "See money invested and how much is back"),
            new("dash.edits", "See records edited after capture")
        ]),
        new("Revenue",
        [
            new("revenue.view", "View revenue records"),
            new("revenue.capture", "Capture revenue"),
            new("revenue.no_earnings", "Record a no earnings reason"),
            new("revenue.correct", "Correct revenue after the day")
        ]),
        new("Expenses",
        [
            new("expenses.view", "View expenses"),
            new("expenses.capture", "Record an expense straight onto a vehicle"),
            new("expenses.correct", "Change an expense after the day"),
            new("expenses.setup", "Set up expense categories and items")
        ]),
        new("Petty cash",
        [
            new("pettycash.spend", "Record spending from my float"),
            new("pettycash.view_all", "View every float"),
            new("pettycash.approve_item", "Approve single entries"),
            new("pettycash.approve_day", "Approve a whole day"),
            new("pettycash.issue", "Record money sent to a float"),
            new("pettycash.issue_negative", "Send money that takes a float below zero")
        ]),
        new("Office bills",
        [
            new("bills.view", "View office bills"),
            new("bills.capture", "Capture office bills"),
            new("bills.approve", "Approve office bills")
        ]),
        new("Recurring costs and savings",
        [
            new("commitments.view", "View recurring costs and savings"),
            new("commitments.manage", "Set up, change and stop recurring costs and savings")
        ]),
        new("Reports",
        [
            new("reports.view", "View reports"),
            new("reports.export", "Export reports")
        ]),
        new("Setup",
        [
            new("companies.manage", "Set up PSV companies"),
            new("vehicles.manage", "Set up vehicles and weekly targets"),
            new("invest.view", "See what was invested in a vehicle"),
            new("invest.manage", "Record what was invested in a vehicle"),
            new("people.view", "View people"),
            new("people.manage", "Add people, choose their role and what they can see, remove access"),
            new("access.manage", "Change single permissions and approval limits for a person"),
            new("audit.view", "View the change log"),
            new("organization.manage", "Manage organization settings")
        ])
    ];

    public static IReadOnlyList<string> All => Groups.SelectMany(x => x.Items).Select(x => x.Key).ToArray();

    public static readonly IReadOnlyDictionary<string, string[]> RolePermissions = new Dictionary<string, string[]>(StringComparer.OrdinalIgnoreCase)
    {
        ["Owner"] = All.Where(x => x is not ("dash.capture" or "dash.float" or "pettycash.spend")).ToArray(),
        ["Office admin"] =
        [
            "dash.capture", "dash.revenue", "dash.costs", "dash.gaps", "dash.commitments", "dash.investment", "dash.edits",
            "revenue.view", "revenue.capture", "revenue.no_earnings", "revenue.correct",
            "expenses.view", "expenses.capture", "expenses.correct", "expenses.setup",
            "bills.view", "bills.capture", "bills.approve",
            "commitments.view", "commitments.manage",
            "reports.view", "reports.export",
            "invest.view", "invest.manage",
            "companies.manage", "vehicles.manage", "people.view", "people.manage", "audit.view"
        ],
        ["Fleet manager"] =
        [
            "dash.float", "dash.revenue", "dash.costs", "dash.gaps",
            "revenue.view", "revenue.capture", "revenue.no_earnings", "revenue.correct",
            "pettycash.spend", "expenses.view", "reports.view"
        ],
        ["Revenue clerk"] = ["dash.capture", "dash.gaps", "revenue.view", "revenue.capture", "revenue.no_earnings"]
    };

    public static IReadOnlyList<string> DefaultsFor(string roleName) => WithDependencies(RolePermissions.GetValueOrDefault(roleName, []));

    public static IReadOnlyList<string> WithDependencies(IEnumerable<string> permissions) =>
        PermissionDependencies.Expand(permissions).ToArray();
}
