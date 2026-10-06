import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { AppShell } from "../components/AppShell";
import { appearanceFixture } from "./renderInApp";

type Scope = {
  allCompanies: boolean;
  companies: { id: string; name: string }[];
  vehicles: { id: string; registration: string; companyId: string }[];
};

const company = (id: string, name: string) => ({ id, name });
const vehicle = (id: string, registration: string) => ({ id, registration, companyId: "c1" });

// Signs in and records every path the shell asks for, so a test can assert that "Your access" is
// answered by the server rather than worked out from the session.
function signIn(scope: Scope | { status: number }) {
  const asked: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string) => {
      asked.push(input);
      if (input.includes("/auth/session"))
        return new Response(JSON.stringify({ userId: "me", firstName: "Test", lastName: "User", role: "Fleet manager", permissions: [] }), { status: 200 });
      if (input.includes("appearance")) return new Response(JSON.stringify(appearanceFixture("2026-09-30")), { status: 200 });
      if (input.includes("access/me"))
        return "status" in scope
          ? new Response(JSON.stringify({ title: "Unavailable" }), { status: scope.status })
          : new Response(JSON.stringify(scope), { status: 200 });
      if (input.includes("access/catalog")) return new Response(JSON.stringify([]), { status: 200 });
      return new Response(JSON.stringify({ items: [], pageNumber: 1, pageSize: 100, total: 0 }), { status: 200 });
    }),
  );
  render(<AppShell onSignOut={() => {}} />);
  return asked;
}

async function openYourAccess() {
  fireEvent.click(await screen.findByRole("button", { name: /Test User/i }));
  fireEvent.click(await screen.findByRole("menuitem", { name: "Your access" }));
  return within(await screen.findByRole("dialog", { name: "Your access" }));
}

it("asks the server what the person can see", async () => {
  const asked = signIn({ allCompanies: false, companies: [company("c1", "Zuri Genesis")], vehicles: [vehicle("v1", "KDA 482M")] });
  const dialog = await openYourAccess();
  expect(await dialog.findByText("Zuri Genesis")).toBeInTheDocument();
  expect(asked.some((path) => path.includes("setup/access/me"))).toBe(true);
});

it("names the companies while there are few, and counts them after that", async () => {
  signIn({
    allCompanies: false,
    companies: [company("c1", "Zuri Genesis"), company("c2", "Nairobi Fleet"), company("c3", "Rift Movers")],
    vehicles: [vehicle("v1", "KDA 482M"), vehicle("v2", "KDB 100A")],
  });
  const dialog = await openYourAccess();
  expect(await dialog.findByText("3 companies")).toBeInTheDocument();
  expect(dialog.getByText("2 vehicles")).toBeInTheDocument();
});

it("says All companies for an organization-wide viewer, with no vehicle count", async () => {
  signIn({ allCompanies: true, companies: [company("c1", "Zuri Genesis")], vehicles: [vehicle("v1", "KDA 482M")] });
  const dialog = await openYourAccess();
  expect(await dialog.findByText("All companies")).toBeInTheDocument();
  expect(dialog.queryByText("1 vehicle")).not.toBeInTheDocument();
});

it("says so when the scope cannot be fetched, instead of claiming no access", async () => {
  signIn({ status: 503 });
  const dialog = await openYourAccess();
  expect(await dialog.findByText("Connect to see what you can reach.", {}, { timeout: 6000 })).toBeInTheDocument();
  expect(dialog.queryByText("All companies")).not.toBeInTheDocument();
});
