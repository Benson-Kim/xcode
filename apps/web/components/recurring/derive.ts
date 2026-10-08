import { firstOfMonth } from "@xcode/shared/dates";

import type { SaveRecurringRequest } from "../../lib/endpoints/recurring";
import type { ExpenseItemOption } from "../../lib/types";
import type { RecurringItem } from "../setup/shared";
import type { RecurringFields } from "./fields";
import { itemPicker, legacyNeeds } from "./itemChoices";
import { buildSchedule, itemStatus, periodIsValid } from "./schedule";
import type { RecurringInput } from "./validate";

type Source = {
  item?: RecurringItem;
  fields: RecurringFields;
  expenseItems?: ExpenseItemOption[];
  today?: string;
};

// Everything the form shows or checks that follows from its fields and the business date.
export function deriveRecurring({ item, fields, expenseItems, today }: Source) {
  const picker = itemPicker(expenseItems, item, fields.expenseItemId);
  const start = fields.start ?? today ?? "";
  return {
    status: itemStatus(item, today),
    earliestStart: today ? firstOfMonth(today) : undefined,
    picker,
    start,
    periodOk: periodIsValid(fields, start),
    schedule: buildSchedule(fields, start),
    legacyNeeds: legacyNeeds(item, picker),
    title:
      fields.kind === 1
        ? picker.picked?.name || item?.name || ""
        : fields.name.trim(),
  };
}

export type Derived = ReturnType<typeof deriveRecurring>;

type Allocation = {
  selected: string[];
  shares: Record<string, string>;
  total: number;
  allocationTotal: number;
  difference: number;
};

export function recurringInput(
  item: RecurringItem | undefined,
  fields: RecurringFields,
  derived: Derived,
  alloc: Allocation,
): RecurringInput {
  return {
    item,
    kind: fields.kind,
    picked: derived.picker.picked,
    name: fields.name,
    note: fields.note,
    total: alloc.total,
    frequency: fields.frequency,
    start: derived.start,
    end: fields.end,
    noEnd: fields.noEnd,
    earliestStart: derived.earliestStart,
    selectedCount: alloc.selected.length,
    allocationTotal: alloc.allocationTotal,
    difference: alloc.difference,
  };
}

export function recurringRequest(
  fields: RecurringFields,
  derived: Derived,
  alloc: Allocation,
): SaveRecurringRequest {
  const { schedule } = derived;
  return {
    name: derived.title,
    kind: fields.kind,
    amount: alloc.total,
    frequency: fields.frequency,
    day: schedule.day,
    lastDay: schedule.lastDay,
    start: derived.start,
    end: fields.noEnd ? null : fields.end,
    allocations: alloc.selected.map((vehicleId) => ({
      vehicleId,
      amount: Number(alloc.shares[vehicleId]) || 0,
    })),
    expenseItemId: fields.kind === 1 ? fields.expenseItemId : null,
    note: fields.note.trim() || null,
    month: schedule.month,
  };
}
