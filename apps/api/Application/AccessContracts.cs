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
// CompanyIds and VehicleIds hold only what the viewer can reach; OtherCompanies and OtherVehicles count what is hidden.
public sealed record PersonDto(Guid Id, string FirstName, string LastName, string Email, string PhoneNumber,
    string Role, bool Active, string ScopeMode, IReadOnlyList<Guid> CompanyIds, IReadOnlyList<Guid> VehicleIds,
    IReadOnlyList<string> Permissions, decimal? ApprovalLimit, bool HasPin, long Version,
    int OtherCompanies, int OtherVehicles);
// The caller's own data scope: what the companies and vehicles lists would show them.
public sealed record MyScope(bool AllCompanies, IReadOnlyList<ScopeCompanyOption> Companies, IReadOnlyList<ScopeVehicleOption> Vehicles);
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
            new(PermissionKeys.DashCapture, "See today's capture for my vehicles"),
            new(PermissionKeys.DashFloat, "See my petty cash float"),
            new(PermissionKeys.DashRevenue, "See revenue totals"),
            new(PermissionKeys.DashNet, "See net contribution and weakest vehicles"),
            new(PermissionKeys.DashCosts, "See cost totals"),
            new(PermissionKeys.DashGaps, "See missing revenue days"),
            new(PermissionKeys.DashPettyCash, "See petty cash waiting for approval"),
            new(PermissionKeys.DashCommitments, "See renewals due"),
            new(PermissionKeys.DashInvestment, "See money invested and how much is back"),
            new(PermissionKeys.DashEdits, "See records edited after capture")
        ]),
        new("Revenue",
        [
            new(PermissionKeys.RevenueView, "View revenue records"),
            new(PermissionKeys.RevenueCapture, "Capture revenue"),
            new(PermissionKeys.RevenueNoEarnings, "Record a no earnings reason"),
            new(PermissionKeys.RevenueCorrect, "Correct revenue after the day")
        ]),
        new("Expenses",
        [
            new(PermissionKeys.ExpensesView, "View expenses"),
            new(PermissionKeys.ExpensesCapture, "Record an expense straight onto a vehicle"),
            new(PermissionKeys.ExpensesCorrect, "Change an expense after the day"),
            new(PermissionKeys.ExpensesSetup, "Set up expense categories and items")
        ]),
        new("Petty cash",
        [
            new(PermissionKeys.PettyCashSpend, "Record spending from my float"),
            new(PermissionKeys.PettyCashViewAll, "View every float"),
            new(PermissionKeys.PettyCashApproveItem, "Approve single entries"),
            new(PermissionKeys.PettyCashApproveDay, "Approve a whole day"),
            new(PermissionKeys.PettyCashIssue, "Record money sent to a float"),
            new(PermissionKeys.PettyCashIssueNegative, "Send money that takes a float below zero")
        ]),
        new("Office bills",
        [
            new(PermissionKeys.BillsView, "View office bills"),
            new(PermissionKeys.BillsCapture, "Capture office bills"),
            new(PermissionKeys.BillsApprove, "Approve office bills")
        ]),
        new("Scheduled expenses and savings",
        [
            new(PermissionKeys.CommitmentsView, "View scheduled expenses and savings"),
            new(PermissionKeys.CommitmentsManage, "Set up, change and stop scheduled expenses and savings")
        ]),
        new("Reports",
        [
            new(PermissionKeys.ReportsView, "View reports"),
            new(PermissionKeys.ReportsExport, "Export reports")
        ]),
        new("Setup",
        [
            new(PermissionKeys.CompaniesManage, "Set up PSV companies"),
            new(PermissionKeys.VehiclesManage, "Set up vehicles and weekly targets"),
            new(PermissionKeys.InvestView, "See what was invested in a vehicle"),
            new(PermissionKeys.InvestManage, "Record what was invested in a vehicle"),
            new(PermissionKeys.PeopleView, "View people"),
            new(PermissionKeys.PeopleManage, "Add people, choose their role and what they can see, remove access"),
            new(PermissionKeys.AccessManage, "Change single permissions and approval limits for a person"),
            new(PermissionKeys.AuditView, "View the change log"),
            new(PermissionKeys.OrganizationManage, "Manage organization settings")
        ])
    ];

    public static IReadOnlyList<string> All => Groups.SelectMany(x => x.Items).Select(x => x.Key).ToArray();

    private static readonly IReadOnlyDictionary<string, string> Labels = Groups.SelectMany(x => x.Items).ToDictionary(x => x.Key, x => x.Label);

    // A refusal names the permission it needs, as People and access labels it, so the phone and the web can say so.
    public static UnauthorizedAccessException Refusal(string action, string permission) =>
        new($"{action} needs the permission \"{Labels.GetValueOrDefault(permission, permission)}\".");

    public static readonly IReadOnlyDictionary<string, string[]> RolePermissions = new Dictionary<string, string[]>(StringComparer.OrdinalIgnoreCase)
    {
        ["Owner"] = All.Where(x => x is not PermissionKeys.DashCapture).ToArray(),
        ["Office admin"] =
        [
            PermissionKeys.DashRevenue, PermissionKeys.DashCosts, PermissionKeys.DashGaps, PermissionKeys.DashCommitments, PermissionKeys.DashEdits,
            PermissionKeys.RevenueView, PermissionKeys.RevenueCorrect,
            PermissionKeys.ExpensesView, PermissionKeys.ExpensesCapture, PermissionKeys.ExpensesCorrect, PermissionKeys.ExpensesSetup,
            PermissionKeys.BillsView, PermissionKeys.BillsCapture,
            PermissionKeys.CommitmentsView, PermissionKeys.CommitmentsManage,
            PermissionKeys.ReportsView, PermissionKeys.ReportsExport,
            PermissionKeys.InvestView, PermissionKeys.InvestManage,
            PermissionKeys.CompaniesManage, PermissionKeys.VehiclesManage, PermissionKeys.PeopleView, PermissionKeys.PeopleManage, PermissionKeys.AuditView
        ],
        ["Fleet manager"] =
        [
            PermissionKeys.DashFloat, PermissionKeys.DashRevenue, PermissionKeys.DashCosts, PermissionKeys.DashGaps,
            PermissionKeys.RevenueView, PermissionKeys.RevenueCapture, PermissionKeys.RevenueNoEarnings, PermissionKeys.RevenueCorrect,
            PermissionKeys.PettyCashSpend, PermissionKeys.ExpensesView, PermissionKeys.ReportsView
        ],
        ["Revenue clerk"] = [PermissionKeys.DashCapture, PermissionKeys.DashGaps, PermissionKeys.RevenueView, PermissionKeys.RevenueCapture, PermissionKeys.RevenueNoEarnings]
    };

    public static IReadOnlyList<string> DefaultsFor(string roleName) => WithDependencies(RolePermissions.GetValueOrDefault(roleName, []));

    public static IReadOnlyList<string> WithDependencies(IEnumerable<string> permissions) =>
        PermissionDependencies.Expand(permissions).ToArray();
}
