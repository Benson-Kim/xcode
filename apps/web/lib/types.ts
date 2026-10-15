import type { PersonIdentity } from "@xcode/shared/auth";

export type View =
  | "dashboard"
  | "revenue"
  | "centralexpenses"
  | "reports"
  | "people"
  | "companies"
  | "vehicles"
  | "expenses"
  | "recurring"
  | "savings"
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
export type MyScope = ScopeOptions & {
  allCompanies: boolean;
  // v2.32: how far back this person may change records, in words, and the earliest date allowed (null for none).
  canChange?: string;
  earliest?: string | null;
};

// How far back a person may add, change or delete dated records (v2.32): no rolling limit, a number of days or
// months back, and an optional date they may never go before. With both, the later date wins.
export type BackLimitMode = "none" | "days" | "months";

export type BackLimit = {
  mode: BackLimitMode;
  count: number | null;
  from: string | null;
};

// Where a person is with signing in (v2.33).
export type PersonStatus =
  "active" | "not_signed_in" | "pin_reset_due" | "locked" | "blocked";

export type PersonModule = { name: string; held: number; total: number };

export type PersonDevice = {
  id: string;
  name: string | null;
  trustedAt: string;
  lastUsedAt: string | null;
};

// The person's "Sign in" pane (GET /setup/people/{id}).
export type PersonSignIn = {
  status: PersonStatus;
  lock: string | null;
  lastSignedInAt: string | null;
  email: string;
  devices: PersonDevice[];
};

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
  // v2.32 and v2.33: the sign-in status with the last sign in, the back-dating limit in data and in words, and the
  // modules the person can reach (held of total), "everything" when they hold all 59 rights.
  status?: PersonStatus;
  lastSignedInAt?: string | null;
  backLimit?: BackLimit;
  canChange?: string;
  modules?: PersonModule[];
  everything?: boolean;
  signIn?: PersonSignIn;
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

// A category belongs to a main category or to none (v2.31). The bucket stays for released clients.
export type ExpenseCategory = {
  id: string;
  name: string;
  bucket: ExpenseBucket | null;
  active: boolean;
  stoppedOn: string | null;
  items: ExpenseItem[];
  mainCategoryId?: string | null;
  mainCategoryName?: string | null;
};

// GET setup/expense-main-categories: every main category with what it groups.
export type ExpenseMainCategory = {
  id: string;
  name: string;
  categoryCount: number;
  itemCount: number;
};

export type ExpenseMainCategoryPage = Page<ExpenseMainCategory> & {
  categoriesWithoutMain: number;
};

// An item a scheduled cost can pick (GET expense-items/options): active items in active categories.
export type ExpenseItemOption = {
  id: string;
  name: string;
  categoryId: string;
  categoryName: string;
  bucket: ExpenseBucket | null;
  mainCategoryName?: string | null;
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
