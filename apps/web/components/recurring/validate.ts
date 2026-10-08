import type { Formatter } from "@xcode/shared/format";

import { RECURRING_FREQUENCY } from "../recurringPresentation";
import type { RecurringItem } from "../setup/shared";
import { NOTE_LIMIT } from "./fields";
import type { ItemChoice } from "./itemChoices";

export type Errors = Partial<
  Record<
    | "expenseItem"
    | "name"
    | "note"
    | "amount"
    | "frequency"
    | "start"
    | "end"
    | "allocations",
    string
  >
>;

export type RecurringInput = {
  item?: RecurringItem;
  kind: number;
  picked?: ItemChoice;
  name: string;
  note: string;
  total: number;
  frequency: number;
  start: string;
  end: string;
  noEnd: boolean;
  earliestStart?: string;
  selectedCount: number;
  allocationTotal: number;
  // Cents still to allocate: positive when short, negative when over.
  difference: number;
};

export function validateRecurring(
  input: RecurringInput,
  { kes, formatDateOnly }: Pick<Formatter, "kes" | "formatDateOnly">,
): Errors {
  const { item, kind, picked, start, end, noEnd, earliestStart } = input;
  const next: Errors = {};

  if (kind === 1 && !picked) next.expenseItem = "Choose the expense item.";
  else if (kind === 1 && picked?.off)
    next.expenseItem = "This item is turned off. Choose another expense item.";
  if (kind === 2 && !input.name.trim()) next.name = "Enter a name.";
  if (input.note.trim().length > NOTE_LIMIT)
    next.note = `Keep the note to ${NOTE_LIMIT} characters.`;
  if (input.total <= 0) next.amount = "Enter the amount in KES.";
  if (input.frequency === RECURRING_FREQUENCY.daily)
    next.frequency =
      "Every day is no longer offered. Choose how often it posts.";
  if (!start) next.start = "Enter the start date.";
  else if (
    earliestStart &&
    start < earliestStart &&
    (!item || start !== item.start)
  )
    next.start = `Start on or after ${formatDateOnly(earliestStart)}. Anything earlier is a one-off expense, not a schedule.`;
  if (!noEnd && (!end || end < start))
    next.end = "The end date must be on or after the start date.";
  if (!input.selectedCount) next.allocations = "Tick at least one vehicle.";
  else if (input.difference !== 0)
    next.allocations = `The split must add up to ${kes(input.total)}. It is ${kes(input.allocationTotal)}.`;
  return next;
}
