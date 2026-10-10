import { fireEvent, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import { PeopleAccessView } from "../components/PeopleAccessView";
import { CompaniesPage } from "../components/setup/CompaniesPage";
import { RecurringPage } from "../components/setup/RecurringPage";
import { fakeApi, type Sent } from "./fakeApi";
import { catalogFixture, personFixture, rolesFixture } from "./fixtures";
import { renderInApp } from "./renderInApp";
import { pick } from "./searchSelect";

// A paged API list: the page and size asked for, and the total of all of it.
function paged<T>(all: T[]) {
  return (sent: Sent) => {
    const query = new URL(sent.path, "http://localhost").searchParams;
    const pageSize = Number(query.get("pageSize"));
    const page = Number(query.get("page"));
    return [
      200,
      {
        items: all.slice((page - 1) * pageSize, page * pageSize),
        pageNumber: page,
        pageSize,
        total: all.length,
      },
    ] as const;
  };
}

const reads = (api: ReturnType<typeof fakeApi>, prefix: string) =>
  api.calls
    .filter((call) => call.method === "GET" && call.path.startsWith(prefix))
    .map((call) => call.path);

it("pages PSV companies on the server, 25 to a page", async () => {
  const api = fakeApi();
  const companies = Array.from({ length: 60 }, (_, index) => ({
    id: `c-${index + 1}`,
    name: `Company ${String(index + 1).padStart(2, "0")}`,
    vehicleCount: 1,
    active: true,
  }));
  api.on("setup/companies*", paged(companies));
  renderInApp(<CompaniesPage />, { permissions: ["companies.manage"] });

  expect(await screen.findByText("Company 25")).toBeInTheDocument();
  expect(reads(api, "setup/companies")).toEqual([
    "setup/companies?page=1&pageSize=25",
  ]);
  expect(screen.queryByText("Company 26")).not.toBeInTheDocument();
  expect(screen.getByText("Showing 1–25 of 60")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Next page" }));
  expect(await screen.findByText("Company 26")).toBeInTheDocument();
  expect(reads(api, "setup/companies").at(-1)).toBe(
    "setup/companies?page=2&pageSize=25",
  );
  expect(screen.queryByText("Company 01")).not.toBeInTheDocument();

  pick(screen.getByLabelText("Rows per page"), "50");
  expect(await screen.findByText("Showing 1–50 of 60")).toBeInTheDocument();
  expect(reads(api, "setup/companies").at(-1)).toBe(
    "setup/companies?page=1&pageSize=50",
  );
});

it("pages People and access on the server, filters included", async () => {
  const api = fakeApi();
  const people = Array.from({ length: 60 }, (_, index) =>
    personFixture({
      id: `p-${index + 1}`,
      firstName: `Person${String(index + 1).padStart(2, "0")}`,
      lastName: "Test",
      role: index % 2 ? "Fleet manager" : "Revenue clerk",
    }),
  );
  api.on("setup/people*", (sent) => {
    const role = new URL(sent.path, "http://localhost").searchParams.get(
      "role",
    );
    return paged(role ? people.filter((x) => x.role === role) : people)(sent);
  });
  api.on("setup/access/catalog", [200, catalogFixture]);
  api.on("setup/access/roles", [200, rolesFixture]);
  renderInApp(<PeopleAccessView />, { permissions: ["people.view"] });

  expect(
    await screen.findByRole("button", { name: "View Person25 Test" }),
  ).toBeInTheDocument();
  expect(reads(api, "setup/people")).toEqual([
    "setup/people?page=1&pageSize=25",
  ]);
  expect(screen.getByText("Showing 1–25 of 60")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Page 2" }));
  expect(
    await screen.findByRole("button", { name: "View Person26 Test" }),
  ).toBeInTheDocument();
  expect(reads(api, "setup/people").at(-1)).toBe(
    "setup/people?page=2&pageSize=25",
  );

  // A filter goes to the server, which counts and pages the matches from the first page.
  fireEvent.change(screen.getByLabelText("Role"), {
    target: { value: "Fleet manager" },
  });
  expect(await screen.findByText("Showing 1–25 of 30")).toBeInTheDocument();
  expect(reads(api, "setup/people").at(-1)).toBe(
    "setup/people?role=Fleet+manager&page=1&pageSize=25",
  );
  expect(
    screen.getByRole("button", { name: "View Person40 Test" }),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "View Person39 Test" }),
  ).toBeNull();
});

it("pages Scheduled expenses and savings on the server", async () => {
  const api = fakeApi();
  const items = Array.from({ length: 30 }, (_, index) => ({
    id: `item-${index + 1}`,
    name: `Cost ${String(index + 1).padStart(2, "0")}`,
    kind: 1,
    category: null,
    amount: 100,
    frequency: 2,
    day: 6,
    lastDay: false,
    start: "2026-10-01",
    end: null,
    stoppedFrom: null,
    allocations: [],
    expenseItemId: "loan",
    expenseItemName: "Loan repayment",
    bucket: 3,
    note: null,
    month: null,
  }));
  api.on("setup/recurring*", paged(items));
  api.on("setup/recurring/vehicle-options", [200, []]);
  renderInApp(
    <RecurringPage canManage />,
    { permissions: ["commitments.view", "commitments.manage"] },
    { businessDate: "2026-10-09" },
  );

  expect(await screen.findByText("Cost 25")).toBeInTheDocument();
  expect(reads(api, "setup/recurring?")).toEqual([
    "setup/recurring?kind=cost&page=1&pageSize=25",
  ]);
  expect(screen.queryByText("Cost 26")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Next page" }));
  expect(await screen.findByText("Cost 30")).toBeInTheDocument();
  expect(reads(api, "setup/recurring?").at(-1)).toBe(
    "setup/recurring?kind=cost&page=2&pageSize=25",
  );
});
