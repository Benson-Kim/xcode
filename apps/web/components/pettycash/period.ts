import type { PettyCashPeriod } from "@xcode/shared/pettyCash";

export const PERIODS: { value: PettyCashPeriod; label: string }[] = [
  { value: "day", label: "Day" },
  { value: "week", label: "Week" },
];

// The days the figures and lists cover. A week's range comes from the server, which cuts weeks on the organization's
// first day of the week.
export type PeriodRange = { from: string; to: string };

export const periodStep = (period: PettyCashPeriod) =>
  period === "week" ? 7 : 1;
