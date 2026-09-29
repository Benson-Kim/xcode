import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { RevenuePage } from "../components/RevenuePage";
import { renderInApp } from "./renderInApp";

const dates = ["2026-09-28", "2026-09-29", "2026-09-30", "2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04"];
const week = {
  weekStart: "2026-09-28",
  weekThrough: "2026-10-04",
  businessDate: "2026-09-29",
  companies: [{ id: "company-1", name: "North Star" }],
  vehicles: [{
    id: "vehicle-1",
    companyId: "company-1",
    companyName: "North Star",
    registration: "KDA 482M",
    joinedOn: "2026-09-28",
    leftOn: null,
    earliestMissing: "2026-09-28",
    days: dates.map((date, index) => ({
      date,
      status: index === 0 ? "missing" : index === 1 ? "amount" : "future",
      expected: 1000,
      amount: index === 1 ? 850 : null,
      reason: null,
      note: null,
      canEdit: index < 2,
      editedAfterCapture: false,
    })),
    totalAmount: 850,
    totalExpected: 2000,
    percent: 43,
  }],
  totalAmount: 850,
  totalExpected: 2000,
  percent: 43,
};

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    if (init?.method === "PUT") return new Response(JSON.stringify({ id: "record-1" }), { status: 200 });
    if (path.includes("/setup/revenue")) return new Response(JSON.stringify(week), { status: 200 });
    return new Response("{}", { status: 404 });
  }));
});

it("loads the weekly grid and saves a dated revenue amount", async () => {
  renderInApp(<RevenuePage />, {
    permissions: ["revenue.view", "revenue.capture", "revenue.no_earnings", "revenue.correct"],
  });

  expect(await screen.findByRole("button", { name: /KDA 482M, 28 Sep 2026: Missing/ })).toBeInTheDocument();
  expect(screen.getByText("North Star")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: /KDA 482M, 28 Sep 2026: Missing/ }));
  expect(screen.getByText("No earnings reason")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Revenue amount"), { target: { value: "1000" } });
  fireEvent.click(screen.getByRole("button", { name: "Save revenue" }));

  await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalledWith(
    "/api/setup/revenue/vehicle-1/2026-09-28",
    expect.objectContaining({ method: "PUT" }),
  ));
  const call = vi.mocked(fetch).mock.calls.find(([input, init]) => String(input).endsWith("/2026-09-28") && init?.method === "PUT");
  expect(JSON.parse(String(call?.[1]?.body))).toEqual({ amount: 1000, reason: null, note: null });
});
