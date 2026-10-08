// Revenue days are the organization's calendar dates ("yyyy-MM-dd"), worked out in UTC so the phone's own
// clock and time zone never move them.
import {
  daysBetween,
  firstOfMonth,
  isDate,
  shiftDate,
  startOfWeek,
} from "@xcode/shared/dates";

export { daysBetween, firstOfMonth, isDate, shiftDate, startOfWeek };

// The first day of the organization's week that holds a date on or before the current week, from the current
// week's first day as the API reports it (the organization chooses which weekday starts its week).
export const weekHolding = (date: string, currentWeekStart: string) =>
  shiftDate(
    currentWeekStart,
    -7 * Math.ceil(daysBetween(date, currentWeekStart) / 7),
  );
