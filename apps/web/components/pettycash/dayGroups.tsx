"use client";

import { Fragment, type ReactNode } from "react";

import type { PettyCashEntry } from "@xcode/shared/pettyCash";

import { useFormats } from "../../lib/formats";

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

// A row naming a day (.grp), with what the day came to at its right.
export function DayRow({
  date,
  span,
  note,
}: {
  date: string;
  span: number;
  note: string;
}) {
  const formats = useFormats();
  return (
    <tr className="grp" data-day={date}>
      <td colSpan={span}>
        <div>
          <span>{formats.formatWeekdayDate(date)}</span>
          <span>{note}</span>
        </div>
      </td>
    </tr>
  );
}

// Lists the entries as they come, or under a row per day when several days are shown.
export function Days({
  entries,
  grouped,
  row,
  span,
  note,
}: {
  entries: PettyCashEntry[];
  grouped: boolean;
  row: (entry: PettyCashEntry) => ReactNode;
  span: number;
  note: (day: DayGroup) => string;
}) {
  if (!grouped) return entries.map(row);
  return groupByDay(entries).map((day) => (
    <Fragment key={day.date}>
      <DayRow date={day.date} span={span} note={note(day)} />
      {day.entries.map(row)}
    </Fragment>
  ));
}
