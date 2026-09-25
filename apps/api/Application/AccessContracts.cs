namespace Auth.Application;

public sealed record PermissionGroup(string Name, IReadOnlyList<PermissionItem> Items);
public sealed record PermissionItem(string Key, string Label, IReadOnlyList<string> Needs);
public sealed record AccessRole(Guid Id, string Name);
public sealed record PersonDto(Guid Id, string FirstName, string LastName, string Email, string PhoneNumber,
    string Role, bool Active, string ScopeMode, IReadOnlyList<Guid> CompanyIds, IReadOnlyList<Guid> VehicleIds,
    IReadOnlyList<string> Permissions, decimal? ApprovalLimit, bool HasPin);
public sealed record SavePerson(string FirstName, string LastName, string Email, string PhoneNumber, string Role,
    string ScopeMode, List<Guid> CompanyIds, List<Guid> VehicleIds, List<string> Permissions, decimal? ApprovalLimit);

public static class PermissionCatalog
{
    public static readonly IReadOnlyList<PermissionGroup> Groups =
    [
        new("Dashboard", [new("dash.capture", "See today's capture for my vehicles", []), new("dash.float", "See my petty cash float", []), new("dash.revenue", "See revenue totals", []), new("dash.net", "See net contribution and weakest vehicles", []), new("dash.costs", "See cost totals", []), new("dash.gaps", "See missing revenue days", []), new("dash.pettycash", "See petty cash waiting for approval", []), new("dash.commitments", "See renewals due", []), new("dash.edits", "See records edited after capture", [])]),
        new("Revenue", [new("revenue.view", "View revenue records", []), new("revenue.capture", "Capture revenue", ["revenue.view"]), new("revenue.no_earnings", "Record a no earnings reason", ["revenue.capture"]), new("revenue.correct", "Correct revenue after the day", ["revenue.view"])]),
        new("Petty cash", [new("pettycash.spend", "Record spending from my float", []), new("pettycash.view_all", "View every float", []), new("pettycash.approve_item", "Approve single entries", ["pettycash.view_all"]), new("pettycash.approve_day", "Approve a whole day", ["pettycash.approve_item"]), new("pettycash.issue", "Record money sent to a float", ["pettycash.view_all"]), new("pettycash.issue_negative", "Send money that takes a float below zero", ["pettycash.issue"])]),
        new("Office bills", [new("bills.view", "View office bills", []), new("bills.capture", "Capture office bills", ["bills.view"]), new("bills.approve", "Approve office bills", ["bills.view"])]),
        new("Recurring costs and savings", [new("commitments.view", "View recurring costs and savings", []), new("commitments.manage", "Set up, change and stop recurring costs and savings", ["commitments.view"])]),
        new("Reports", [new("reports.view", "View reports", []), new("reports.export", "Export reports", ["reports.view"])]),
        new("Setup", [new("companies.manage", "Set up PSV companies", []), new("vehicles.manage", "Set up vehicles and weekly targets", []), new("people.view", "View people", []), new("people.manage", "Add people, choose their role and what they can see, remove access", ["people.view"]), new("access.manage", "Change single permissions and approval limits for a person", ["people.manage"]), new("audit.view", "View the change log", []), new("organization.manage", "Manage organization settings", [])])
    ];

    public static IReadOnlyList<string> All => Groups.SelectMany(x => x.Items).Select(x => x.Key).ToArray();
    public static readonly IReadOnlyDictionary<string, string[]> RolePermissions = new Dictionary<string, string[]>(StringComparer.OrdinalIgnoreCase)
    {
        ["Owner"] = All.Where(x => x is not ("dash.capture" or "dash.float" or "pettycash.spend")).ToArray(),
        ["Office admin"] = ["dash.revenue", "dash.costs", "dash.gaps", "dash.commitments", "dash.edits", "revenue.view", "revenue.correct", "bills.view", "bills.capture", "commitments.view", "commitments.manage", "reports.view", "reports.export", "companies.manage", "vehicles.manage", "people.view", "people.manage", "audit.view"],
        ["Fleet manager"] = ["dash.float", "dash.revenue", "dash.costs", "dash.gaps", "revenue.view", "revenue.capture", "revenue.no_earnings", "revenue.correct", "pettycash.spend", "reports.view"],
        ["Revenue clerk"] = ["dash.capture", "dash.gaps", "revenue.view", "revenue.capture", "revenue.no_earnings"]
    };

    public static IReadOnlyList<string> WithDependencies(IEnumerable<string> permissions)
    {
        var result = permissions.ToHashSet(StringComparer.Ordinal);
        var pending = new Queue<string>(result);
        while (pending.TryDequeue(out var key))
            foreach (var need in Groups.SelectMany(x => x.Items).FirstOrDefault(x => x.Key == key)?.Needs ?? [])
                if (result.Add(need)) pending.Enqueue(need);
        return result.ToArray();
    }
}