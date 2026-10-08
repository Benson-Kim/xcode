import { fireEvent, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { VehiclesPage } from "../components/setup";
import type { VehicleReport } from "../components/setup/shared";
import { renderInApp } from "./renderInApp";

const vehicle = {
  id: "vehicle-1",
  companyId: "company-1",
  companyName: "North Star",
  registration: "KDA 482M",
  joinedOn: "2026-02-01",
  leftOn: null,
  active: true,
  weeklyTarget: 14000,
  targets: [],
  recurringItems: 5,
};

// Contract C6: the server works out every figure; the tab shows them as the design does.
const march: VehicleReport = {
  vehicleId: vehicle.id,
  from: "2026-03-01",
  through: "2026-03-31",
  moneyIn: 43500,
  target: 45000,
  repairs: 4600,
  charges: 50,
  loans: 10000,
  moneyOut: 14650,
  net: 28850,
  savings: 1000,
  afterSavings: 27850,
  costs: 14650,
  postings: [
    {
      itemId: "tyres",
      versionId: "v3",
      date: "2026-03-01",
      name: "Tyres",
      kind: 1,
      amount: 100,
      bucket: 1,
    },
    // A cost saved without a bucket counts as a recurring charge, as the API reports it.
    {
      itemId: "lunch",
      versionId: "v4",
      date: "2026-03-02",
      name: "Crew lunch",
      kind: 1,
      amount: 50,
      bucket: null,
    },
    {
      itemId: "savings",
      versionId: "v6",
      date: "2026-03-06",
      name: "Owner savings",
      kind: 2,
      amount: 1000,
      bucket: null,
    },
    {
      itemId: "service",
      versionId: "v1",
      date: "2026-03-10",
      name: "Service",
      kind: 1,
      amount: 2000,
      bucket: 1,
    },
    {
      itemId: "service",
      versionId: "v2",
      date: "2026-03-25",
      name: "Service",
      kind: 1,
      amount: 2500,
      bucket: 1,
    },
    {
      itemId: "loan",
      versionId: "v5",
      date: "2026-03-31",
      name: "Loan repayment",
      kind: 1,
      amount: 10000,
      bucket: 3,
    },
  ],
};

function serve(report: VehicleReport) {
  const fetchMock = vi.fn(async (input: string) => {
    if (input.includes("/report"))
      return new Response(JSON.stringify(report), { status: 200 });
    if (input.includes("company-options"))
      return new Response(
        JSON.stringify([{ id: "company-1", name: "North Star" }]),
        { status: 200 },
      );
    return new Response(
      JSON.stringify({
        items: [vehicle],
        pageNumber: 1,
        pageSize: 25,
        total: 1,
      }),
      { status: 200 },
    );
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

async function openReport() {
  renderInApp(
    <VehiclesPage />,
    { permissions: ["vehicles.manage"] },
    { businessDate: "2026-03-31" },
  );
  fireEvent.click(await screen.findByRole("button", { name: "KDA 482M" }));
  fireEvent.click(screen.getByRole("tab", { name: "Report" }));
  await screen.findByText("Money in", { selector: "small" });
}

const stats = () =>
  [
    ...screen.getByText("Money in", { selector: "small" }).parentElement!
      .parentElement!.children,
  ].map((stat) => [
    stat.querySelector("small")!.textContent,
    stat.querySelector("strong")!.textContent,
  ]);

it("shows money in, the target, the three buckets, money out, net and savings in the design's order", async () => {
  const fetchMock = serve(march);
  await openReport();

  expect(fetchMock).toHaveBeenCalledWith(
    "/api/setup/vehicles/vehicle-1/report?period=month",
    expect.anything(),
  );
  expect(
    screen.getByRole("heading", { name: "This month, 1 to 31 Mar 2026" }),
  ).toBeInTheDocument();
  expect(
    screen.getByText(
      "Money in and money out, counted on the day it moved. Fuel and crew pay are not tracked; revenue is recorded net of them.",
    ),
  ).toBeInTheDocument();
  expect(stats()).toEqual([
    ["Money in", "KES 43,500"],
    ["Target", "KES 45,000"],
    ["Repairs and maintenance", "KES 4,600"],
    ["Recurring charges", "KES 50"],
    ["Loan repayments", "KES 10,000"],
    ["Money out", "KES 14,650"],
    ["Net contribution", "KES 28,850"],
    ["Savings set aside", "KES 1,000"],
    ["After savings", "KES 27,850"],
  ]);
});

it("lists each item's postings under its bucket, or as savings", async () => {
  serve(march);
  await openReport();

  const list = within(screen.getByRole("list"));
  const rows = list.getAllByRole("listitem").map((row) => row.textContent);
  expect(rows).toEqual([
    "TyresRepairs and maintenance. 1 Mar 2026KES 100",
    "Crew lunchRecurring charges. 2 Mar 2026KES 50",
    "Owner savingsSavings. 6 Mar 2026KES 1,000",
    "ServiceRepairs and maintenance. 10 Mar 2026, 25 Mar 2026KES 4,500",
    "Loan repaymentLoan repayments. 31 Mar 2026KES 10,000",
  ]);
});

it("shows a loss as a loss, in red, and follows the period chosen", async () => {
  const fetchMock = serve({
    ...march,
    moneyIn: 12000,
    net: -2650,
    afterSavings: -3650,
  });
  await openReport();

  const value = (label: string) =>
    screen.getByText(label, { selector: "small" }).nextElementSibling!;
  expect(value("Net contribution")).toHaveTextContent("KES 2,650 loss");
  expect(value("Net contribution")).toHaveClass("text-red");
  expect(value("After savings")).toHaveTextContent("KES 3,650 loss");
  expect(value("Money out")).not.toHaveClass("text-red");

  fireEvent.click(screen.getByRole("button", { name: "This week" }));
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/setup/vehicles/vehicle-1/report?period=week",
    expect.anything(),
  );
});

it("keeps a revision that moved an item to another bucket on its own line, not under the first version's bucket", async () => {
  serve({
    ...march,
    postings: [
      {
        itemId: "van",
        versionId: "v1",
        date: "2026-03-05",
        name: "Repair",
        kind: 1,
        amount: 3000,
        bucket: 1,
      },
      {
        itemId: "van",
        versionId: "v2",
        date: "2026-03-20",
        name: "Loan",
        kind: 1,
        amount: 8000,
        bucket: 3,
      },
    ],
  });
  await openReport();

  const rows = within(screen.getByRole("list"))
    .getAllByRole("listitem")
    .map((row) => row.textContent);
  expect(rows).toEqual([
    "RepairRepairs and maintenance. 5 Mar 2026KES 3,000",
    "LoanLoan repayments. 20 Mar 2026KES 8,000",
  ]);
});
