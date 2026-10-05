import { fireEvent, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { VehiclesPage } from "../components/setup";
import { renderInApp } from "./renderInApp";

const vehicle = {
  id: "vehicle-1",
  companyId: "company-1",
  companyName: "North Star",
  registration: "KDA 482M",
  joinedOn: "2026-01-01",
  leftOn: null,
  active: true,
  weeklyTarget: 15000,
  targets: [],
  recurringItems: 4,
};

const posting = (itemId: string, name: string, date: string, amount: number, extra: Record<string, unknown>) => ({
  itemId,
  versionId: `${itemId}-v1`,
  date,
  name,
  kind: 1,
  category: null,
  bucket: null,
  amount,
  ...extra,
});

// New costs carry a bucket and no category; rows saved before expense items carry only their old cost type.
const report = {
  vehicleId: vehicle.id,
  from: "2026-09-01",
  through: "2026-09-21",
  costs: 7000,
  savings: 2000,
  postings: [
    posting("loan", "Loan repayment", "2026-09-05", 5000, { bucket: 3 }),
    posting("parking", "Parking", "2026-09-07", 300, { bucket: 2 }),
    posting("parking", "Parking", "2026-09-14", 300, { bucket: 2 }),
    // Legacy: Repairs and upkeep (2) counts as Repairs and maintenance; any other old type as Recurring charges.
    posting("tyres", "Tyres", "2026-09-10", 1000, { category: 2 }),
    posting("insurance", "Insurance", "2026-09-12", 400, { category: 4 }),
    posting("savings", "Owner savings", "2026-09-19", 2000, { kind: 2 }),
  ],
};

it("totals the vehicle report by expense bucket, with old cost types counted in their bucket", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string) => {
      if (input.includes("/report")) return new Response(JSON.stringify(report), { status: 200 });
      if (input.includes("company-options")) return new Response(JSON.stringify([]), { status: 200 });
      return new Response(JSON.stringify({ items: [vehicle], pageNumber: 1, pageSize: 25, total: 1 }), { status: 200 });
    }),
  );
  renderInApp(<VehiclesPage />, { permissions: ["vehicles.manage"] }, { businessDate: "2026-09-21" });
  fireEvent.click(await screen.findByRole("button", { name: "KDA 482M" }));
  fireEvent.click(screen.getByRole("tab", { name: "Report" }));

  const stat = async (label: string) => (await screen.findByText(label, { selector: "small" })).nextElementSibling;
  expect(await stat("Repairs and maintenance")).toHaveTextContent("KES 1,000");
  expect(await stat("Recurring charges")).toHaveTextContent("KES 1,000");
  expect(await stat("Loan repayments")).toHaveTextContent("KES 5,000");
  expect(await stat("Savings set aside")).toHaveTextContent("KES 2,000");
  expect([...document.querySelectorAll("small")].map((node) => node.textContent)).toEqual(
    expect.not.arrayContaining(["Running costs", "Repairs and upkeep", "Crew costs", "Fixed commitments"]),
  );

  expect(screen.getByText("Loan repayments. 5 Sep 2026")).toBeInTheDocument();
  expect(screen.getByText("Recurring charges. 7 Sep 2026, 14 Sep 2026")).toBeInTheDocument();
  expect(screen.getByText("Repairs and maintenance. 10 Sep 2026")).toBeInTheDocument();
  expect(screen.getByText("Recurring charges. 12 Sep 2026")).toBeInTheDocument();
  expect(screen.getByText("Savings. 19 Sep 2026")).toBeInTheDocument();
  expect(screen.queryByText(/Fixed commitments|Running costs|Crew costs|Repairs and upkeep/)).not.toBeInTheDocument();
});
