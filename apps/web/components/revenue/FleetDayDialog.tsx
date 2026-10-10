"use client";

import {
  useEffect,
  useId,
  useRef,
  type KeyboardEvent,
  type RefObject,
} from "react";

import { shiftDate } from "@xcode/shared/dates";
import {
  REVENUE_NOTE_LIMIT,
  REVENUE_REASONS,
  type RevenueDayVehicle,
  type RevenueReason,
} from "@xcode/shared/revenue";

import { useFormats } from "../../lib/formats";
import {
  Banner,
  Button,
  ChevronIcon,
  cn,
  Dialog,
  IconButton,
  ListSkeleton,
  LoadingRegion,
  Note,
  SearchSelect,
  TextInput,
} from "../ui";
import { dayTotal, type DayEntry } from "./fleetDay";
import { RegPlate } from "./RegPlate";
import { CELL, HEAD } from "./styles";
import { useFleetDay } from "./useFleetDay";

const REASON_OPTIONS = REVENUE_REASONS.map((reason) => ({
  value: reason,
  label: reason,
}));
// The comparison column gives way first on a phone.
const LAST_WEEK = "max-[600px]:hidden";

// Capture revenue (design v2.28, openCapture): one day for every vehicle, the same day last week beside each, and
// one save for the rows that changed.
export function FleetDayDialog({
  date,
  today,
  companyId,
  companyName,
  canChooseReason,
  onDate,
  onClose,
  onSaved,
}: {
  date: string | null;
  today: string;
  companyId: string;
  companyName: string;
  canChooseReason: boolean;
  onDate: (date: string) => void;
  onClose: () => void;
  onSaved: (date: string, count: number) => void;
}) {
  const formats = useFormats();
  const capture = useFleetDay({ date, companyId, canChooseReason, onSaved });
  const prefix = useId();
  const inputId = (vehicleId: string) => `${prefix}-${vehicleId}`;
  const saveRef = useRef<HTMLButtonElement>(null);
  const { day } = capture;
  useFirstEmptyFocus(day?.date ?? null, day?.vehicles, prefix);
  const editable = day?.vehicles.filter((vehicle) => vehicle.day.canEdit);
  const invalid = new Set(capture.problems.map((problem) => problem.vehicleId));

  // Enter moves down the revenue column, then to Save day.
  const next = (vehicleId: string) => (event: KeyboardEvent) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    const index = editable?.findIndex((vehicle) => vehicle.id === vehicleId);
    const below = index === undefined ? undefined : editable?.[index + 1];
    if (below) document.getElementById(inputId(below.id))?.focus();
    else saveRef.current?.focus();
  };

  return (
    <Dialog
      open={date !== null}
      size="md"
      title="Capture revenue"
      subtitle={companyName || undefined}
      onClose={onClose}
      footer={
        date !== null && (
          <DayActions
            saveRef={saveRef}
            disabled={!day || capture.saving}
            saving={capture.saving}
            onCancel={onClose}
            onSave={capture.save}
          />
        )
      }
    >
      {date !== null && (
        <div className="flex flex-col gap-3.5">
          <DayStepper
            date={date}
            last={day?.businessDate ?? today}
            onDate={onDate}
          />
          {capture.loadError ? (
            <Banner>{capture.loadError}</Banner>
          ) : !day ? (
            <LoadingRegion label="Loading the day">
              <ListSkeleton rows={4} />
            </LoadingRegion>
          ) : day.vehicles.length === 0 ? (
            <Note tone="info">No vehicle was in the fleet on this day.</Note>
          ) : (
            <>
              {day.truncated && (
                <Note tone="info">
                  {`Showing the first ${day.vehicles.length} vehicles. Choose a company to capture the rest.`}
                </Note>
              )}
              <div className="overflow-x-auto rounded-2xl border border-line">
                <table className="w-full border-collapse">
                  <thead>
                    <tr>
                      <th className={cn(HEAD, "text-left")}>Vehicle</th>
                      <th className={cn(HEAD, "text-right", LAST_WEEK)}>
                        Same day last week
                      </th>
                      <th className={cn(HEAD, "text-right")}>
                        {`Revenue, ${formats.currencyCode()}`}
                      </th>
                      <th className={cn(HEAD, "text-left")}>
                        No revenue reason
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {day.vehicles.map((vehicle) => (
                      <DayRow
                        key={vehicle.id}
                        vehicle={vehicle}
                        entry={capture.entry(vehicle.id)}
                        invalid={invalid.has(vehicle.id)}
                        canChooseReason={canChooseReason}
                        inputId={inputId(vehicle.id)}
                        onAmount={(value) =>
                          capture.typeAmount(vehicle.id, value)
                        }
                        onReason={(value) =>
                          capture.chooseReason(vehicle.id, value)
                        }
                        onNote={(value) => capture.typeNote(vehicle.id, value)}
                        onKeyDown={next(vehicle.id)}
                      />
                    ))}
                  </tbody>
                  <tfoot>
                    <tr className="bg-paper-2 font-bold text-ink">
                      <td className={CELL}>
                        {`${day.vehicles.length} vehicle${day.vehicles.length === 1 ? "" : "s"}`}
                      </td>
                      <td className={cn(CELL, LAST_WEEK)} />
                      <td className={cn(CELL, "text-right")}>
                        {formats.formatNumber(dayTotal(day, capture.typed))}
                      </td>
                      <td className={CELL} />
                    </tr>
                  </tfoot>
                </table>
              </div>
            </>
          )}
          {capture.problems.length > 0 && (
            <Banner>
              {capture.problems.map((problem) => (
                <span key={problem.vehicleId} className="block">
                  {problem.message}
                </span>
              ))}
            </Banner>
          )}
          {capture.error && <Banner>{capture.error}</Banner>}
        </div>
      )}
    </Dialog>
  );
}

