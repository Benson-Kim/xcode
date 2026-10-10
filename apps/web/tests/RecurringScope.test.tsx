import { fireEvent, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { RecurringPage } from "../components/setup";
import { renderInApp } from "./renderInApp";

const vehicle = {
  id: "vehicle-1",
  companyId: "company-1",
  companyName: "North Star",
  registration: "KDA 482M",
};

// A cost split with vehicles outside the viewer's scope: the API sends only their share and marks it partial.
const shared = {
  id: "item-1",
  name: "Office rent",
  kind: 1,
  category: 4,
  amount: 1000,
  frequency: 3,
  day: 1,
  lastDay: false,
  start: "2026-09-01",
  end: null,
  stoppedFrom: null,
  allocations: [
    { vehicleId: vehicle.id, amount: 1000, registration: vehicle.registration },
  ],
  partial: true,
};

it("opens an item shared with vehicles outside your scope read-only", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/recurring/vehicle-options"))
        return new Response(JSON.stringify([vehicle]), { status: 200 });
      if (url.includes("/expense-items/options"))
        return new Response(JSON.stringify([]), { status: 200 });
      return new Response(
        JSON.stringify({
          items: [shared],
          pageNumber: 1,
          pageSize: 25,
          total: 1,
        }),
        { status: 200 },
      );
    }),
  );

  renderInApp(<RecurringPage canManage />, {
    permissions: ["commitments.view", "commitments.manage"],
  });

  expect(
    await screen.findByTitle(/plus vehicles you can't see/),
  ).toBeInTheDocument();
  expect(screen.getByTitle(/Your vehicles' share/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Open Office rent" }));
  expect(
    await screen.findByText(
      /only someone who can see all of them can change it/,
    ),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: /save/i }),
  ).not.toBeInTheDocument();
});
