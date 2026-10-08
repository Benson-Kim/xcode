"use client";

import type { PettyCashOverview } from "@xcode/shared/pettyCash";

import { useFormats } from "../../lib/formats";
import { cn, StatGridSkeleton } from "../ui";

// The design's figure cards (.hero): money out tinted red, cash received green, the closing balance blue.
const TONES = {
  plain: "border-card-line bg-surface",
  out: "border-red-line/70 bg-red-bg/45",
  in: "border-green-line/70 bg-green-bg/45",
  close: "border-blue/25 bg-blue-tint",
} as const;

function Figure({
  label,
  value,
  tone,
  bad,
}: {
  label: string;
  value: string;
  tone: keyof typeof TONES;
  bad?: boolean;
}) {
  return (
    <div
      className={cn(
        "flex flex-col gap-1.5 rounded-2xl border px-5 py-4.5 shadow-[0_1px_2px_rgb(20_33_61/4%)]",
        TONES[tone],
      )}
    >
      <small className="text-[13px] text-grey">{label}</small>
      <strong
        className={cn(
          "text-[26px] leading-[1.15] font-bold tabular-nums",
          bad && "text-red",
        )}
      >
        {value}
      </strong>
    </div>
  );
}

export function FigureCards({ overview }: { overview?: PettyCashOverview }) {
  const formats = useFormats();

  if (!overview) return <StatGridSkeleton count={4} />;

  const { figures, period, businessDate } = overview;

  const week = period === "week";
  const current = week
    ? overview.from <= businessDate && businessDate <= overview.to
    : overview.date === businessDate;
  const label = current
    ? week
      ? "This week"
      : "Today"
    : week
      ? `Week of ${formats.formatDateOnly(overview.from)}`
      : formats.formatDateOnly(overview.date);

  return (
    <div
      role="group"
      aria-label={week ? "Week figures" : "Day figures"}
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
