"use client";

import type { ReactNode } from "react";

import type { PettyCashEntry } from "@xcode/shared/pettyCash";

import { useFormats } from "../../lib/formats";
import { Td, Tr } from "../ui";

export type DayGroup = {
  date: string;
  entries: PettyCashEntry[];
  total: number;
};

// The entries under their days, in the order the days first appear, with what each day came to.
export function groupByDay(entries: PettyCashEntry[]): DayGroup[] {
  const days = new Map<string, DayGroup>();
  for (const entry of entries) {
    const day = days.get(entry.date) ?? {
      date: entry.date,
      entries: [],
      total: 0,
    };
    day.entries.push(entry);
    day.total = Math.round((day.total + entry.total) * 100) / 100;
    days.set(entry.date, day);
  }
  return [...days.values()];
}

// A row naming a day, with its total in the column that holds the amounts. `before` cells come first and `after`
// cells follow.
export function DayRow({
  date,
  total,
  before,
  after,
  label,
}: {
  date: string;
  total: number;
  before: number;
  after: number;
  label: string;
}) {
  const formats = useFormats();
  return (
    <Tr className="bg-paper-2" data-day={date}>
      <Td colSpan={before} className="font-bold text-ink">
        {formats.formatWeekdayDate(date)}
      </Td>
      <Td numeric label={label} className="font-bold text-slate">
        {formats.formatNumber(total)}
      </Td>
      {after > 0 && <Td colSpan={after} />}
    </Tr>
  );
}

// Lists the entries as they come, or under a row per day when several days are shown.
export function Days({
  entries,
  grouped,
  row,
  before,
  after,
  totalLabel,
}: {
  entries: PettyCashEntry[];
  grouped: boolean;
  row: (entry: PettyCashEntry) => ReactNode;
  before: number;
  after: number;
  totalLabel: string;
}) {
  if (!grouped) return entries.map(row);
  return groupByDay(entries).map((day) => (
    <DayGroupRows
      key={day.date}
      day={day}
      row={row}
      before={before}
      after={after}
      label={totalLabel}
    />
  ));
}

function DayGroupRows({
  day,
  row,
  before,
  after,
  label,
}: {
  day: DayGroup;
  row: (entry: PettyCashEntry) => ReactNode;
  before: number;
  after: number;
  label: string;
}) {
  return (
    <>
      <DayRow
        date={day.date}
        total={day.total}
        before={before}
        after={after}
        label={label}
      />
      {day.entries.map(row)}
    </>
  );
}
