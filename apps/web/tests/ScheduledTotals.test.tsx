import { fireEvent, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { RecurringEditor } from "../components/RecurringEditor";
import { RecurringPage } from "../components/setup";
import { renderInApp } from "./renderInApp";

// `amount` is the saved total of every share, including vehicles that have left the fleet; `activeAmount` is what
// still posts.
const businessDate = "2026-09-21";
const north = {
  id: "v-1",
  companyId: "c-1",
  companyName: "North Star",
  registration: "KDA 482M",
};
const south = {
  id: "v-2",
  companyId: "c-1",
  companyName: "North Star",
  registration: "KCY 117T",
};
const retired = {
  id: "v-3",
  companyId: "c-1",
  companyName: "North Star",
  registration: "KDG 905B",
  active: false,
};

const item = {
  id: "parking",
  name: "Parking",
  kind: 1,
  category: null,
  amount: 2000,
  activeAmount: 1200,
  frequency: 3,
  day: 5,
  lastDay: false,
  start: "2026-10-01",
  end: null,
  stoppedFrom: null,
  expenseItemId: "parking-item",
  expenseItemName: "Parking",
  bucket: 2 as const,
  note: null,
  month: null,
  allocations: [
    {
      vehicleId: north.id,
      amount: 600,
      registration: north.registration,
      active: true,
    },
    {
      vehicleId: south.id,
      amount: 600,
      registration: south.registration,
      active: true,
    },
    {
      vehicleId: retired.id,
      amount: 800,
      registration: retired.registration,
      active: false,
    },
  ],
};

const expenseItems = [
  {
    id: "parking-item",
    name: "Parking",
    categoryId: "charges",
    categoryName: "Charges",
    bucket: 2 as const,
  },
];

function renderEditor() {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(JSON.stringify({ id: item.id }), { status: 200 }),
    ),
  );
  renderInApp(
    <RecurringEditor
      item={item}
      vehicles={[north, south, retired]}
      expenseItems={expenseItems}
      onCancel={vi.fn()}
      onSaved={vi.fn()}
    />,
    {},
    { businessDate },
  );
}

it("lists what posts now, and says when retired shares make the saved total larger", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            items: [item],
            pageNumber: 1,
            pageSize: 25,
            total: 1,
          }),
          { status: 200 },
        ),
    ),
  );
  renderInApp(<RecurringPage canManage={false} />, {}, { businessDate });

  const cell = await screen.findByText("KES 1,200", {
    selector: "td[data-label='Amount each time']",
  });
  expect(
    within(cell).getByText(
      /KES 2,000 in total, with 1 share for a vehicle not in the fleet today/,
    ),
  ).toBeInTheDocument();
  expect(within(cell).getByText(/About KES 1,200 a month/)).toBeInTheDocument();
});

it("opens balanced, with a retired vehicle's share counted and read-only", () => {
  renderEditor();

  expect(screen.getByLabelText("Amount each time")).toHaveValue("2,000");
  expect(screen.getByText("Balanced")).toBeInTheDocument();
  expect(screen.getByLabelText("Share for KDG 905B")).toBeDisabled();
  expect(screen.getByLabelText("Share for KDG 905B")).toHaveValue("800");
  expect(
    screen.getByText(
      /KDG 905B is not in the fleet today, so its share stays in the total but does not post/,
    ),
  ).toBeInTheDocument();
  // What will post leaves out the retired vehicle.
  expect(
    screen.getByText("5 Oct 2026: KES 1,200 across 2 vehicles"),
  ).toBeInTheDocument();
  expect(screen.getByText(/About KES 1,200 a month/)).toBeInTheDocument();
});

it("splits equally across the vehicles still in the fleet and keeps the retired share", () => {
  renderEditor();

  fireEvent.change(screen.getByLabelText("Amount each time"), {
    target: { value: "2200" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Split equally" }));

  expect(screen.getByLabelText("Share for KDA 482M")).toHaveValue("700");
  expect(screen.getByLabelText("Share for KCY 117T")).toHaveValue("700");
  expect(screen.getByLabelText("Share for KDG 905B")).toHaveValue("800");
  expect(screen.getByText("Balanced")).toBeInTheDocument();
});

it("takes a removed retired share off the amount, so the form stays balanced", () => {
  renderEditor();

  fireEvent.click(screen.getByLabelText("KDG 905B (not in the fleet today)"));

  expect(screen.getByLabelText("Amount each time")).toHaveValue("1,200");
  expect(screen.getByText("Balanced")).toBeInTheDocument();
  expect(
    screen.getByText("Took KDG 905B's KES 800 share off the amount."),
  ).toBeInTheDocument();
  expect(
    screen.getByLabelText("KDG 905B (not in the fleet today)"),
  ).toBeDisabled();
});
