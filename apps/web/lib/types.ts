export type View = "dashboard" | "revenue" | "people" | "companies" | "vehicles" | "expenses" | "recurring" | "history" | "settings" | "preferences";
export type Page<T> = { items: T[]; pageNumber: number; pageSize: number; total: number };
export type Permission = { key: string; label: string; needs: string[] };
export type PermissionGroup = { name: string; items: Permission[] };
export type Role = { id: string; name: string; permissions: string[] };
export type ScopeOptions = {
  companies: { id: string; name: string }[];
  vehicles: { id: string; registration: string; companyId: string }[];
};
export type Person = { id: string; firstName: string; lastName: string; email: string; phoneNumber: string; role: string; active: boolean; scopeMode: string; companyIds: string[]; vehicleIds: string[]; permissions: string[]; approvalLimit?: number; hasPin: boolean; version: number };

// Money out is counted in three buckets: 1 repairs and maintenance, 2 recurring charges, 3 loan repayments.
export type ExpenseBucket = 1 | 2 | 3;
export type ExpenseItem = { id: string; categoryId: string; name: string; active: boolean; stoppedOn: string | null };
export type ExpenseCategory = { id: string; name: string; bucket: ExpenseBucket; active: boolean; stoppedOn: string | null; items: ExpenseItem[] };
// An item a scheduled cost can pick (GET expense-items/options): active items in active categories.
export type ExpenseItemOption = { id: string; name: string; categoryId: string; categoryName: string; bucket: ExpenseBucket };

export type InvestmentEntry = { id: string; date: string; description: string; amount: number; recordedBy: string; recordedAt: string };
// What went into a vehicle. `returned` and `percentPaidOff` stay null until they can be worked out from revenue.
export type VehicleInvestment = {
  vehicleId: string;
  totalInvested: number;
  returned: number | null;
  percentPaidOff: number | null;
  entries: InvestmentEntry[];
};
