import { apiRequest } from "../data";
import type { Person } from "../types";

export const PEOPLE_PATH = "setup/people";
export const ROLES_PATH = "setup/access/roles";
export const CATALOG_PATH = "setup/access/catalog";
export const SCOPE_PATH = "setup/access/scope-options";
export const RECENT_CHANGES_PATH =
  "setup/history?pageSize=3&includeTotal=false";

export const personPath = (id: string) => `${PEOPLE_PATH}/${id}`;

export type SavePersonRequest = {
  firstName: string;
  lastName: string;
  email: string;
  phoneNumber: string;
  role: string;
  scopeMode: string;
  companyIds: string[];
  vehicleIds: string[];
  permissions: string[];
  approvalLimit: number | null;
  version: number | undefined;
};

export type LifecycleAction = "activate" | "deactivate" | "sign-out";

export type LifecycleRequest = { version: number; reason?: string };

export const peopleApi = {
  save: (person: Person | undefined, body: SavePersonRequest) =>
    apiRequest(person ? personPath(person.id) : PEOPLE_PATH, {
      method: person ? "PUT" : "POST",
      body: JSON.stringify(body),
    }),
  lifecycle: (id: string, action: LifecycleAction, body?: LifecycleRequest) =>
    apiRequest(`${personPath(id)}/${action}`, {
      method: "POST",
      ...(action === "sign-out" ? {} : { body: JSON.stringify(body) }),
    }),
};
