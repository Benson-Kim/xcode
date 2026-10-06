import { afterEach, expect, it, vi } from "vitest";

import { apiRequest } from "../lib/data";

afterEach(() => vi.unstubAllGlobals());

const refuse = (body: object) => vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status: 403 })));

// Every setup screen shows the error message of the shared request helper, so this is what each one says.
it("says why a change was refused when the server gives the reason", async () => {
  refuse({ title: "Not permitted in this organization or data scope.", status: 403, detail: "Only an Owner may give the Owner role." });
  await expect(apiRequest("setup/people")).rejects.toThrow("Only an Owner may give the Owner role.");
});

it("says a refusal without a reason in plain words", async () => {
  refuse({ title: "Not permitted in this organization or data scope.", status: 403 });
  await expect(apiRequest("setup/people")).rejects.toThrow("Your access does not include this. Ask your admin if you need it.");
});

it("falls back to the category for other failures without a reason", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ title: "Invalid security policy.", status: 400 }), { status: 400 })));
  await expect(apiRequest("setup/organization/settings/securityPolicy")).rejects.toThrow("Invalid security policy.");
});
