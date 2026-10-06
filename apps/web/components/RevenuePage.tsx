"use client";

import { Fragment, useEffect, useMemo, useRef, useState } from "react";

import { percentText, type Formatter } from "@xcode/shared/format";
import {
  parseRevenueAmount,
  REVENUE_NOTE_LIMIT,
  REVENUE_REASONS,
  type RevenueCell,
  type RevenueReason,
  type RevenueVehicle,
  type RevenueWeek,
  type SaveRevenue,
} from "@xcode/shared/revenue";

import { ApiError, apiRequest, useResource } from "../lib/data";
import { useFormats } from "../lib/formats";
import { useSession } from "../lib/session-context";
import { dayOfMonth, difference, figure, longDate, shiftDate, weekday } from "./revenueFormat";
import {
  Banner,
  Button,
  ChevronIcon,
  CurrencyInput,
  Dialog,
  Field,
  FormActions,
  Hint,
  IconButton,
  ListSkeleton,
  LoadingRegion,
  Note,
  PageHeader,
  SelectInput,
  Skeleton,
  Spacer,
  Stat,
  StatGrid,
  TableRowsSkeleton,
  TextInput,
  Toolbar,
  cn,
} from "./ui";

const isReason = (value: string | null): value is RevenueReason =>
  REVENUE_REASONS.includes(value as RevenueReason);

// The day being captured and the day the person set out to fill (an earlier gap opens first), plus the vehicles
// already done for that day in this run, so a grid that has not reloaded yet never sends capture back to them.
type Capture = { vehicleId: string; date: string; target: string; info: string; done: string[] };

// One vehicle's week: a capture day outside the grid's week, or a fresh look at the vehicle after a save.
const vehicleWeekPath = (vehicleId: string, date: string) => `setup/revenue?weekStart=${date}&vehicleId=${vehicleId}`;

const activeOn = (vehicle: RevenueVehicle, date: string) =>
  vehicle.joinedOn <= date && (vehicle.leftOn === null || date < vehicle.leftOn);

// Whether the vehicle still needs a record for the day. Inside the loaded week the cell says so; for another week,
// captures run in date order, so any day on or after the vehicle's earliest gap is still missing too.
function missingOn(vehicle: RevenueVehicle, date: string) {
  const cell = vehicle.days.find((day) => day.date === date);
  if (cell) return cell.status === "missing";
  return activeOn(vehicle, date) && vehicle.earliestMissing !== null && vehicle.earliestMissing <= date;
}

// Where capture opens for a day: a missing day waits for the vehicle's earliest gap, so that gap opens first.
function openAt(formats: Formatter, vehicle: RevenueVehicle, day: string, done: string[] = []): Capture {
  const first = vehicle.earliestMissing;
  if (first && first < day && missingOn(vehicle, day))
    return { vehicleId: vehicle.id, date: first, target: day, info: `Fill ${longDate(formats, first)} first.`, done };
  return { vehicleId: vehicle.id, date: day, target: day, info: "", done };
}

// The next vehicle after this one (in grid order, wrapping round) that still has no record for the day.
function nextMissing(vehicles: RevenueVehicle[], after: string, day: string, done: string[]) {
  const index = vehicles.findIndex((vehicle) => vehicle.id === after);
  return [...vehicles.slice(index + 1), ...vehicles.slice(0, Math.max(index, 0))].find(
    (vehicle) => !done.includes(vehicle.id) && missingOn(vehicle, day),
  );
}

// The first day a vehicle can be captured: its earliest gap, or today while today has no record.
function firstGap(vehicle: RevenueVehicle, today: string) {
  return vehicle.earliestMissing ?? (vehicle.days.find((day) => day.date === today)?.status === "missing" ? today : null);
}

// A later missing day stays shut on the server until the earliest gap is filled; the grid still offers it and
// opens the gap instead.
function opens(vehicle: RevenueVehicle, cell: RevenueCell, canCapture: boolean) {
  return (
    cell.canEdit ||
    (cell.status === "missing" && canCapture && vehicle.earliestMissing !== null && vehicle.earliestMissing < cell.date)
  );
}

