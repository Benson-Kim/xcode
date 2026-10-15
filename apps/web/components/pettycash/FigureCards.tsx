"use client";

import type { PettyCashOverview } from "@xcode/shared/pettyCash";

import { useFormats } from "../../lib/formats";
import { BandSkeleton } from "../revenue/RegPlate";
import { BandFigure, BandTerm } from "../ui";

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
      <BandTerm
        op="="
        label="Opening balance"
        value={formats.formatNumber(figures.openingBalance)}
      />
      <BandTerm
        op="+"
        label="Cash issued"
        value={
          figures.cashReceived < 0
            ? `${formats.formatNumber(figures.cashReceived)} returned`
            : formats.formatNumber(figures.cashReceived)
        }
      />
      <BandTerm
        op={"−"}
        label="Expenses"
        value={formats.formatNumber(figures.expenses)}
      />
      <BandTerm
        op={"−"}
        label="Credit notes"
        value={formats.formatNumber(figures.creditNotes)}
      />
    </div>
  );
}
