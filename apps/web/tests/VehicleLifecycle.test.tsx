import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { RecurringEditor } from "../components/RecurringEditor";
import { VehiclesPage } from "../components/setup";
import { renderInApp } from "./renderInApp";

// The business date is 21 Sep. A vehicle joining on 3 Oct is not active yet, but it has not left the fleet either:
// only a leave date means a vehicle is retired.
const businessDate = "2026-09-21";
const base = { companyId: "company-1", companyName: "North Star", weeklyTarget: 15000, targets: [], recurringItems: 0 };
const joining = { ...base, id: "joining", registration: "KDA 482M", joinedOn: "2026-10-03", leftOn: null, active: false };
const retired = { ...base, id: "retired", registration: "KCY 117T", joinedOn: "2026-01-01", leftOn: "2026-09-10", active: false };
const running = { ...base, id: "running", registration: "KDG 905B", joinedOn: "2026-01-01", leftOn: null, active: true };

// The vehicle list, as the API sends it after each save.
function serve(lists: unknown[][]) {
  let reads = 0;
  const fetchMock = vi.fn(async (input: string, init?: RequestInit) => {
    if (init?.method) return new Response(JSON.stringify({ id: input.split("/")[4] }), { status: 200 });
    if (input.includes("company-options")) return new Response(JSON.stringify([{ id: "company-1", name: "North Star" }]), { status: 200 });
    if (input.includes("/recurring"))
      return new Response(
        JSON.stringify({
          items: [{ id: "parking", name: "Parking", kind: 1, amount: 700, activeAmount: 0, frequency: 2, day: 1, lastDay: false, start: "2026-09-01", allocations: [{ vehicleId: "joining", amount: 700, registration: "KDA 482M", active: false }] }],
          pageNumber: 1,
          pageSize: 25,
          total: 1,
        }),
        { status: 200 },
      );
    const items = lists[Math.min(reads, lists.length - 1)];
    reads += 1;
    return new Response(JSON.stringify({ items, pageNumber: 1, pageSize: 25, total: items.length }), { status: 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const row = (registration: string) => within(screen.getByRole("row", { name: new RegExp(registration) }));
// The badge in the vehicle's Status cell.
const status = (registration: string) => row(registration).getByText(/Active|Left|Joins/, { selector: "td[data-label='Status'] > *" });

it("tells a vehicle that has not joined yet from one that has left the fleet", async () => {
  serve([[joining, retired, running]]);
  renderInApp(<VehiclesPage />, { permissions: ["vehicles.manage", "commitments.view"] }, { businessDate });

  await screen.findByRole("button", { name: "KDA 482M" });
  expect(status("KDA 482M")).toHaveTextContent("Joins 3 Oct 2026");
  expect(status("KCY 117T")).toHaveTextContent("Left fleet 10 Sep 2026");
  expect(status("KDG 905B")).toHaveTextContent("Active");
  // Leaving the fleet ends the target; a vehicle that has not joined yet keeps the one it starts on.
  expect(row("KCY 117T").getByText("Target ended")).toBeInTheDocument();
  expect(row("KCY 117T").queryByText(/KES/)).not.toBeInTheDocument();
  expect(row("KDA 482M").getByText("KES 15,000")).toBeInTheDocument();
});

it("lets a vehicle that has not joined yet be edited, and shows what the server saved", async () => {
  const moved = { ...joining, joinedOn: "2026-09-20", active: true, weeklyTarget: 16000, targets: [{ effectiveFrom: "2026-09-20", weeklyAmount: 16000, revision: 2 }, { effectiveFrom: "2026-09-20", weeklyAmount: 15000, revision: 1 }] };
  const fetchMock = serve([[joining], [moved]]);
  renderInApp(<VehiclesPage />, { permissions: ["vehicles.manage", "commitments.view"] }, { businessDate });

  fireEvent.click(await screen.findByRole("button", { name: "KDA 482M" }));
  expect(screen.getByText("North Star · Joins 3 Oct 2026")).toBeInTheDocument();
  expect(screen.getByText("Joins the fleet on 3 Oct 2026, after the business date. To save a change, set a join date on or before 21 Sep 2026.")).toBeInTheDocument();
  expect(screen.getByLabelText("Weekly performance target")).toBeEnabled();
  expect(screen.queryByRole("button", { name: "Restore to active fleet" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Retire vehicle" })).not.toBeInTheDocument();
  expect(screen.getByText("It can leave the fleet once it has joined.")).toBeInTheDocument();

  fireEvent.change(screen.getByLabelText("In the fleet from"), { target: { value: "2026-09-20" } });
  fireEvent.change(screen.getByLabelText("Weekly performance target"), { target: { value: "16000" } });
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/setup/vehicles/joining", expect.objectContaining({ method: "PUT" })));

  // The editor shows the vehicle as the server now has it: in the fleet, with its new target history.
  expect(await screen.findByText("Target history")).toBeInTheDocument();
  expect(screen.queryByText(/Joins 3 Oct 2026/)).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Retire vehicle" })).toBeInTheDocument();
});

it("keeps a retired vehicle read-only until it is restored, and reloads it after retiring", async () => {
  const left = { ...running, leftOn: "2026-09-21", active: false };
  const fetchMock = serve([[retired, running], [retired, left]]);
  renderInApp(<VehiclesPage />, { permissions: ["vehicles.manage"] }, { businessDate });

  fireEvent.click(await screen.findByRole("button", { name: "KCY 117T" }));
  expect(screen.getByLabelText("Weekly performance target")).toBeDisabled();
  expect(screen.getByRole("button", { name: "Restore to active fleet" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

  fireEvent.click(await screen.findByRole("button", { name: "KDG 905B" }));
  fireEvent.click(screen.getByRole("button", { name: "Retire vehicle" }));
  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/setup/vehicles/running/retire", expect.objectContaining({ method: "POST" })));
  expect(await screen.findByText("Left the fleet on 21 Sep 2026.")).toBeInTheDocument();
  // The form keeps the target the server has.
  expect(screen.getByLabelText("Weekly performance target")).toHaveValue("15,000");
});

// D4: restoring a vehicle whose leave already took effect records the days it was away, so the editor has to say
// which day it comes back and then show the stretch it missed.
it("restores a retired vehicle on a chosen date and lists the days it was away", async () => {
  const back = { ...retired, leftOn: null, active: true, away: [{ leftOn: "2026-09-10", returnedOn: "2026-09-21" }] };
  const fetchMock = serve([[retired], [back]]);
  renderInApp(<VehiclesPage />, { permissions: ["vehicles.manage"] }, { businessDate });

  fireEvent.click(await screen.findByRole("button", { name: "KCY 117T" }));
  // The return date follows the business date until someone chooses another.
  expect(screen.getByLabelText("Returns to the fleet")).toHaveValue("2026-09-21");
  expect(screen.getByText("10 to 20 Sep 2026 is recorded as time away: those days are neither expected nor missing.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Restore to active fleet" }));
  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/setup/vehicles/retired/restore",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ returnedOn: "2026-09-21" }) }),
    ),
  );

  expect(await screen.findByText("Time away from the fleet")).toBeInTheDocument();
  expect(screen.getByText("10 to 20 Sep 2026")).toBeInTheDocument();
  expect(screen.getByText("Back on 21 Sep 2026")).toBeInTheDocument();
  // Back in the fleet, so it can be edited and retired again.
  expect(screen.getByLabelText("Weekly performance target")).toBeEnabled();
  expect(screen.getByRole("button", { name: "Retire vehicle" })).toBeInTheDocument();
});

it("says a return on the day it left undoes the leave instead of recording time away", async () => {
  const fetchMock = serve([[retired]]);
  renderInApp(<VehiclesPage />, { permissions: ["vehicles.manage"] }, { businessDate });

  fireEvent.click(await screen.findByRole("button", { name: "KCY 117T" }));
  fireEvent.change(screen.getByLabelText("Returns to the fleet"), { target: { value: "2026-09-10" } });
  expect(screen.getByText("Returning on the day it left undoes the leave outright.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Restore to active fleet" }));
  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/setup/vehicles/retired/restore",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ returnedOn: "2026-09-10" }) }),
    ),
  );
  expect(screen.queryByText("Time away from the fleet")).not.toBeInTheDocument();
});

it("says a share for a vehicle that is not in the fleet today does not post, without calling it retired", () => {
  vi.stubGlobal("fetch", vi.fn());
  const item = {
    id: "parking",
    name: "Parking",
    kind: 1,
    amount: 700,
    activeAmount: 0,
    frequency: 2,
    day: 1,
    lastDay: false,
    start: "2026-09-01",
    expenseItemId: "parking-item",
    expenseItemName: "Parking",
    bucket: 2 as const,
    allocations: [{ vehicleId: "joining", amount: 700, registration: "KDA 482M", active: false }],
  };
  renderInApp(<RecurringEditor item={item} vehicles={[{ ...joining, active: false }]} onCancel={vi.fn()} onSaved={vi.fn()} />, {}, { businessDate });

  expect(screen.getByLabelText("KDA 482M (not in the fleet today)")).toBeChecked();
  expect(screen.getByText(/KDA 482M is not in the fleet today, so its share stays in the total but does not post/)).toBeInTheDocument();
  expect(screen.queryByText(/left the fleet/i)).not.toBeInTheDocument();
});
