import type { PersonIdentity } from "@xcode/shared/auth";

export type View =
  | "dashboard"
  | "revenue"
  | "people"
  | "companies"
  | "vehicles"
  | "expenses"
  | "recurring"
  | "history"
  | "settings"
  | "preferences";

export type Page<T> = {
  items: T[];
  pageNumber: number;
  pageSize: number;
  total: number;
};

export type ChangeLogPage<T> = Omit<Page<T>, "total"> & {
  total: number | null;
  hasMore: boolean;
  nextBefore: number | null;
};

export type {
  PermissionGroup,
  PermissionItem as Permission,
} from "@xcode/shared/permissions";

export type Role = {
  id: string;
  name: string;
  permissions: string[];
};

export type ScopeOptions = {
  companies: {
    id: string;
    name: string;
  }[];

  vehicles: {
    id: string;
    registration: string;
    companyId: string;
  }[];
};

// What the signed-in person may see, answered by the server (GET /setup/access/me) rather than worked
// out from the session, so "Your access" cannot drift from what a request is actually allowed to reach.
export type MyScope = ScopeOptions & { allCompanies: boolean };

export type Person = PersonIdentity & {
  id: string;
  email: string;
  phoneNumber: string;
  active: boolean;
  scopeMode: string;
  companyIds: string[];
  vehicleIds: string[];
  otherCompanies: number;
  otherVehicles: number;
  approvalLimit?: number;
  hasPin: boolean;
  version: number;
};

// Money out is counted in three buckets: 1 repairs and maintenance, 2 recurring charges, 3 loan repayments.
export type ExpenseBucket = 1 | 2 | 3;

export type ExpenseItem = {
  id: string;
  categoryId: string;
  name: string;
  active: boolean;
  stoppedOn: string | null;
};

export type ExpenseCategory = {
  id: string;
  name: string;
  bucket: ExpenseBucket;
  active: boolean;
  stoppedOn: string | null;
  items: ExpenseItem[];
};

// An item a scheduled cost can pick (GET expense-items/options): active items in active categories.
export type ExpenseItemOption = {
  id: string;
  name: string;
  categoryId: string;
  categoryName: string;
  bucket: ExpenseBucket;
};

export type InvestmentEntry = {
  id: string;
  date: string;
  description: string;
  amount: number;
  recordedBy: string;
  recordedAt: string;
};

export type VehicleInvestment = {
  vehicleId: string;
  totalInvested: number;
  returned: number | null;
  percentPaidOff: number | null;
  entries: InvestmentEntry[];
};
