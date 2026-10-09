"use client";

import type { PettyCashOverview } from "@xcode/shared/pettyCash";

import { useFormats } from "../../lib/formats";
import { Figure, StatGridSkeleton } from "../ui";

export function FigureCards({ overview }: { overview?: PettyCashOverview }) {
  const formats = useFormats();

  if (!overview) return <StatGridSkeleton count={4} />;

  const { figures, businessDate, from, to } = overview;

  const day = from === to;
  const label = day
    ? from === businessDate
      ? "Today"
      : formats.formatDateOnly(from)
    : formats.formatDateRange(from, to);

  return (
    <div
      role="group"
      aria-label={day ? "Day figures" : "Period figures"}
      className="grid grid-cols-[repeat(auto-fit,minmax(210px,1fr))] gap-3.5"
    >
      <Figure
        label="Opening cash balance"
        value={formats.kes(figures.openingBalance)}
        tone="plain"
        bad={figures.openingBalance < 0}
      />
      <Figure
        label={`${label}, money out`}
        value={formats.kes(figures.moneyOut)}
        tone="out"
      />
      <Figure
        label={`${label}, cash received`}
        value={
          figures.cashReceived < 0
            ? `${formats.kes(figures.cashReceived)} returned`
            : formats.kes(figures.cashReceived)
        }
        tone="in"
      />
      <Figure
        label="Closing cash balance"
        value={formats.kes(figures.closingBalance)}
        tone="close"
        bad={figures.closingBalance < 0}
      />
    </div>
  );
}
