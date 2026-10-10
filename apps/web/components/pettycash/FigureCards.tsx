"use client";

import type { PettyCashOverview } from "@xcode/shared/pettyCash";

import { useFormats } from "../../lib/formats";
import { BandSkeleton } from "../revenue/RegPlate";
import { BandFigure, BandOp, BandTerm } from "../ui";

// Cash balance = Opening balance + Cash issued - Expenses - Credit notes, as the terms of the headline card.
export function FigureCards({
  overview,
  label,
}: {
  overview?: PettyCashOverview;
  label: string;
}) {
  const formats = useFormats();

  if (!overview) return <BandSkeleton />;

  const { figures, from, to } = overview;

  return (
    <div
      role="group"
      aria-label={from === to ? "Day figures" : "Period figures"}
      className="contents"
    >
      <BandFigure
        main
        label={label}
        value={formats.formatNumber(figures.closingBalance)}
        negative={figures.closingBalance < 0}
      />
      <BandOp>=</BandOp>
      <BandTerm
        label="Opening balance"
        value={formats.kes(figures.openingBalance)}
      />
      <BandOp>+</BandOp>
      <BandTerm
        label="Cash issued"
        value={
          figures.cashReceived < 0
            ? `${formats.kes(figures.cashReceived)} returned`
            : formats.kes(figures.cashReceived)
        }
      />
      <BandOp>&minus;</BandOp>
      <BandTerm label="Expenses" value={formats.kes(figures.expenses)} />
      <BandOp>&minus;</BandOp>
      <BandTerm label="Credit notes" value={formats.kes(figures.creditNotes)} />
    </div>
  );
}
