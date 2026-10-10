"use client";

import type { ExpenseFigures } from "@xcode/shared/expenses";

import { useFormats } from "../../lib/formats";
import { BandFigure, BandStats } from "../ui";

export function FigureCards({ figures }: { figures: ExpenseFigures }) {
  const formats = useFormats();
  return (
    <div role="group" aria-label="Period figures" className="contents">
      <BandFigure label="Total" value={formats.formatNumber(figures.total)} />
      <BandStats
        items={[
          { label: "Central", value: formats.formatNumber(figures.central) },
          {
            label: "Petty cash",
            value: formats.formatNumber(figures.pettyCash),
          },
          {
            label: "Scheduled",
            value: formats.formatNumber(figures.scheduled),
          },
        ]}
      />
    </div>
  );
}
