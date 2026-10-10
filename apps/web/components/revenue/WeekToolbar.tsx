import { percentText } from "@xcode/shared/format";
import type { RevenueWeek } from "@xcode/shared/revenue";

import { useFormats } from "../../lib/formats";
import { shiftDate } from "../revenueFormat";
import {
  BandFigure,
  BandStats,
  bandControl,
  ChevronIcon,
  HeroBand,
  Skeleton,
} from "../ui";
import { BandSkeleton } from "./RegPlate";

const STEP =
  "grid h-[34px] w-[30px] place-items-center rounded-[9px] text-white hover:enabled:bg-glass-2 disabled:opacity-30";

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
    <div className="inline-flex items-center rounded-xl border border-glass-line bg-glass p-[3px]">
      <button
        type="button"
        aria-label="Previous week"
        disabled={!start}
        onClick={() => onWeek(shiftDate(start, -7))}
        className={STEP}
      >
        <ChevronIcon size={20} className="rotate-90" />
      </button>
      <strong
        aria-live="polite"
        className="min-w-[222px] px-2 text-center text-[15px] font-bold text-white max-[600px]:min-w-0"
      >
        {start ? (
          formats.formatDateRange(start, shiftDate(start, 6))
        ) : (
          <Skeleton className="mx-auto w-36" />
        )}
      </strong>
      <button
        type="button"
        aria-label="Next week"
        disabled={!shown || start >= shown.currentWeekStart}
        onClick={() => onWeek(shiftDate(start, 7))}
        className={STEP}
      >
        <ChevronIcon size={20} className="-rotate-90" />
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
        className={bandControl}
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
          <div className="flex flex-col gap-0.5">
            <BandFigure
              label="Week to date"
              value={formats.formatNumber(data.totalAmount)}
            />
            <small className="text-[13px] font-semibold text-on-deep">
              {`of ${formats.kes(data.totalExpected)} expected${data.percent === null ? "" : `, ${percentText(data.percent)}`}`}
            </small>
          </div>
          {counts && (
            <BandStats
              items={[
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
