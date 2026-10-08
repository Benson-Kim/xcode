namespace Auth.Domain;

// The one list of permission keys. packages/shared/src/permissions.ts mirrors it; PermissionKeysTests fails on drift.
public static class PermissionKeys
{
    public const string DashCapture = "dash.capture";
    public const string DashFloat = "dash.float";
    public const string DashRevenue = "dash.revenue";
    public const string DashNet = "dash.net";
    public const string DashCosts = "dash.costs";
    public const string DashGaps = "dash.gaps";
    public const string DashPettyCash = "dash.pettycash";
    public const string DashCommitments = "dash.commitments";
    public const string DashInvestment = "dash.investment";
    public const string DashEdits = "dash.edits";

    public const string RevenueView = "revenue.view";
    public const string RevenueCapture = "revenue.capture";
    public const string RevenueNoEarnings = "revenue.no_earnings";
    public const string RevenueCorrect = "revenue.correct";

    public const string ExpensesView = "expenses.view";
    public const string ExpensesCapture = "expenses.capture";
    public const string ExpensesCorrect = "expenses.correct";
    public const string ExpensesSetup = "expenses.setup";

    public const string PettyCashSpend = "pettycash.spend";
    public const string PettyCashViewAll = "pettycash.view_all";
    public const string PettyCashApproveItem = "pettycash.approve_item";
    public const string PettyCashApproveDay = "pettycash.approve_day";
    public const string PettyCashIssue = "pettycash.issue";
    public const string PettyCashIssueNegative = "pettycash.issue_negative";

    public const string BillsView = "bills.view";
    public const string BillsCapture = "bills.capture";
    public const string BillsApprove = "bills.approve";

    public const string CommitmentsView = "commitments.view";
    public const string CommitmentsManage = "commitments.manage";

    public const string ReportsView = "reports.view";
    public const string ReportsExport = "reports.export";

    public const string CompaniesManage = "companies.manage";
    public const string VehiclesManage = "vehicles.manage";
    public const string InvestView = "invest.view";
    public const string InvestManage = "invest.manage";
    public const string PeopleView = "people.view";
    public const string PeopleManage = "people.manage";
    public const string AccessManage = "access.manage";
    public const string AuditView = "audit.view";
    public const string OrganizationManage = "organization.manage";
}
