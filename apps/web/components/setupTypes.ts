export type View = "dashboard" | "revenue" | "people" | "companies" | "vehicles" | "recurring" | "history" | "settings";
export type Page<T> = { items: T[]; pageNumber: number; pageSize: number; total: number };
export type Permission = { key: string; label: string; needs: string[] };
export type PermissionGroup = { name: string; items: Permission[] };
export type Role = { id: string; name: string };
export type Person = { id: string; firstName: string; lastName: string; email: string; phoneNumber: string; role: string; active: boolean; scopeMode: string; companyIds: string[]; vehicleIds: string[]; permissions: string[]; approvalLimit?: number; hasPin: boolean };
