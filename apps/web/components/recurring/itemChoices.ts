import type { ExpenseBucket, ExpenseItemOption } from "../../lib/types";
import { RECURRING_FREQUENCY } from "../recurringPresentation";
import {
  costBucket,
  expenseBucketNames,
  type RecurringItem,
} from "../setup/shared";

// An expense item in the picker. `off` marks the item a saved cost uses once it is no longer active.
export type ItemChoice = {
  id: string;
  name: string;
  categoryId: string;
  categoryName: string;
  bucket: ExpenseBucket | null;
  off: boolean;
};

export type ItemPicker = {
  groups: ItemChoice[][];
  picked?: ItemChoice;
  countedAs?: string;
  noExpenseItem: boolean;
};

export function buildItemChoices(
  expenseItems: ExpenseItemOption[] | undefined,
  item?: RecurringItem,
): ItemChoice[] {
  const choices: ItemChoice[] = (expenseItems ?? []).map((option) => ({
    ...option,
    off: false,
  }));
  if (
    item?.expenseItemId &&
    !choices.some((choice) => choice.id === item.expenseItemId)
  )
    choices.unshift({
      id: item.expenseItemId,
      name: item.expenseItemName || item.name,
      categoryId: "",
      categoryName: "",
      bucket: item.bucket ?? null,
      off: expenseItems !== undefined,
    });
  return choices;
}

export function groupByCategory(choices: ItemChoice[]) {
  return [
    ...choices
      .reduce(
        (groups, choice) =>
          groups.set(choice.categoryId, [
            ...(groups.get(choice.categoryId) ?? []),
            choice,
          ]),
        new Map<string, ItemChoice[]>(),
      )
      .values(),
  ];
}

export function countedAs(
  picked: ItemChoice | undefined,
  savedBucket: ExpenseBucket | null,
  expenseItemId: string,
) {
  return picked?.bucket
    ? expenseBucketNames[picked.bucket]
    : savedBucket && !expenseItemId
      ? expenseBucketNames[savedBucket]
      : undefined;
}

export function itemPicker(
  expenseItems: ExpenseItemOption[] | undefined,
  item: RecurringItem | undefined,
  expenseItemId: string,
): ItemPicker {
  // Items saved before expense items, or on the daily schedule, keep posting until someone changes them.
  const noExpenseItem = Boolean(item?.kind === 1 && !item.expenseItemId);
  // Until an expense item is chosen, such a row keeps counting in the bucket it was saved under.
  const savedBucket = item && noExpenseItem ? costBucket(item) : null;
  const choices = buildItemChoices(expenseItems, item);
  const picked = choices.find((choice) => choice.id === expenseItemId);
  return {
    groups: groupByCategory(choices),
    picked,
    countedAs: countedAs(picked, savedBucket, expenseItemId),
    noExpenseItem,
  };
}

// What an item saved under the old rules must be given before any change to it can be saved.
export function legacyNeeds(
  item: RecurringItem | undefined,
  picker: ItemPicker,
) {
  return [
    picker.noExpenseItem && "an expense item",
    item?.frequency === RECURRING_FREQUENCY.daily && "how often it posts",
  ].filter(Boolean);
}
