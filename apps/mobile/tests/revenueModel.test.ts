import { createFormatter } from "@xcode/shared/format";

import type {
  QueuedCapture,
  RevenueCell,
  RevenueVehicle,
  RevenueWeek,
} from "../src/revenue/types";
import { dayBarFigures } from "../src/shell/revenue/DayBar";
import { keyOf, targetFor, type Waiting } from "../src/shell/revenue/model";

const formats = createFormatter({});

const cell = (date: string, over: Partial<RevenueCell> = {}): RevenueCell => ({
  date,
  status: "missing",
  expected: 1000,
  amount: null,
  reason: null,
  note: null,
  canEdit: true,
  editedAfterCapture: false,
  version: null,
  ...over,
});

const vehicle = (days: RevenueCell[]): RevenueVehicle => ({
  id: "v-1",
  companyId: "c-1",
  companyName: "North Star",
  registration: "KDA 482M",
  joinedOn: "2026-09-28",
  leftOn: null,
  earliestMissing: days.find((day) => day.status === "missing")?.date ?? null,
  days,
  totalAmount: 0,
  totalExpected: 0,
  percent: null,
});

const weekOf = (v: RevenueVehicle): RevenueWeek => ({
  weekStart: "2026-09-28",
  weekThrough: "2026-10-04",
  currentWeekStart: "2026-09-28",
  businessDate: "2026-09-29",
  companies: [],
  vehicles: [v],
  totalAmount: 0,
  totalExpected: 0,
  percent: null,
});

const queued = (over: Partial<QueuedCapture> = {}): QueuedCapture => ({
  vehicleId: "v-1",
  registration: "KDA 482M",
  date: "2026-09-29",
  amount: 700,
  reason: null,
  note: null,
  version: null,
  state: "pending",
  message: "",
  earliestMissing: null,
  current: null,
  queuedAt: 0,
  attempts: 0,
  lastAttemptAt: 0,
  ...over,
});

const waitingWith = (...entries: QueuedCapture[]): Waiting =>
  new Map(entries.map((entry) => [keyOf(entry.vehicleId, entry.date), entry]));

describe("targetFor", () => {
  const monday = cell("2026-09-28");
  const tuesday = cell("2026-09-29");
  const v = vehicle([
    monday,
    tuesday,
    cell("2026-09-30", { status: "future", canEdit: false }),
  ]);
  const week = weekOf(v);

  it.each([
    [
      "a day with a conflict opens nothing",
      waitingWith(queued({ state: "conflict" })),
      "2026-09-29",
      true,
      null,
    ],
    [
      "a waiting capture reopens as itself",
      waitingWith(queued()),
      "2026-09-29",
      true,
      { date: "2026-09-29", earlier: null, waiting: true },
    ],
    [
      "a missing day with an earlier one open sends to the earlier day",
      waitingWith(),
      "2026-09-29",
      true,
      { date: "2026-09-28", earlier: "2026-09-28", waiting: false },
    ],
    [
      "the earlier day, once handled, lets the day itself open",
      waitingWith(queued({ date: "2026-09-28" })),
      "2026-09-29",
      true,
      { date: "2026-09-29", earlier: null, waiting: false },
    ],
    [
      "a day that is not open opens nothing",
      waitingWith(),
      "2026-09-30",
      true,
      null,
    ],
    [
      "a day outside the week opens nothing",
      waitingWith(),
      "2026-10-20",
      true,
      null,
    ],
    [
      "without capture a missing day opens nothing",
      waitingWith(),
      "2026-09-29",
      false,
      null,
    ],
  ])("%s", (_name, waiting, date, canCapture, expected) => {
    const target = targetFor(v, date, week, waiting, canCapture);
    if (expected === null) return expect(target).toBeNull();
    expect(target).toMatchObject({
      date: expected.date,
      earlier: expected.earlier,
    });
    expect(Boolean(target?.waiting)).toBe(expected.waiting);
  });

  it("opens a recorded day to change it only when the API allows it", () => {
    const recorded = vehicle([
      cell("2026-09-28", { status: "amount", amount: 900, version: 3 }),
    ]);
    const open = targetFor(
      recorded,
      "2026-09-28",
      weekOf(recorded),
      waitingWith(),
      false,
    );
    expect(open).toMatchObject({ date: "2026-09-28", earlier: null });
    expect(open?.cell?.version).toBe(3);
    const locked = vehicle([
      cell("2026-09-28", { status: "amount", amount: 900, canEdit: false }),
    ]);
    expect(
      targetFor(locked, "2026-09-28", weekOf(locked), waitingWith(), true),
    ).toBeNull();
  });
});

describe("dayBarFigures", () => {
  const today = "2026-09-29";

  it.each([
    [
      "a future day",
      cell("2026-09-30", { status: "future", canEdit: false }),
      undefined,
      {
        compared: false,
        shown: "Not yet",
        tone: "muted",
        difference: "",
        share: 0,
      },
    ],
    [
      "today before capture",
      cell(today),
      undefined,
      {
        compared: false,
        shown: "Not yet",
        tone: "muted",
        difference: "",
        share: 0,
      },
    ],
    [
      "an earlier day nobody captured",
      cell("2026-09-28"),
      undefined,
      { compared: true, shown: "No record", below: true, share: 0 },
    ],
    [
      "a recorded amount short of the target",
      cell(today, { status: "amount", amount: 600 }),
      undefined,
      { compared: true, shown: "KES 600", below: true, share: 0.6 },
    ],
    [
      "a recorded amount over the target",
      cell(today, { status: "amount", amount: 1200 }),
      undefined,
      { compared: true, shown: "KES 1,200", below: false, share: 1 },
    ],
    [
      "a recorded reason",
      cell(today, { status: "reason", reason: "Garage" }),
      undefined,
      { compared: true, shown: "Garage", below: true, share: 0 },
    ],
    [
      "a capture waiting on the phone",
      cell(today),
      queued({ amount: 700 }),
      {
        compared: true,
        shown: "KES 700, not sent yet",
        tone: "normal",
        below: true,
        share: 0.7,
      },
    ],
  ])("%s", (_name, day, waiting, expected) => {
    expect(dayBarFigures(formats, day, waiting, today)).toMatchObject(expected);
  });

  it("states the difference only where days are compared", () => {
    expect(
      dayBarFigures(
        formats,
        cell(today, { status: "amount", amount: 1200 }),
        undefined,
        today,
      ).difference,
    ).toBe("KES 200 above");
    expect(
      dayBarFigures(
        formats,
        cell(today, { status: "amount", amount: 600 }),
        undefined,
        today,
      ).difference,
    ).toBe("KES 400 below");
  });
});
