import { RECURRING_FREQUENCY } from "../recurringPresentation";
import type { RecurringItem } from "../setup/shared";
import { formatShare } from "./allocation";

export const NOTE_LIMIT = 200;

export type RecurringFields = {
  kind: number;
  expenseItemId: string;
  name: string;
  note: string;
  amount: string;
  frequency: number;
  weekday: string;
  monthDay: string;
  month: string;
  // null until the date is edited: a new item then starts on the business date.
  start: string | null;
  end: string;
  noEnd: boolean;
};

export function initialFields(item?: RecurringItem): RecurringFields {
  const monthly =
    item?.frequency === RECURRING_FREQUENCY.monthly ||
    item?.frequency === RECURRING_FREQUENCY.yearly;
  return {
    kind: item?.kind || 1,
    expenseItemId: item?.expenseItemId ?? "",
    name: item?.kind === 2 ? item.name : "",
    note: item?.note ?? "",
    amount: item
      ? formatShare(
          item.allocations.reduce(
            (sum, allocation) => sum + allocation.amount,
            0,
          ),
        )
      : "",
    frequency: item?.frequency || RECURRING_FREQUENCY.monthly,
    weekday: String(
      item?.frequency === RECURRING_FREQUENCY.weekly ? (item.day ?? 6) : 6,
    ),
    monthDay:
      item && monthly ? (item.lastDay ? "last" : String(item.day ?? 1)) : "1",
    month: String(item?.month ?? 1),
    start: item?.start ?? null,
    end: item?.end || "",
    noEnd: !item?.end,
  };
}
