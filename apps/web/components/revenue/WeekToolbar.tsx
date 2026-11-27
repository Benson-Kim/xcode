import type { ReactNode } from "react";

import { gapText, type RevenueWeek } from "@xcode/shared/revenue";

import { useFormats } from "../../lib/formats";
import { shiftDate } from "../revenueFormat";
import { BandFigure, BandStats, HeroBand, Skeleton } from "../ui";
import { BandSkeleton } from "./RegPlate";
import { weekCounts } from "./summaryImage";

export function WeekToolbar({
  start,
  shown,
  data,
  companyId,
  search,
  showTargets,
  exportMenu,
  onWeek,
  onCompany,
  onSearch,
}: {
  start: string;
  shown: RevenueWeek | undefined;
  data: RevenueWeek | undefined;
  companyId: string;
  search: string;
  // False while Targets is switched off (v2.38): no Gap to target figure.
  showTargets: boolean;
  exportMenu?: ReactNode;
  onWeek: (weekStart: string) => void;
  onCompany: (companyId: string) => void;
  onSearch: (value: string) => void;
}) {
  const formats = useFormats();
  const counts = data && weekCounts(data);
  // A week still running is judged on its days so far.
  const finished = data ? data.weekThrough < data.businessDate : false;
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
  // While a filter is set, All companies stays one choice away even when this week lists a single company.
  const companies =
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
  const tools = (
    <>
      {companies}
      <input
        className="inp srch"
        type="search"
        placeholder="Search vehicle"
        aria-label="Search vehicle"
        value={search}
        onChange={(event) => onSearch(event.target.value)}
      />
      {exportMenu}
    </>
  );
  return (
    <HeroBand
      period={period}
      tools={tools}
      toolsClass={companies ? undefined : "slim"}
    >
      {data ? (
        <>
          <BandFigure
            label="Revenue"
            value={formats.formatNumber(data.totalAmount)}
          />
          {counts && (
            <BandStats
              items={[
                ...(showTargets
                  ? [
                      {
                        label: finished
                          ? "Gap to target"
                          : "Gap to target so far",
                        value:
                          data.gap === null || data.gap === undefined
                            ? "0"
                            : gapText(data.gap, formats.formatNumber),
                      },
                    ]
                  : []),
                // Days below each vehicle's own low figure, and no revenue days (v2.34).
                { label: "Low days", value: String(counts.low) },
                { label: "Not fueled", value: String(counts.notFueled) },
                {
                  label: "Missing days",
                  value: String(counts.missing),
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
