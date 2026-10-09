"use client";

import type { ExpenseFigures } from "@xcode/shared/expenses";

import { useFormats } from "../../lib/formats";
import { Figure } from "../ui";

export function FigureCards({ figures }: { figures: ExpenseFigures }) {
  const formats = useFormats();
  return (
    <div
      role="group"
      aria-label="Period figures"
      className="grid grid-cols-[repeat(auto-fit,minmax(210px,1fr))] gap-3.5"
    >
      <Figure label="Total" value={formats.kes(figures.total)} tone="close" />
      <Figure
        label="Central"
        value={formats.kes(figures.central)}
        tone="plain"
      />
      <Figure
        label="Petty cash"
        value={formats.kes(figures.pettyCash)}
        tone="plain"
      />
      <Figure
        label="Scheduled"
        value={formats.kes(figures.scheduled)}
        tone="plain"
      />
    </div>
  );
}
