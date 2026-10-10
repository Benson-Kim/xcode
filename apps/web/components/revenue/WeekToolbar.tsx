import { percentText } from "@xcode/shared/format";
import type { RevenueWeek } from "@xcode/shared/revenue";

import { useFormats } from "../../lib/formats";
import { shiftDate } from "../revenueFormat";
import { BandFigure, BandStats, HeroBand, Skeleton } from "../ui";
import { BandSkeleton } from "./RegPlate";

function countDays(week: RevenueWeek) {
  let noRevenue = 0;
  let missing = 0;
  for (const vehicle of week.vehicles)
    for (const day of vehicle.days) {
      if (day.status === "reason") noRevenue++;
      else if (day.status === "missing") missing++;
    }
  return { noRevenue, missing };
}

export function WeekToolbar({
  start,
  shown,
  data,
  companyId,
  onWeek,
  onCompany,
}: {
  start: string;
  shown: RevenueWeek | undefined;
  data: RevenueWeek | undefined;
  companyId: string;
  onWeek: (weekStart: string) => void;
  onCompany: (companyId: string) => void;
}) {
  const formats = useFormats();
  const counts = data && countDays(data);
  const period = (
    <div className="step">
      <button
        type="button"
        aria-label="Previous week"
        disabled={!start}
        onClick={() => onWeek(shiftDate(start, -7))}
      >
        ‹
      </button>
      <span className="d" aria-live="polite">
        {start ? (
          formats.formatDateRange(start, shiftDate(start, 6))
        ) : (
          <Skeleton className="mx-auto w-36" />
        )}
      </span>
      <button
        type="button"
        aria-label="Next week"
        disabled={!shown || start >= shown.currentWeekStart}
        onClick={() => onWeek(shiftDate(start, 7))}
      >
        ›
      </button>
    </div>
  );
  const tools =
    // While a filter is set, All companies stays one choice away even when this week lists a single company.
    shown && (shown.companies.length > 1 || companyId) ? (
      <select
        aria-label="Company"
        value={companyId}
        onChange={(event) => onCompany(event.target.value)}
        className="inp"
      >
        <option value="">All companies</option>
        {shown.companies.map((company) => (
          <option key={company.id} value={company.id}>
            {company.name}
          </option>
        ))}
      </select>
    ) : undefined;
  return (
    <HeroBand period={period} tools={tools}>
      {data ? (
        <>
          <BandFigure
            label="Revenue"
            value={formats.formatNumber(data.totalAmount)}
          />
          {counts && (
            <BandStats
              items={[
                {
                  label: "Expected",
                  value: formats.formatNumber(data.totalExpected),
                },
                {
                  label: "Reached",
                  value: data.percent === null ? "" : percentText(data.percent),
                },
                { label: "No revenue days", value: String(counts.noRevenue) },
                {
                  label: "Missing days",
                  value: String(counts.missing),
                  tone: counts.missing > 0 ? "neg" : undefined,
                },
              ]}
            />
          )}
        </>
      ) : (
        <BandSkeleton />
      )}
    </HeroBand>
  );
}