function DayActions({
  saveRef,
  disabled,
  saving,
  onCancel,
  onSave,
}: {
  saveRef: RefObject<HTMLButtonElement | null>;
  disabled: boolean;
  saving: boolean;
  onCancel: () => void;
  onSave: () => void;
}) {
  return (
    <>
      <Button tone="outline" onClick={onCancel}>
        Cancel
      </Button>
      <Button
        ref={saveRef}
        tone="ok"
        disabled={disabled}
        aria-busy={saving || undefined}
        onClick={onSave}
      >
        Save day
      </Button>
    </>
  );
}

// The day being captured, a day at a time, up to the business date.
function DayStepper({
  date,
  last,
  onDate,
}: {
  date: string;
  last: string;
  onDate: (date: string) => void;
}) {
  const formats = useFormats();
  return (
    <div className="flex items-center gap-1">
      <IconButton
        aria-label="Previous day"
        onClick={() => onDate(shiftDate(date, -1))}
      >
        <ChevronIcon size={20} className="rotate-90" />
      </IconButton>
      <strong aria-live="polite" className="min-w-44 text-center text-[15px]">
        {formats.formatWeekdayDate(date)}
      </strong>
      <IconButton
        aria-label="Next day"
        disabled={date >= last}
        onClick={() => onDate(shiftDate(date, 1))}
      >
        <ChevronIcon size={20} className="-rotate-90" />
      </IconButton>
    </div>
  );
}

function DayRow({
  vehicle,
  entry,
  invalid,
  canChooseReason,
  inputId,
  onAmount,
  onReason,
  onNote,
  onKeyDown,
}: {
  vehicle: RevenueDayVehicle;
  entry: DayEntry;
  invalid: boolean;
  canChooseReason: boolean;
  inputId: string;
  onAmount: (value: string) => void;
  onReason: (value: RevenueReason | "") => void;
  onNote: (value: string) => void;
  onKeyDown: (event: KeyboardEvent) => void;
}) {
  const formats = useFormats();
  const { day: cell, lastWeek, registration } = vehicle;
  const saved =
    cell.reason === null
      ? ""
      : cell.note
        ? `${cell.reason}: ${cell.note}`
        : cell.reason;
  return (
    <tr>
      <td className={cn(CELL, "whitespace-nowrap")}>
        <RegPlate>{registration}</RegPlate>
      </td>
      <td className={cn(CELL, "text-right text-slate", LAST_WEEK)}>
        {lastWeek === null
          ? ""
          : lastWeek.amount !== null
            ? formats.formatNumber(lastWeek.amount)
            : lastWeek.reason}
      </td>
      <td className={cn(CELL, "text-right")}>
        {cell.canEdit ? (
          <div className="ml-auto w-28">
            <TextInput
              id={inputId}
              density="compact"
              inputMode="decimal"
              autoComplete="off"
              aria-label={`Revenue, ${registration}`}
              aria-invalid={invalid || undefined}
              value={entry.amount}
              onChange={(event) => onAmount(event.target.value)}
              onKeyDown={onKeyDown}
              className="text-right tabular-nums"
            />
          </div>
        ) : cell.amount === null ? (
          ""
        ) : (
          formats.formatNumber(cell.amount)
        )}
      </td>
      <td className={CELL}>
        {cell.canEdit && canChooseReason ? (
          <div className="flex min-w-36 flex-col gap-1.5">
            <SearchSelect
              density="compact"
              options={REASON_OPTIONS}
              value={entry.reason}
              placeholder="Choose reason"
              disabled={Boolean(entry.amount.trim())}
              aria-label={`No revenue reason, ${registration}`}
              onChange={(value) => onReason(value as RevenueReason | "")}
            />
            {entry.reason === "Other" && (
              <TextInput
                density="compact"
                maxLength={REVENUE_NOTE_LIMIT}
                placeholder="What happened"
                aria-label={`What happened, ${registration}`}
                value={entry.note}
                onChange={(event) => onNote(event.target.value)}
              />
            )}
          </div>
        ) : (
          <span className="text-slate">{saved}</span>
        )}
      </td>
    </tr>
  );
}

// Once a day has loaded, the cursor goes to the first row with nothing recorded, or the first row that can change.
function useFirstEmptyFocus(
  date: string | null,
  vehicles: RevenueDayVehicle[] | undefined,
  prefix: string,
) {
  const focused = useRef<string | null>(null);
  useEffect(() => {
    if (date === null) {
      focused.current = null;
      return;
    }
    if (!vehicles || focused.current === date) return;
    focused.current = date;
    const target =
      vehicles.find(
        (vehicle) => vehicle.day.canEdit && vehicle.day.status === "missing",
      ) ?? vehicles.find((vehicle) => vehicle.day.canEdit);
    if (!target) return;
    const timer = setTimeout(
      () => document.getElementById(`${prefix}-${target.id}`)?.focus(),
      0,
    );
    return () => clearTimeout(timer);
  }, [date, vehicles, prefix]);
}
