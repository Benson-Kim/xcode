import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import type {
  RevenueCell,
  RevenueDay,
  RevenueDayVehicle,
  RevenueVehicle,
  RevenueWeek,
} from "@xcode/shared/revenue";

import { RevenuePage } from "../components/RevenuePage";
import { renderInApp } from "./renderInApp";
import { pick } from "./searchSelect";

// Monday to Sunday; the business date is the Wednesday. Capture revenue (design v2.28) takes one day for every vehicle.
const DATES = [
  "2026-09-28",
  "2026-09-29",
  "2026-09-30",
  "2026-10-01",
  "2026-10-02",
  "2026-10-03",
  "2026-10-04",
];
const TODAY = "2026-09-30";
const TUESDAY = "2026-09-29";
const CLERK = ["revenue.view", "revenue.capture", "revenue.no_earnings"];

function cell(date: string, over: Partial<RevenueCell> = {}): RevenueCell {
  const status = date > TODAY ? "future" : "missing";
  return {
    date,
    status,
    expected: 1000,
    amount: null,
    reason: null,
    note: null,
    canEdit: status === "missing",
    editedAfterCapture: false,
    version: null,
    ...over,
  };
}

const saved = (amount: number, version: number, canEdit = true) =>
  ({ status: "amount", amount, version, canEdit }) as const;

// The grid: KDA 482M has every day to today; KBZ 110A still misses Tuesday, so Capture revenue opens on Tuesday.
function gridVehicle(
  id: string,
  registration: string,
  days: Record<string, Partial<RevenueCell>>,
): RevenueVehicle {
  return {
    id,
    companyId: "company-1",
    companyName: "North Star",
    registration,
    joinedOn: "2026-01-01",
    leftOn: null,
    earliestMissing: null,
    days: DATES.map((date) => cell(date, days[date])),
    totalAmount: 0,
    totalExpected: 0,
    percent: null,
  };
}

const week: RevenueWeek = {
  weekStart: DATES[0],
  weekThrough: DATES[6],
  currentWeekStart: DATES[0],
  businessDate: TODAY,
  companies: [{ id: "company-1", name: "North Star" }],
  vehicles: [
    gridVehicle("vehicle-1", "KDA 482M", {
      [DATES[0]]: saved(900, 1, false),
      [DATES[1]]: saved(900, 1, false),
    }),
    gridVehicle("vehicle-2", "KBZ 110A", {
      [DATES[0]]: saved(800, 1, false),
    }),
  ],
  totalAmount: 0,
  totalExpected: 0,
  percent: null,
  pageNumber: 1,
  pageSize: 500,
  truncated: false,
  totalVehicles: 2,
  dayTotals: [],
  firstGap: null,
};

function row(
  id: string,
  registration: string,
  over: Partial<RevenueCell>,
  lastWeek: RevenueDayVehicle["lastWeek"],
): RevenueDayVehicle {
  return {
    id,
    companyId: "company-1",
    registration,
    day: cell(TUESDAY, over),
    lastWeek,
  };
}

// Tuesday for four vehicles: a missing day, a saved one the person may change, a missing one with nothing last week,
// and a saved one they may not change.
const tuesday = (over: Partial<Record<string, Partial<RevenueCell>>> = {}) =>
  ({
    date: TUESDAY,
    businessDate: TODAY,
    truncated: false,
    vehicles: [
      row(
        "vehicle-1",
        "KDA 482M",
        { ...over["vehicle-1"] },
        {
          amount: 1200,
          reason: null,
        },
      ),
      row(
        "vehicle-2",
        "KBZ 110A",
        { ...saved(900, 3), ...over["vehicle-2"] },
        { amount: null, reason: "Garage" },
      ),
      row("vehicle-3", "KCC 333C", { ...over["vehicle-3"] }, null),
      row("vehicle-4", "KDD 444D", saved(700, 1, false), {
        amount: 650,
        reason: null,
      }),
    ],
  }) satisfies RevenueDay;

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

