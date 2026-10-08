import { WEEKDAYS } from "@xcode/shared/dates";

import { RECURRING_FREQUENCY } from "../recurringPresentation";
import type { RecurringItem } from "../setup/shared";
import type { RecurringFields } from "./fields";

export const weekdays = [...WEEKDAYS.slice(1), WEEKDAYS[0]];

export const dayOptions = Array.from({ length: 28 }, (_, index) => index + 1);

export function periodIsValid(fields: RecurringFields, start: string) {
  return fields.noEnd || Boolean(fields.end && fields.end >= start);
}

export function buildSchedule(fields: RecurringFields, start: string) {
  const { frequency, monthDay, noEnd, end } = fields;
  const lastDay =
    (frequency === RECURRING_FREQUENCY.monthly ||
      frequency === RECURRING_FREQUENCY.yearly) &&
    monthDay === "last";
  return {
    frequency,
    day:
      frequency === RECURRING_FREQUENCY.weekly
        ? Number(fields.weekday)
        : frequency === RECURRING_FREQUENCY.daily || lastDay
          ? null
          : Number(monthDay),
    lastDay,
    month:
      frequency === RECURRING_FREQUENCY.yearly ? Number(fields.month) : null,
    start,
    end: noEnd ? null : end || null,
  };
}

export type ItemStatus = {
  stopped: boolean;
  futureStop: string | null;
  startLocked: boolean;
};

export function itemStatus(
  item: RecurringItem | undefined,
  today: string | undefined,
): ItemStatus {
  return {
    stopped: Boolean(
      item?.stoppedFrom && (!today || item.stoppedFrom <= today),
    ),
    futureStop:
      item?.stoppedFrom && today && item.stoppedFrom > today
        ? item.stoppedFrom
        : null,
    startLocked: Boolean(item && (!today || item.start < today)),
  };
}
