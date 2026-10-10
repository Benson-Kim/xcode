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
  cn,
  Dialog,
  ListSkeleton,
  LoadingRegion,
  Note,
  SearchSelect,
  TextInput,
} from "../ui";
import { dayTotal, type DayEntry } from "./fleetDay";
import { RegPlate } from "./RegPlate";
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
        <>
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
              <div className="tbl">
                <div className="scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Vehicle</th>
                        <th className={cn("r", LAST_WEEK)}>
                          Same day last week
                        </th>
                        <th className="r">
                          {`Revenue, ${formats.currencyCode()}`}
                        </th>
                        <th>No revenue reason</th>
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
                          onNote={(value) =>
                            capture.typeNote(vehicle.id, value)
                          }
                          onKeyDown={next(vehicle.id)}
                        />
                      ))}
                    </tbody>
                    <tfoot>
                      <tr>
                        <td>
                          {`${day.vehicles.length} vehicle${day.vehicles.length === 1 ? "" : "s"}`}
                        </td>
                        <td className={LAST_WEEK} />
                        <td className="r">
                          {formats.formatNumber(dayTotal(day, capture.typed))}
                        </td>
                        <td />
                      </tr>
                    </tfoot>
                  </table>
                </div>
              </div>
            </>
          )}
          {capture.problems.length > 0 && (
            <div className="ferr" role="alert">
              {capture.problems.map((problem) => (
                <span key={problem.vehicleId} className="block">
                  {problem.message}
                </span>
              ))}
            </div>
          )}
          {capture.error && (
            <div className="ferr" role="alert">
              {capture.error}
            </div>
          )}
        </>
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
    <div className="mstep">
      <div className="step day">
        <button
          type="button"
          aria-label="Previous day"
          onClick={() => onDate(shiftDate(date, -1))}
        >
          ‹
        </button>
        <span className="d" aria-live="polite">
          {formats.formatWeekdayDate(date)}
        </span>
        <button
          type="button"
          aria-label="Next day"
          disabled={date >= last}
          onClick={() => onDate(shiftDate(date, 1))}
        >
          ›
        </button>
      </div>
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
      <td>
        <RegPlate>{registration}</RegPlate>
      </td>
      <td className={cn("r muted", LAST_WEEK)}>
        {lastWeek === null
          ? ""
          : lastWeek.amount !== null
            ? formats.formatNumber(lastWeek.amount)
            : lastWeek.reason}
      </td>
      <td className={cn("r", cell.canEdit && "ed")}>
        {cell.canEdit ? (
          <input
            id={inputId}
            inputMode="decimal"
            autoComplete="off"
            aria-label={`Revenue, ${registration}`}
            aria-invalid={invalid || undefined}
            value={entry.amount}
            onChange={(event) => onAmount(event.target.value)}
            onKeyDown={onKeyDown}
            className={cn("cell wide", invalid && "err")}
          />
        ) : cell.amount === null ? (
          ""
        ) : (
          formats.formatNumber(cell.amount)
        )}
      </td>
      <td>
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
          <span className="muted">{saved}</span>
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