function entryLabel(formats: Formatter, entry: Pick<RevenueCell, "amount" | "reason" | "note">) {
  if (entry.amount !== null) return formats.kes(entry.amount);
  if (entry.reason) return entry.note ? `${entry.reason}: ${entry.note}` : entry.reason;
  return "No record";
}

function cellState(formats: Formatter, cell: RevenueCell) {
  const state = cell.status === "missing" ? "Missing" : entryLabel(formats, cell);
  return cell.editedAfterCapture ? `${state}, edited after capture` : state;
}

const HEAD = "border-b border-card-line bg-paper px-2 py-2.5 text-xs font-semibold whitespace-nowrap text-grey";
const CELL = "border-b border-divider px-2 py-1.5 text-[15px] tabular-nums";
// Below 720px the seven day columns give way to each vehicle's week detail, which lists the same days.
const DAY_COLUMN = "max-[720px]:hidden";
const PILL = "rounded-full bg-divider px-2 py-0.5 text-xs font-bold whitespace-nowrap text-navy";
const MINI_HEAD = "border-b border-card-line px-2 py-2 text-left text-xs font-semibold text-grey";
const MINI = "border-b border-card-line/70 px-2 py-1.5 text-sm tabular-nums";

export function RevenuePage() {
  const { can } = useSession();
  const formats = useFormats();
  const canView = can("revenue.view");
  const canCapture = can("revenue.capture");
  const [weekStart, setWeekStart] = useState("");
  const [companyId, setCompanyId] = useState("");
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(() => new Set());
  const [capture, setCapture] = useState<Capture | null>(null);
  const opener = useRef<HTMLElement | null>(null);
  const gridRef = useRef<HTMLDivElement>(null);

  const query = useMemo(() => {
    const params = new URLSearchParams();
    if (weekStart) params.set("weekStart", weekStart);
    if (companyId) params.set("companyId", companyId);
    const encoded = params.toString();
    return `setup/revenue${encoded ? `?${encoded}` : ""}`;
  }, [companyId, weekStart]);
  // One request per week and company; every cell comes from it.
  const week = useResource<RevenueWeek>(canView ? query : null);
  const data = week.data;
  // The toolbar keeps the last week shown while the next one loads, so its controls (and focus) stay in place.
  const [shown, setShown] = useState<RevenueWeek>();
  if (data && data !== shown) setShown(data);
  // A company picked in another week that this week does not list (an archived one, say) would leave an empty grid,
  // and with one company or none no control to leave it: the filter goes once the week has loaded.
  if (data && companyId && !data.companies.some((company) => company.id === companyId)) setCompanyId("");
  // After a save the grid reloads in place. Until the new week arrives its gaps are out of date, so Capture revenue
  // waits for it rather than opening a day that was just saved.
  const [stale, setStale] = useState<RevenueWeek | null>(null);
  if (stale && (data !== stale || week.error)) setStale(null);

  const today = shown?.businessDate ?? "";
  const start = weekStart || shown?.weekStart || "";
  const days = useMemo(() => (data ? Array.from({ length: 7 }, (_, index) => shiftDate(data.weekStart, index)) : []), [data]);
  const dayTotals = useMemo(
    () =>
      days.map((_, index) =>
        (data?.vehicles ?? []).reduce((sum, vehicle) => sum + (vehicle.days[index]?.status === "amount" ? (vehicle.days[index].amount ?? 0) : 0), 0),
      ),
    [data, days],
  );
  // The grid's primary action starts at the earliest missing vehicle and day.
  const first =
    data && canCapture
      ? data.vehicles.reduce<{ vehicle: RevenueVehicle; date: string } | null>((best, vehicle) => {
          const date = firstGap(vehicle, today);
          return date && (!best || date < best.date) ? { vehicle, date } : best;
        }, null)
      : null;

  const gridVehicle = capture ? data?.vehicles.find((vehicle) => vehicle.id === capture.vehicleId) : undefined;
  const gridCell = capture ? gridVehicle?.days.find((day) => day.date === capture.date) : undefined;
  const elsewhere = useResource<RevenueWeek>(capture && data && !gridCell ? vehicleWeekPath(capture.vehicleId, capture.date) : null);
  const otherVehicle = elsewhere.data?.vehicles[0];
  const otherCell = capture ? otherVehicle?.days.find((day) => day.date === capture.date) : undefined;
  const vehicle = gridCell ? gridVehicle : otherCell ? otherVehicle : undefined;
  const cell = gridCell ?? otherCell;

  // Focus goes back to the day that opened capture, or to the grid when that day is no longer a button.
  const dialogOpen = capture !== null;
  useEffect(() => {
    if (dialogOpen || !opener.current) return;
    const element = opener.current;
    opener.current = null;
    (element.isConnected ? element : gridRef.current)?.focus();
  }, [dialogOpen]);

  function open(next: Capture, from: HTMLElement) {
    if (!capture) opener.current = from;
    setCapture(next);
  }

  function toggle(id: string) {
    setExpanded((current) => {
      const next = new Set(current);
      if (!next.delete(id)) next.add(id);
      return next;
    });
  }

  // After a save: the same vehicle again while the day it set out to fill is still open (its next gap first), then
  // the next vehicle still missing that day, then done. The grid reloads alongside.
  async function advance(saved: Capture) {
    setStale(data ?? null);
    week.reload();
    if (saved.date < saved.target) {
      const fresh = await apiRequest<RevenueWeek>(vehicleWeekPath(saved.vehicleId, saved.target)).catch(() => undefined);
      const same = fresh?.vehicles[0];
      if (same && missingOn(same, saved.target)) return setCapture(openAt(formats, same, saved.target, saved.done));
    }
    const done = [...saved.done, saved.vehicleId];
    const next = canCapture && data ? nextMissing(data.vehicles, saved.vehicleId, saved.target, done) : undefined;
    setCapture(next ? openAt(formats, next, saved.target, done) : null);
  }

  if (!canView) {
    return (
      <section>
        <PageHeader title="Revenue" description="Your access does not include revenue records." />
      </section>
    );
  }

  return (
    <section>
      <PageHeader title="Revenue" />
      <Toolbar>
        <div className="flex items-center gap-1">
          <IconButton aria-label="Previous week" disabled={!start} onClick={() => setWeekStart(shiftDate(start, -7))}>
            <ChevronIcon size={20} className="rotate-90" />
          </IconButton>
          <strong aria-live="polite" className="min-w-44 text-center text-[15px] max-[600px]:min-w-0">
            {start ? formats.formatDateRange(start, shiftDate(start, 6)) : <Skeleton className="mx-auto w-36" />}
          </strong>
          <IconButton
            aria-label="Next week"
            disabled={!shown || start >= shown.currentWeekStart}
            onClick={() => setWeekStart(shiftDate(start, 7))}
          >
            <ChevronIcon size={20} className="-rotate-90" />
          </IconButton>
        </div>
        {/* While a filter is set, All companies stays one choice away even when this week lists a single company. */}
        {shown && (shown.companies.length > 1 || companyId) && (
          <SelectInput aria-label="Company" density="compact" inline value={companyId} onChange={(event) => setCompanyId(event.target.value)}>
            <option value="">All companies</option>
            {shown.companies.map((company) => (
              <option key={company.id} value={company.id}>
                {company.name}
              </option>
            ))}
          </SelectInput>
        )}
        <Spacer />
        {first && (
          <Button
            disabled={Boolean(stale)}
            aria-busy={stale ? true : undefined}
            onClick={(event) => open(openAt(formats, first.vehicle, first.date), event.currentTarget)}
          >
            Capture revenue
          </Button>
        )}
        <div className="flex flex-col items-end leading-[1.3]">
          <small className="text-xs text-grey">Week to date</small>
          {data ? (
            <>
              <strong className="text-xl tabular-nums">{formats.kes(data.totalAmount)}</strong>
              <small className="text-xs text-grey">
                {`of ${formats.kes(data.totalExpected)} expected${data.percent === null ? "" : `, ${percentText(data.percent)}`}`}
              </small>
            </>
          ) : (
            <Skeleton className="mt-1 h-6 w-24" />
          )}
        </div>
      </Toolbar>

      {week.error && <Banner className="mt-4">{week.error}</Banner>}

      {!data ? (
        week.loading && (
          <LoadingRegion label="Loading revenue" className="mt-4 overflow-hidden rounded-[14px] border border-card-line bg-surface">
            <table className="w-full border-collapse">
              <tbody>
                <TableRowsSkeleton columns={4} />
              </tbody>
            </table>
          </LoadingRegion>
        )
      ) : (
        // relative: the card is the containing block for the screen-reader-only labels (absolutely positioned) in the
        // grid, so they scroll with it instead of widening the page at tablet widths.
        <div ref={gridRef} tabIndex={-1} className="relative mt-4 overflow-x-auto rounded-[14px] border border-card-line bg-surface">
          <table className="w-full border-collapse min-[721px]:min-w-225">
            <caption className="sr-only">Revenue by vehicle and day, {formats.formatDateRange(data.weekStart, data.weekThrough)}</caption>
            <thead>
              <tr>
                <th scope="col" className={cn(HEAD, "sticky left-0 z-1 min-w-35 text-left")}>
                  Vehicle
                </th>
                {days.map((date) => (
                  <th
                    key={date}
                    scope="col"
                    aria-current={date === today ? "date" : undefined}
                    className={cn(HEAD, DAY_COLUMN, "text-right", date === today && "shadow-[inset_0_-3px_0_var(--color-blue)]")}
                  >
                    {weekday(date)}{" "}
                    <span className={cn("block text-base font-bold text-navy", date === today && "text-blue-dark")}>{dayOfMonth(date)}</span>
                    {date === today && <span className="sr-only">, today</span>}
                  </th>
                ))}
                <th scope="col" className={cn(HEAD, "text-right")}>
                  Week
                </th>
                <th scope="col" className={cn(HEAD, "text-right")}>
                  vs expected
                </th>
              </tr>
            </thead>
            <tbody>
              {data.vehicles.length === 0 ? (
                <tr>
                  <td colSpan={10} className="px-4 py-6 text-center text-grey">
                    No vehicles.
                  </td>
                </tr>
              ) : (
                data.vehicles.map((item) => {
                  const isOpen = expanded.has(item.id);
                  return (
                    <Fragment key={item.id}>
                      <tr>
                        <th scope="row" className={cn(CELL, "sticky left-0 z-1 min-w-35 bg-surface text-left font-normal")}>
                          <button
                            type="button"
                            aria-expanded={isOpen}
                            aria-controls={isOpen ? `revenue-detail-${item.id}` : undefined}
                            onClick={() => toggle(item.id)}
                            className="inline-flex min-h-8 items-center gap-1.5 text-left font-bold text-blue hover:underline"
                          >
                            <ChevronIcon className={cn("shrink-0 transition-transform motion-reduce:transition-none", !isOpen && "-rotate-90")} />
                            {item.registration}
                          </button>
                          <small className="block pl-5.5 text-xs text-grey">{item.companyName}</small>
                        </th>
                        {item.days.map((day) => (
                          <td key={day.date} className={cn(CELL, DAY_COLUMN, "text-right", day.date === today && "bg-blue-wash")}>
                            <DayCell
                              vehicle={item}
                              cell={day}
                              today={today}
                              canCapture={canCapture}
                              onOpen={(from) => open(openAt(formats, item, day.date), from)}
                            />
                          </td>
                        ))}
                        <td className={cn(CELL, "text-right")}>
                          <strong>{figure(formats, item.totalAmount)}</strong>
                        </td>
                        <td className={cn(CELL, "text-right")}>
                          {item.percent !== null && (
                            <span className={cn("font-bold", item.percent < 90 && "text-red")}>{percentText(item.percent)}</span>
                          )}
                        </td>
                      </tr>
                      {isOpen && (
                        <tr id={`revenue-detail-${item.id}`}>
                          <td colSpan={10} className="border-b border-divider bg-paper px-3 pt-1 pb-4">
                            <VehicleWeek
                              vehicle={item}
                              today={today}
                              canCapture={canCapture}
                              onOpen={(date, from) => open(openAt(formats, item, date), from)}
                            />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })
              )}
            </tbody>
            {data.vehicles.length > 0 && (
              <tfoot>
                <tr className="bg-paper font-bold">
                  <th scope="row" className="sticky left-0 z-1 bg-paper px-2 py-2 text-left">
                    All vehicles
                  </th>
                  {dayTotals.map((total, index) => (
                    <td key={days[index]} className={cn("px-2 py-2 text-right tabular-nums", DAY_COLUMN)}>
                      {total ? figure(formats, total) : ""}
                    </td>
                  ))}
                  <td className="px-2 py-2 text-right tabular-nums">{figure(formats, data.totalAmount)}</td>
                  <td className="px-2 py-2 text-right tabular-nums">{data.percent === null ? "" : percentText(data.percent)}</td>
                </tr>
              </tfoot>
            )}
          </table>
        </div>
      )}

      <Dialog open={dialogOpen} title={gridVehicle?.registration ?? otherVehicle?.registration ?? ""} onClose={() => setCapture(null)}>
        {capture &&
          (vehicle && cell ? (
            <CaptureForm
              key={`${capture.vehicleId}:${capture.date}`}
              vehicle={vehicle}
              cell={cell}
              info={capture.info}
              canChooseReason={can("revenue.no_earnings")}
              onCancel={() => setCapture(null)}
              onDone={() => advance(capture)}
              onOpenDay={(date) => setCapture({ ...capture, date, info: `Fill ${longDate(formats, date)} first.` })}
              reload={async () =>
                (await apiRequest<RevenueWeek>(vehicleWeekPath(capture.vehicleId, capture.date))).vehicles[0]?.days.find(
                  (day) => day.date === capture.date,
                )
              }
            />
          ) : elsewhere.error ? (
            <Banner>{elsewhere.error}</Banner>
          ) : elsewhere.data ? (
            <Banner>This day is outside the vehicle&apos;s time in the fleet.</Banner>
          ) : (
            <LoadingRegion label="Loading the day">
              <ListSkeleton rows={2} />
            </LoadingRegion>
          ))}
      </Dialog>
    </section>
  );
}

function DayCell({
  vehicle,
  cell,
  today,
  canCapture,
  onOpen,
}: {
  vehicle: RevenueVehicle;
  cell: RevenueCell;
  today: string;
  canCapture: boolean;
  onOpen: (from: HTMLElement) => void;
}) {
  const formats = useFormats();
  const clickable = opens(vehicle, cell, canCapture);
  const missing = cell.status === "missing";
  const now = cell.date === today;
  const content =
    cell.status === "amount" ? (
      figure(formats, cell.amount ?? 0)
    ) : cell.status === "reason" ? (
      <span className={PILL}>{cell.reason}</span>
    ) : missing ? (
      clickable ? "Enter" : "Missing"
    ) : (
      <span className="sr-only">{cell.status === "future" ? "Future day" : "Not counted"}</span>
    );
  const edited = cell.editedAfterCapture && <small className="text-[11px] font-normal text-grey">Edited</small>;
  const className = cn(
    "inline-flex min-h-9 min-w-17 flex-col items-end justify-center rounded-lg px-2 tabular-nums",
    missing && "items-center text-[13px] font-bold",
    missing && (now ? "text-blue-dark" : "text-red"),
  );
  if (!clickable)
    return (
      <span className={className}>
        {content}
        {edited}
      </span>
    );
  return (
    <button
      type="button"
      aria-label={`${vehicle.registration}, ${longDate(formats, cell.date)}: ${cellState(formats, cell)}`}
      onClick={(event) => onOpen(event.currentTarget)}
      className={cn(className, "hover:bg-hover", missing && "border border-dashed", missing && (now ? "border-blue" : "border-red"))}
    >
      {content}
      {edited}
    </button>
  );
}

// Expected, actual, difference and a bar for each day of one vehicle's week.
function VehicleWeek({
  vehicle,
  today,
  canCapture,
  onOpen,
}: {
  vehicle: RevenueVehicle;
  today: string;
  canCapture: boolean;
  onOpen: (date: string, from: HTMLElement) => void;
}) {
  const formats = useFormats();
  return (
    <table className="ml-6 w-[calc(100%-24px)] border-collapse max-[720px]:ml-0 max-[720px]:w-full">
      <caption className="sr-only">{vehicle.registration} week detail</caption>
      <thead>
        <tr>
          <th scope="col" className={MINI_HEAD}>
            Day
          </th>
          <th scope="col" className={cn(MINI_HEAD, "text-right")}>
            Expected
          </th>
          <th scope="col" className={cn(MINI_HEAD, "text-right")}>
            Revenue
          </th>
          <th scope="col" className={cn(MINI_HEAD, "text-right")}>
            Difference
          </th>
          <th scope="col" className={MINI_HEAD}>
            <span className="sr-only">Share of expected</span>
          </th>
        </tr>
      </thead>
      <tbody>
        {vehicle.days.map((cell) => {
          const day = (
            <th scope="row" className={cn(MINI, "text-left font-normal whitespace-nowrap")}>
              {`${weekday(cell.date)} ${dayOfMonth(cell.date)}`}
            </th>
          );
          if (cell.status === "none")
            return (
              <tr key={cell.date} className="text-grey">
                {day}
                <td colSpan={4} className={MINI}>
                  Not counted
                </td>
              </tr>
            );
          const expected = <td className={cn(MINI, "text-right")}>{figure(formats, cell.expected)}</td>;
          if (cell.status === "future")
            return (
              <tr key={cell.date} className="text-grey">
                {day}
                {expected}
                <td className={MINI} />
                <td className={MINI} />
                <td className={MINI} />
              </tr>
            );
          const missing = cell.status === "missing";
          const value = missing ? (
            <span className={cn("text-[13px] font-bold", cell.date === today ? "text-blue-dark" : "text-red")}>
              {cell.date < today ? "No record" : "Not yet"}
            </span>
          ) : cell.amount !== null ? (
            figure(formats, cell.amount)
          ) : (
            <span className={PILL}>{cell.reason}</span>
          );
          const revenue = opens(vehicle, cell, canCapture) ? (
            <button
              type="button"
              aria-label={`${vehicle.registration}, ${longDate(formats, cell.date)}: ${cellState(formats, cell)}`}
              onClick={(event) => onOpen(cell.date, event.currentTarget)}
              className="min-h-8 rounded-lg px-1.5 underline decoration-dotted underline-offset-4 hover:bg-hover"
            >
              {value}
            </button>
          ) : (
            value
          );
          if (missing)
            return (
              <tr key={cell.date}>
                {day}
                {expected}
                <td className={cn(MINI, "text-right")}>{revenue}</td>
                <td className={MINI} />
                <td className={MINI} />
              </tr>
            );
          const actual = cell.amount ?? 0;
          const share = cell.expected ? Math.round((actual / cell.expected) * 100) : 0;
          return (
            <tr key={cell.date}>
              {day}
              {expected}
              <td className={cn(MINI, "text-right")}>{revenue}</td>
              <td className={cn(MINI, "text-right")}>
                <Gap actual={actual} expected={cell.expected} />
              </td>
              <td className={MINI}>
                <div data-bar aria-hidden="true" className="h-1.5 w-30 overflow-hidden rounded-full bg-card-line max-[720px]:w-12">
                  <span className={cn("block h-full", share < 90 ? "bg-red" : "bg-blue")} style={{ width: `${Math.min(share, 100)}%` }} />
                </div>
              </td>
            </tr>
          );
        })}
        <tr className="font-bold">
          <th scope="row" className="px-2 py-1.5 text-left text-sm">
            To date
          </th>
          <td className="px-2 py-1.5 text-right text-sm tabular-nums">{figure(formats, vehicle.totalExpected)}</td>
          <td className="px-2 py-1.5 text-right text-sm tabular-nums">{figure(formats, vehicle.totalAmount)}</td>
          <td className="px-2 py-1.5 text-right text-sm tabular-nums">
            <Gap actual={vehicle.totalAmount} expected={vehicle.totalExpected} />
          </td>
          <td />
        </tr>
      </tbody>
    </table>
  );
}

function Gap({ actual, expected }: { actual: number; expected: number }) {
  const formats = useFormats();
  return <span className={cn(actual < expected && "text-red", actual > expected && "text-green")}>{difference(formats, actual, expected)}</span>;
}

function CaptureForm({
  vehicle,
  cell,
  info,
  canChooseReason,
  onCancel,
  onDone,
  onOpenDay,
  reload,
}: {
  vehicle: RevenueVehicle;
  cell: RevenueCell;
  info: string;
  canChooseReason: boolean;
  onCancel: () => void;
  // Called once the day is settled (saved, or the saved record kept): moves capture on.
  onDone: () => Promise<void>;
  onOpenDay: (date: string) => void;
  // Reads the day again, for a conflict that came without the saved record.
  reload: () => Promise<RevenueCell | undefined>;
}) {
  const formats = useFormats();
  // The record as it was when the day opened. A grid reload can bring a newer one, but saving over what the person
  // never saw must come back as a conflict, so its version is the one sent.
  const [opened] = useState(cell);
  const [amount, setAmount] = useState(opened.amount === null ? "" : String(opened.amount));
  const [reason, setReason] = useState<RevenueReason | "">(isReason(opened.reason) ? opened.reason : "");
  const [note, setNote] = useState(opened.note ?? "");
  const [error, setError] = useState("");
  const [earlier, setEarlier] = useState("");
  const [conflict, setConflict] = useState<{ message: string; current: RevenueCell } | null>(null);
  const [saving, setSaving] = useState(false);
  // Blocks a second save (Enter, or a quick second click) while one is on its way, before the disabled button renders.
  const busy = useRef(false);
  const amountRef = useRef<HTMLInputElement>(null);
  const noteRef = useRef<HTMLInputElement>(null);
  const opensOnNote = useRef(opened.reason === "Other");

  // After the dialog has opened (which focuses its first control), put the cursor where the entry goes.
  useEffect(() => {
    const timer = setTimeout(() => (opensOnNote.current ? noteRef : amountRef).current?.focus(), 0);
    return () => clearTimeout(timer);
  }, []);

  function entry(): SaveRevenue | string {
    const parsedAmount = parseRevenueAmount(amount);
    if (!parsedAmount.ok) return parsedAmount.error;
    if (parsedAmount.amount !== null)
      return { amount: parsedAmount.amount, reason: null, note: null };
    if (!canChooseReason) return "Enter the revenue.";
    if (!reason) return "Enter the revenue or pick a reason.";
    if (reason === "Other" && !note.trim()) return "Say what happened.";
    return { amount: null, reason, note: reason === "Other" ? note.trim() : null };
  }

  async function settle(work: () => Promise<void>) {
    if (busy.current) return;
    busy.current = true;
    setSaving(true);
    try {
      await work();
    } finally {
      busy.current = false;
      setSaving(false);
    }
  }

  // A correction sends the version it was read at; a first capture sends null.
  function save(version: number | null) {
    const next = entry();
    if (typeof next === "string") return setError(next);
    void settle(async () => {
      setError("");
      setEarlier("");
      try {
        await apiRequest(`setup/revenue/${vehicle.id}/${cell.date}`, { method: "PUT", body: JSON.stringify({ ...next, version }) });
      } catch (failure) {
        if (failure instanceof ApiError && failure.status === 409) {
          // Without the saved record (two first captures at once), read the day again before offering the choice.
          const current = (failure.body.current as RevenueCell | undefined) ?? (await reload().catch(() => undefined));
          if (current) setConflict({ message: failure.message, current });
          else setError(failure.message);
        } else if (failure instanceof ApiError && failure.status === 400 && typeof failure.body.earliestMissing === "string") {
          setEarlier(failure.body.earliestMissing);
        } else {
          setError(failure instanceof Error ? failure.message : "The revenue could not be saved.");
        }
        return;
      }
      await onDone();
    });
  }

  function choose(item: RevenueReason) {
    setReason((current) => (current === item ? "" : item));
    setAmount("");
    setError("");
  }

  const mine = entry();
  return (
    <form
      noValidate
      className="flex flex-col gap-3.5"
      onSubmit={(event) => {
        event.preventDefault();
        save(opened.version ?? null);
      }}
    >
      <p className="m-0 text-[13px] text-grey">{`${longDate(formats, cell.date)}. Expected ${formats.kes(cell.expected)}`}</p>
      {info && <Note>{info}</Note>}
      {!canChooseReason && !conflict && opened.reason && (
        <Hint>{`Recorded as ${entryLabel(formats, opened)}. Enter the revenue to replace it.`}</Hint>
      )}
      {conflict ? (
        <>
          <Note>{conflict.message}</Note>
          <StatGrid className="grid-cols-2">
            <Stat label="Saved value" value={entryLabel(formats, conflict.current)} />
            <Stat label="Yours" value={typeof mine === "string" ? "" : entryLabel(formats, mine)} />
          </StatGrid>
          {!conflict.current.canEdit && <Hint>Your access does not include changing the saved record for this day.</Hint>}
          <FormActions>
            {conflict.current.canEdit && (
              <Button tone="ok" disabled={saving} onClick={() => save(conflict.current.version ?? null)}>
                {saving ? "Saving…" : "Replace with mine"}
              </Button>
            )}
            <Button tone="outline" disabled={saving} onClick={() => void settle(onDone)}>
              Keep saved
            </Button>
          </FormActions>
        </>
      ) : (
        <>
          <Field
            id="revenue-amount"
            label="Revenue"
            hint="What the vehicle handed in for the day, after the crew settle fuel and their own pay."
          >
            <CurrencyInput
              ref={amountRef}
              value={amount}
              className="h-14! text-2xl!"
              onChange={(event) => {
                setAmount(event.target.value);
                setError("");
                if (event.target.value) setReason("");
              }}
            />
          </Field>
          {canChooseReason && (
            <>
              <p className="m-0 flex items-center gap-3 text-[13px] text-grey before:h-px before:flex-1 before:bg-card-line before:content-[''] after:h-px after:flex-1 after:bg-card-line after:content-['']">
                or no revenue
              </p>
              <div role="group" aria-label="No revenue reason" className="grid grid-cols-4 gap-2 max-[600px]:grid-cols-2">
                {REVENUE_REASONS.map((item) => (
                  <button
                    key={item}
                    type="button"
                    aria-pressed={reason === item}
                    onClick={() => choose(item)}
                    className="min-h-12 rounded-xl border border-line bg-surface text-[15px] font-semibold aria-pressed:border-2 aria-pressed:border-blue aria-pressed:bg-blue-soft aria-pressed:text-blue-dark"
                  >
                    {item}
                  </button>
                ))}
              </div>
              {reason === "Other" && (
                <Field id="revenue-note" label="What happened" hint={`Up to ${REVENUE_NOTE_LIMIT} characters.`}>
                  <TextInput
                    ref={noteRef}
                    autoFocus
                    maxLength={REVENUE_NOTE_LIMIT}
                    value={note}
                    onChange={(event) => {
                      setNote(event.target.value);
                      setError("");
                    }}
                  />
                </Field>
              )}
            </>
          )}
          {earlier && (
            <>
              <Note>{`Record ${longDate(formats, earlier)} first.`}</Note>
              <Button tone="outline" className="self-start" onClick={() => onOpenDay(earlier)}>
                {`Open ${longDate(formats, earlier)}`}
              </Button>
            </>
          )}
          {error && <Banner>{error}</Banner>}
          <FormActions>
            <Button tone="ok" type="submit" disabled={saving}>
              {saving ? "Saving…" : "Save"}
            </Button>
            <Button tone="quiet" disabled={saving} onClick={onCancel}>
              Cancel
            </Button>
          </FormActions>
        </>
      )}
    </form>
  );
}
