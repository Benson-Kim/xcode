import type { Formatter } from "@xcode/shared/format";

import type { SaveRecurringRequest } from "../../lib/endpoints/recurring";
import {
  RECURRING_FREQUENCY,
  recurringNextPosting,
} from "../recurringPresentation";
import type { RecurringItem } from "../setup/shared";

// The saving and scheduled expense pop up (v2.30): what, how much per vehicle, when it runs, which vehicles, and
// for a saving the revenue rule and the opening balance. No start or end date: a schedule runs from its next run.
export type RecurringFields = {
  kind: number;
  expenseItemId: string;
  name: string;
  amount: string;
  frequency: number;
  weekday: string;
  monthDay: string;
  month: string;
  allVehicles: boolean;
  vehicleIds: string[];
  conditionOn: boolean;
  conditionMin: string;
  conditionDays: string;
  openingOn: boolean;
  openingDate: string;
  openingAmounts: Record<string, string>;
};

export const DEFAULT_WINDOW: Record<number, number> = {
  [RECURRING_FREQUENCY.daily]: 1,
  [RECURRING_FREQUENCY.weekly]: 7,
  [RECURRING_FREQUENCY.monthly]: 30,
  [RECURRING_FREQUENCY.yearly]: 30,
};

const plain = (value: number) =>
  Number.isInteger(value) ? String(value) : value.toFixed(2);

export function initialFields(
  item: RecurringItem | undefined,
  kind: number,
  fullScope: boolean,
  fleet: string[],
): RecurringFields {
  const shares = item?.allocations ?? [];
  const perVehicle = shares.length
    ? shares.every((share) => share.amount === shares[0].amount)
      ? shares[0].amount
      : shares.reduce((sum, share) => sum + share.amount, 0) / shares.length
    : 0;
  const monthly =
    item?.frequency === RECURRING_FREQUENCY.monthly ||
    item?.frequency === RECURRING_FREQUENCY.yearly;
  const covered = new Set(shares.map((share) => share.vehicleId));
  const coversFleet = fleet.length > 0 && fleet.every((id) => covered.has(id));
  return {
    kind: item?.kind ?? kind,
    expenseItemId: item?.expenseItemId ?? "",
    name: item?.kind === 2 ? item.name : "",
    amount: perVehicle ? plain(perVehicle) : "",
    frequency: item?.frequency || RECURRING_FREQUENCY.monthly,
    weekday: String(
      item?.frequency === RECURRING_FREQUENCY.weekly ? (item.day ?? 6) : 6,
    ),
    monthDay:
      item && monthly ? (item.lastDay ? "last" : String(item.day ?? 1)) : "1",
    month: String(item?.month ?? 1),
    allVehicles: item ? coversFleet && fullScope : fullScope,
    vehicleIds: shares.map((share) => share.vehicleId),
    conditionOn: Boolean(item?.condition),
    conditionMin: item?.condition ? plain(item.condition.min) : "",
    conditionDays: String(
      item?.condition?.days ??
        DEFAULT_WINDOW[item?.frequency || RECURRING_FREQUENCY.monthly],
    ),
    openingOn: Boolean(item?.opening),
    openingDate: item?.opening?.date ?? "",
    openingAmounts: {},
  };
}

const money = (value: string) => Number(value.replace(/[,\s]/g, "")) || 0;

// The vehicles the item runs on: every vehicle of the fleet, or the ticked ones.
export function chosenVehicles(fields: RecurringFields, fleet: string[]) {
  return fields.allVehicles ? fleet : fields.vehicleIds;
}

export function openingAmounts(fields: RecurringFields, vehicles: string[]) {
  const amounts: { vehicleId: string; amount: number }[] = [];
  for (const vehicleId of vehicles) {
    const amount = money(fields.openingAmounts[vehicleId] ?? "");
    if (amount) amounts.push({ vehicleId, amount });
  }
  return amounts;
}

// The first problem on screen, as the prototype says it, or null.
export function validateFields(
  fields: RecurringFields,
  vehicles: string[],
  today: string,
): string | null {
  const expense = fields.kind === 1;
  if (expense ? !fields.expenseItemId : !fields.name.trim())
    return expense ? "Choose the item." : "Enter the name.";
  if (money(fields.amount) <= 0) return "Enter the amount.";
  if (!expense && fields.conditionOn && money(fields.conditionMin) <= 0)
    return "Enter the revenue target.";
  if (!vehicles.length) return "Pick at least one vehicle.";
  if (!expense && fields.openingOn) {
    if (!fields.openingDate) return "Enter the opening balance date.";
    if (today && fields.openingDate > today)
      return "The opening balance date is after today.";
  }
  return null;
}

export function schedulePart(fields: RecurringFields) {
  const { frequency, monthDay } = fields;
  const monthly =
    frequency === RECURRING_FREQUENCY.monthly ||
    frequency === RECURRING_FREQUENCY.yearly;
  const lastDay = monthly && monthDay === "last";
  return {
    frequency,
    day:
      frequency === RECURRING_FREQUENCY.weekly
        ? Number(fields.weekday)
        : monthly && !lastDay
          ? Number(monthDay)
          : null,
    lastDay,
    month:
      frequency === RECURRING_FREQUENCY.yearly ? Number(fields.month) : null,
  };
}

export function buildRequest(
  fields: RecurringFields,
  item: RecurringItem | undefined,
  vehicles: string[],
  today: string,
  itemName: string,
): SaveRecurringRequest {
  const per = money(fields.amount);
  const saving = fields.kind === 2;
  const opening = openingAmounts(fields, vehicles);
  return {
    name: saving ? fields.name.trim() : itemName,
    kind: fields.kind,
    amount: Math.round(per * vehicles.length * 100) / 100,
    ...schedulePart(fields),
    // A schedule runs from its next run date: a new one starts today, an existing one keeps its start.
    start: item?.start ?? today,
    end: null,
    allocations: vehicles.map((vehicleId) => ({ vehicleId, amount: per })),
    expenseItemId: saving ? null : fields.expenseItemId,
    note: null,
    month: schedulePart(fields).month,
    ...(saving
      ? {
          condition: fields.conditionOn
            ? {
                min: money(fields.conditionMin),
                days: Number(fields.conditionDays) || 1,
              }
            : null,
          // Typed amounts replace the opening balance; an unticked box clears it; a ticked box with nothing
          // typed keeps what is stored.
          ...(fields.openingOn
            ? opening.length
              ? { opening: { date: fields.openingDate, amounts: opening } }
              : item?.opening
                ? {}
                : { opening: { date: fields.openingDate, amounts: [] } }
            : { opening: null }),
        }
      : {}),
  };
}

// The foot of the pop up: when it next runs, how many vehicles, and the total per run.
export function runSummary(
  fields: RecurringFields,
  item: RecurringItem | undefined,
  vehicleCount: number,
  today: string,
  formats: Pick<Formatter, "formatDateOnly" | "money" | "plural">,
) {
  const schedule = schedulePart(fields);
  const next = today
    ? recurringNextPosting(
        { ...schedule, start: item?.start ?? today, end: null },
        today,
      )
    : null;
  const when = !next
    ? ""
    : item
      ? `Next run ${formats.formatDateOnly(next)}`
      : next === today
        ? "First run today"
        : `First run ${formats.formatDateOnly(next)}`;
  const per = money(fields.amount);
  return {
    text: [when, formats.plural(vehicleCount, "vehicle", "vehicles")]
      .filter(Boolean)
      .join(", "),
    total: formats.money(Math.round(per * vehicleCount * 100) / 100),
  };
}
