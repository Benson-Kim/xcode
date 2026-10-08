import { beforeEach, describe, expect, it } from "vitest";

import { organizationApi, preferencesApi } from "../lib/endpoints/organization";
import { peopleApi, type SavePersonRequest } from "../lib/endpoints/people";
import {
  recurringApi,
  type SaveRecurringRequest,
} from "../lib/endpoints/recurring";
import type { Person } from "../lib/types";
import { fakeApi } from "./fakeApi";

let fake: ReturnType<typeof fakeApi>;
beforeEach(() => {
  fake = fakeApi();
  fake.on("POST *", [200, {}]);
  fake.on("PUT *", [200, {}]);
  fake.on("DELETE *", [200, {}]);
});

const lastCall = () => fake.calls[fake.calls.length - 1];
const lastInit = () =>
  fake.fetch.mock.calls[fake.fetch.mock.calls.length - 1][1] as RequestInit;

const person = { id: "p1", version: 4 } as Person;
const personBody: SavePersonRequest = {
  firstName: "Amina",
  lastName: "Otieno",
  email: "amina@example.co.ke",
  phoneNumber: "254712345678",
  role: "Revenue clerk",
  scopeMode: "all",
  companyIds: [],
  vehicleIds: [],
  permissions: ["revenue.view"],
  approvalLimit: null,
  version: undefined,
};

describe("organization endpoints", () => {
  it("saves a settings section as PUT with a value", async () => {
    await organizationApi.saveSection("localization", { locale: "en-GB" });
    expect(lastCall()).toMatchObject({
      method: "PUT",
      path: "setup/organization/settings/localization",
      body: { value: { locale: "en-GB" } },
    });
  });

  it("saves the business date through the businessDate section, null clears it", async () => {
    await organizationApi.saveBusinessDate("2026-09-28");
    expect(lastCall()).toMatchObject({
      method: "PUT",
      path: "setup/organization/settings/businessDate",
      body: { value: "2026-09-28" },
    });
    await organizationApi.saveBusinessDate(null);
    expect(lastCall().body).toEqual({ value: null });
  });

  it("uploads the logo with PUT and removes it with DELETE and no body", async () => {
    await organizationApi.uploadLogo("data:image/png;base64,AAAA");
    expect(lastCall()).toMatchObject({
      method: "PUT",
      path: "setup/organization/logo",
      body: { dataUrl: "data:image/png;base64,AAAA" },
    });
    await organizationApi.removeLogo();
    expect(lastCall()).toMatchObject({
      method: "DELETE",
      path: "setup/organization/logo",
    });
    expect(lastInit().body).toBeUndefined();
  });

  it("saves preferences with PUT to the preferences path", async () => {
    expect(preferencesApi.path).toBe("setup/preferences");
    await preferencesApi.save({ locale: "en-KE", hour12: true });
    expect(lastCall()).toMatchObject({
      method: "PUT",
      path: "setup/preferences",
      body: { locale: "en-KE", hour12: true },
    });
  });
});

describe("people endpoints", () => {
  it("creates with POST to the collection and updates with PUT to the person", async () => {
    await peopleApi.save(undefined, personBody);
    expect(lastCall()).toMatchObject({ method: "POST", path: "setup/people" });
    expect(lastCall().body.firstName).toBe("Amina");
    await peopleApi.save(person, { ...personBody, version: 4 });
    expect(lastCall()).toMatchObject({
      method: "PUT",
      path: "setup/people/p1",
    });
    expect(lastCall().body.version).toBe(4);
  });

  it("sends no body to sign-out", async () => {
    await peopleApi.lifecycle("p1", "sign-out", { version: 4 });
    expect(lastCall()).toMatchObject({
      method: "POST",
      path: "setup/people/p1/sign-out",
    });
    expect(lastInit().body).toBeUndefined();
  });

  it("sends the version, and the reason only when deactivating", async () => {
    await peopleApi.lifecycle("p1", "activate", { version: 4 });
    expect(lastCall()).toMatchObject({
      path: "setup/people/p1/activate",
      body: { version: 4 },
    });
    await peopleApi.lifecycle("p1", "deactivate", {
      version: 4,
      reason: "left",
    });
    expect(lastCall()).toMatchObject({
      path: "setup/people/p1/deactivate",
      body: { version: 4, reason: "left" },
    });
  });
});

describe("recurring endpoints", () => {
  const body: SaveRecurringRequest = {
    name: "Insurance",
    kind: 1,
    amount: 100,
    frequency: 3,
    day: 1,
    lastDay: false,
    start: "2026-09-01",
    end: null,
    allocations: [{ vehicleId: "v1", amount: 100 }],
    expenseItemId: "e1",
    note: null,
    month: null,
  };

  it("creates with POST and updates with PUT to the item", async () => {
    await recurringApi.save(undefined, body);
    expect(lastCall()).toMatchObject({
      method: "POST",
      path: "setup/recurring",
      body: { name: "Insurance", amount: 100 },
    });
    await recurringApi.save({ id: "r1" }, body);
    expect(lastCall()).toMatchObject({
      method: "PUT",
      path: "setup/recurring/r1",
    });
  });

  it("stops with a confirmed, trimmed reason", async () => {
    await recurringApi.stop("r1", " loan paid off ");
    expect(lastCall()).toMatchObject({
      method: "POST",
      path: "setup/recurring/r1/stop",
      body: { confirmed: true, reason: "loan paid off" },
    });
  });

  it("restores with an empty JSON body", async () => {
    await recurringApi.restore("r1");
    expect(lastCall()).toMatchObject({
      method: "POST",
      path: "setup/recurring/r1/restore",
      body: {},
    });
    expect(lastInit().body).toBe("{}");
  });
});
