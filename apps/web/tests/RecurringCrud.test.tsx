import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { RecurringEditor } from "../components/RecurringEditor";
import { RecurringPage } from "../components/setup";

const vehicle = {
  id: "vehicle-1",
  companyId: "company-1",
  companyName: "North Star",
  registration: "KDA 482M",
  joinedOn: "2026-01-01",
  weeklyTarget: 15000,
};

const item = {
  id: "item-1",
  name: "Loan repayment",
  kind: 1,
  category: 4,
  amount: 1200,
  frequency: 2,
  day: 6,
  lastDay: false,
  start: "2026-10-01",
  end: null,
  stoppedFrom: null,
  allocations: [{ vehicleId: vehicle.id, amount: 1200 }],
};

function mockFetch(
  handler: (input: RequestInfo | URL, init?: RequestInit) => Response | Promise<Response>,
) {
  const fetchMock = vi.fn(handler);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

beforeEach(() => {
  mockFetch(async () => new Response(JSON.stringify({ id: item.id }), { status: 200 }));
});

it("reads recurring items with the reference summary and hides Add without manage permission", async () => {
  // A view-only user has no vehicle access: every vehicle endpoint is forbidden.
  const fetchMock = mockFetch(async (input) => {
    if (String(input).endsWith("/recurring?page=1&pageSize=25"))
      return new Response(JSON.stringify({ items: [{ ...item, frequency: 1, day: null, amount: 1000, start: "2026-09-27", allocations: [{ vehicleId: vehicle.id, amount: 1000, registration: vehicle.registration }] }], pageNumber: 1, pageSize: 25, total: 1 }), { status: 200 });
    return new Response(JSON.stringify({ title: "Not permitted in this organization or data scope." }), { status: 403 });
  });

  render(<RecurringPage canManage={false} />);

  expect(await screen.findByRole("button", { name: "Loan repayment" })).toBeInTheDocument();
  expect(screen.getByText("About KES 30,400 a month")).toBeInTheDocument();
  expect(screen.getByText("Every day")).toBeInTheDocument();
  expect(screen.getByText("1 vehicle")).toBeInTheDocument();
  expect(screen.getByText("KDA 482M")).toBeInTheDocument();
  const row = screen.getByRole("row", { name: /Loan repayment/ });
  const nextPosting = within(row).getAllByText("27 Sep 2026", { exact: true })[1];
  expect(nextPosting.closest("td")).toHaveAttribute("data-label", "Next posting");
  expect(screen.queryByRole("button", { name: "Add recurring cost or saving" })).not.toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(fetchMock.mock.calls.map(([input]) => String(input))).toEqual(["/api/setup/recurring?page=1&pageSize=25"]);
});

it("creates a recurring item with a balanced vehicle share", async () => {
  const fetchMock = mockFetch(async () => new Response(JSON.stringify({ id: item.id }), { status: 200 }));
  const onSaved = vi.fn(async () => undefined);
  render(<RecurringEditor vehicles={[vehicle]} onCancel={vi.fn()} onSaved={onSaved} />);

  fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Daily collection" } });
  fireEvent.change(screen.getByLabelText("Amount each time"), { target: { value: "1200" } });
  fireEvent.click(screen.getByRole("radio", { name: "Every day" }));
  fireEvent.click(screen.getByLabelText("KDA 482M"));
  expect(screen.getByText("Balanced")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Add" }));

  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
    "/api/setup/recurring",
    expect.objectContaining({ method: "POST" }),
  ));
  const body = JSON.parse(fetchMock.mock.calls[0][1]?.body as string);
  expect(body).toMatchObject({
    name: "Daily collection",
    kind: 1,
    amount: 1200,
    frequency: 1,
    day: null,
    lastDay: false,
    allocations: [{ vehicleId: vehicle.id, amount: 1200 }],
  });
  expect(onSaved).toHaveBeenCalledOnce();
});

it("updates a recurring item using its edited allocations and schedule", async () => {
  const fetchMock = mockFetch(async () => new Response(JSON.stringify({ id: item.id }), { status: 200 }));
  const onSaved = vi.fn(async () => undefined);
  render(<RecurringEditor item={item} vehicles={[vehicle]} onCancel={vi.fn()} onSaved={onSaved} />);

  fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Insurance" } });
  fireEvent.change(screen.getByLabelText("Amount each time"), { target: { value: "1350" } });
  fireEvent.change(screen.getByLabelText("Share for KDA 482M"), { target: { value: "1350" } });
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
    `/api/setup/recurring/${item.id}`,
    expect.objectContaining({ method: "PUT" }),
  ));
  const body = JSON.parse(fetchMock.mock.calls[0][1]?.body as string);
  expect(body).toMatchObject({
    name: "Insurance",
    amount: 1350,
    frequency: 2,
    day: 6,
    allocations: [{ vehicleId: vehicle.id, amount: 1350 }],
  });
  expect(onSaved).toHaveBeenCalledOnce();
});

it("requires a second click before stopping a recurring item", async () => {
  const fetchMock = mockFetch(async () => new Response(JSON.stringify({ id: item.id }), { status: 200 }));
  const onSaved = vi.fn(async () => undefined);
  render(<RecurringEditor item={item} vehicles={[vehicle]} onCancel={vi.fn()} onSaved={onSaved} />);

  fireEvent.click(screen.getByRole("button", { name: "Stop from today" }));
  expect(screen.getByRole("button", { name: "Tap again to stop from today" })).toBeInTheDocument();
  expect(fetchMock).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Tap again to stop from today" }));

  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
    `/api/setup/recurring/${item.id}/stop`,
    expect.objectContaining({ method: "POST" }),
  ));
  expect(JSON.parse(fetchMock.mock.calls[0][1]?.body as string)).toMatchObject({
    confirmed: true,
    reason: "Stopped recurring item",
  });
  expect(onSaved).toHaveBeenCalledOnce();
});