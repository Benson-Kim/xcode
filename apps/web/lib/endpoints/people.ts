import { apiRequest } from "../data";
import type { BackLimit, Person } from "../types";

export const PEOPLE_PATH = "setup/people";
export const ROLES_PATH = "setup/access/roles";
export const CATALOG_PATH = "setup/access/catalog";
export const SCOPE_PATH = "setup/access/scope-options";

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
  // How far back the person may change records (v2.32).
  backLimit: BackLimit;
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
  // Block, unblock, and "Remove all" trusted devices (which also ends every session).
  lifecycle: (id: string, action: LifecycleAction, body?: LifecycleRequest) =>
    apiRequest(`${personPath(id)}/${action}`, {
      method: "POST",
      ...(action === "sign-out" ? {} : { body: JSON.stringify(body) }),
    }),
  // "Make [name] reset the PIN": removes their devices and forces a new PIN at the next sign in (v2.33).
  pinReset: (id: string) =>
    apiRequest(`${personPath(id)}/pin-reset`, { method: "POST" }),
  removeDevice: (id: string, deviceId: string) =>
    apiRequest(`${personPath(id)}/trusted-devices/${deviceId}/remove`, {
      method: "POST",
    }),
};