function serve(
  days: (path: string) => RevenueDay,
  save: () => Response = () => json({ rows: [] }),
) {
  const fetcher = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (init?.method === "PUT") return save();
      if (path.startsWith("/api/setup/revenue/day")) return json(days(path));
      if (path.startsWith("/api/setup/revenue")) return json(week);
      return json({}, 404);
    },
  );
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
}

const weekReads = (fetcher: ReturnType<typeof serve>) =>
  fetcher.mock.calls.filter(([input]) => String(input) === "/api/setup/revenue")
    .length;

const calls = (fetcher: ReturnType<typeof serve>, fragment: string) =>
  fetcher.mock.calls
    .map(([input, init]) => ({ path: String(input), init }))
    .filter((call) => call.path.includes(fragment));

async function openCapture() {
  fireEvent.click(
    await screen.findByRole("button", { name: "Capture revenue" }),
  );
  const dialog = await screen.findByRole("dialog", { name: "Capture revenue" });
  await within(dialog).findByLabelText("Revenue, KDA 482M");
  return dialog;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

it("opens on the week's latest missing day with every vehicle, last week beside it and the day's total", async () => {
  const fetcher = serve(() => tuesday());
  renderInApp(<RevenuePage />, { permissions: CLERK });

  const dialog = await openCapture();
  expect(calls(fetcher, "/revenue/day")[0].path).toBe(
    `/api/setup/revenue/day?date=${TUESDAY}`,
  );
  expect(within(dialog).getByText("Tue 29 Sep 2026")).toBeInTheDocument();
  expect(
    within(dialog)
      .getAllByRole("columnheader")
      .map((header) => header.textContent),
  ).toEqual([
    "Vehicle",
    "Same day last week",
    "Revenue, KES",
    "No revenue reason",
  ]);
  const rows = within(dialog).getAllByRole("row");
  expect(within(rows[1]).getByText("1,200")).toBeInTheDocument();
  expect(within(rows[2]).getAllByRole("cell")[1]).toHaveTextContent("Garage");
  expect(within(dialog).getByLabelText("Revenue, KBZ 110A")).toHaveValue("900");
  // KDD 444D is saved and theirs to keep: shown, not offered.
  expect(within(rows[4]).getByText("700")).toBeInTheDocument();
  expect(within(dialog).queryByLabelText("Revenue, KDD 444D")).toBeNull();
  expect(within(rows[5]).getByText("4 vehicles")).toBeInTheDocument();
  expect(within(rows[5]).getByText("1,600")).toBeInTheDocument();
  // The cursor starts on the first vehicle with nothing recorded.
  await waitFor(() =>
    expect(within(dialog).getByLabelText("Revenue, KDA 482M")).toHaveFocus(),
  );

  fireEvent.change(within(dialog).getByLabelText("Revenue, KDA 482M"), {
    target: { value: "1100" },
  });
  expect(within(rows[5]).getByText("2,700")).toBeInTheDocument();
});

it("saves only the rows that changed, with the version each was read at, then closes and says so", async () => {
  const fetcher = serve(() => tuesday());
  renderInApp(<RevenuePage />, { permissions: CLERK });
  const dialog = await openCapture();
  const readsBefore = weekReads(fetcher);

  fireEvent.change(within(dialog).getByLabelText("Revenue, KDA 482M"), {
    target: { value: "1100" },
  });
  fireEvent.change(within(dialog).getByLabelText("Revenue, KBZ 110A"), {
    target: { value: "950.50" },
  });
  pick(within(dialog).getByLabelText("No revenue reason, KCC 333C"), "Garage");
  fireEvent.click(within(dialog).getByRole("button", { name: "Save day" }));

  await waitFor(() => expect(calls(fetcher, "/revenue/day/")).toHaveLength(1));
  const [put] = calls(fetcher, "/revenue/day/");
  expect(put.path).toBe(`/api/setup/revenue/day/${TUESDAY}`);
  expect(put.init?.method).toBe("PUT");
  expect(JSON.parse(String(put.init?.body))).toEqual({
    rows: [
      {
        vehicleId: "vehicle-1",
        amount: 1100,
        reason: null,
        note: null,
        version: null,
      },
      {
        vehicleId: "vehicle-2",
        amount: 950.5,
        reason: null,
        note: null,
        version: 3,
      },
      {
        vehicleId: "vehicle-3",
        amount: null,
        reason: "Garage",
        note: null,
        version: null,
      },
    ],
  });
  expect(await screen.findByText("Saved Tue 29 Sep 2026")).toBeInTheDocument();
  await waitFor(() =>
    expect(
      screen.queryByRole("dialog", { name: "Capture revenue" }),
    ).toBeNull(),
  );
  await waitFor(() => expect(weekReads(fetcher)).toBeGreaterThan(readsBefore));
});

it("skips blank rows, refuses to empty a saved one or leave Other unexplained, and names each vehicle", async () => {
  const fetcher = serve(() => tuesday());
  renderInApp(<RevenuePage />, { permissions: CLERK });
  const dialog = await openCapture();
  const save = within(dialog).getByRole("button", { name: "Save day" });

  fireEvent.click(save);
  expect(await within(dialog).findByRole("alert")).toHaveTextContent(
    "Enter the revenue or a no-earnings reason for at least one vehicle.",
  );

  fireEvent.change(within(dialog).getByLabelText("Revenue, KBZ 110A"), {
    target: { value: "" },
  });
  pick(within(dialog).getByLabelText("No revenue reason, KCC 333C"), "Other");
  fireEvent.click(save);
  const alert = await within(dialog).findByRole("alert");
  expect(alert).toHaveTextContent(
    "KBZ 110A: Enter the revenue or pick a reason. A saved day cannot be emptied.",
  );
  expect(alert).toHaveTextContent("KCC 333C: Say what happened.");
  expect(within(dialog).getByLabelText("Revenue, KBZ 110A")).toHaveAttribute(
    "aria-invalid",
    "true",
  );
  expect(calls(fetcher, "/revenue/day/")).toHaveLength(0);

  // Once each is right, KDA 482M, left blank, is not sent: its day stays open for later.
  fireEvent.change(within(dialog).getByLabelText("Revenue, KBZ 110A"), {
    target: { value: "900" },
  });
  fireEvent.change(within(dialog).getByLabelText("What happened, KCC 333C"), {
    target: { value: "Flat tyre" },
  });
  fireEvent.click(save);
  await waitFor(() => expect(calls(fetcher, "/revenue/day/")).toHaveLength(1));
  expect(
    JSON.parse(String(calls(fetcher, "/revenue/day/")[0].init?.body)).rows,
  ).toEqual([
    {
      vehicleId: "vehicle-3",
      amount: null,
      reason: "Other",
      note: "Flat tyre",
      version: null,
    },
  ]);
});

it("turns the reason off while an amount is typed, and an amount clears the reason", async () => {
  serve(() => tuesday());
  renderInApp(<RevenuePage />, { permissions: CLERK });
  const dialog = await openCapture();

  expect(
    within(dialog).getByLabelText("No revenue reason, KBZ 110A"),
  ).toBeDisabled();
  const reason = within(dialog).getByLabelText("No revenue reason, KCC 333C");
  pick(reason, "Arrest");
  expect(reason).toHaveValue("Arrest");
  fireEvent.change(within(dialog).getByLabelText("Revenue, KCC 333C"), {
    target: { value: "500" },
  });
  expect(reason).toBeDisabled();
  expect(reason).toHaveValue("");
});

it("moves down the revenue column on Enter, past rows that cannot change, then to Save day", async () => {
  serve(() => tuesday());
  renderInApp(<RevenuePage />, { permissions: CLERK });
  const dialog = await openCapture();

  fireEvent.keyDown(within(dialog).getByLabelText("Revenue, KDA 482M"), {
    key: "Enter",
  });
  expect(within(dialog).getByLabelText("Revenue, KBZ 110A")).toHaveFocus();
  fireEvent.keyDown(within(dialog).getByLabelText("Revenue, KBZ 110A"), {
    key: "Enter",
  });
  fireEvent.keyDown(within(dialog).getByLabelText("Revenue, KCC 333C"), {
    key: "Enter",
  });
  expect(
    within(dialog).getByRole("button", { name: "Save day" }),
  ).toHaveFocus();
});

it("shows a row changed by someone else as saved now, and reads the day again", async () => {
  let reads = 0;
  const fetcher = serve(
    () => {
      reads++;
      return reads === 1 ? tuesday() : tuesday({ "vehicle-2": saved(1000, 4) });
    },
    () =>
      json(
        {
          title: "This day already has a different record.",
          detail:
            "KBZ 110A was changed after you opened the day. Check its current record and save again.",
          vehicleId: "vehicle-2",
          current: cell(TUESDAY, saved(1000, 4)),
        },
        409,
      ),
  );
  renderInApp(<RevenuePage />, { permissions: CLERK });
  const dialog = await openCapture();

  fireEvent.change(within(dialog).getByLabelText("Revenue, KDA 482M"), {
    target: { value: "1100" },
  });
  fireEvent.change(within(dialog).getByLabelText("Revenue, KBZ 110A"), {
    target: { value: "950" },
  });
  fireEvent.click(within(dialog).getByRole("button", { name: "Save day" }));

  expect(await within(dialog).findByRole("alert")).toHaveTextContent(
    "KBZ 110A was changed after you opened the day.",
  );
  await waitFor(() =>
    expect(within(dialog).getByLabelText("Revenue, KBZ 110A")).toHaveValue(
      "1000",
    ),
  );
  // What was typed for the other vehicles stays.
  expect(within(dialog).getByLabelText("Revenue, KDA 482M")).toHaveValue(
    "1100",
  );
  expect(calls(fetcher, "/revenue/day?")).toHaveLength(2);
});

it("steps a day at a time and never past the business date", async () => {
  const fetcher = serve((path) => ({
    ...tuesday(),
    date: new URL(path, "http://web").searchParams.get("date")!,
  }));
  renderInApp(<RevenuePage />, { permissions: CLERK });
  const dialog = await openCapture();

  fireEvent.click(within(dialog).getByRole("button", { name: "Next day" }));
  expect(within(dialog).getByText("Wed 30 Sep 2026")).toBeInTheDocument();
  await waitFor(() =>
    expect(calls(fetcher, "/revenue/day?").map((call) => call.path)).toContain(
      `/api/setup/revenue/day?date=${TODAY}`,
    ),
  );
  expect(
    within(dialog).getByRole("button", { name: "Next day" }),
  ).toBeDisabled();
  fireEvent.click(within(dialog).getByRole("button", { name: "Previous day" }));
  fireEvent.click(within(dialog).getByRole("button", { name: "Previous day" }));
  expect(within(dialog).getByText("Mon 28 Sep 2026")).toBeInTheDocument();
});

it("offers no reasons without the no-earnings permission, but still shows a saved one", async () => {
  serve(() =>
    tuesday({
      "vehicle-2": {
        status: "reason",
        reason: "Garage",
        amount: null,
        version: 2,
      },
    }),
  );
  renderInApp(<RevenuePage />, {
    permissions: ["revenue.view", "revenue.capture"],
  });
  const dialog = await openCapture();

  expect(within(dialog).queryByLabelText(/No revenue reason,/)).toBeNull();
  expect(
    within(within(dialog).getAllByRole("row")[2]).getAllByText("Garage"),
  ).toHaveLength(2);
});
