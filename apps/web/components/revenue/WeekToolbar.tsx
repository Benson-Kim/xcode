import { percentText } from "@xcode/shared/format";
import type { RevenueVehicle, RevenueWeek } from "@xcode/shared/revenue";

import { useFormats } from "../../lib/formats";
import { shiftDate } from "../revenueFormat";
import {
  Button,
  ChevronIcon,
  IconButton,
  SelectInput,
  Skeleton,
  Spacer,
  Toolbar,
} from "../ui";

export function WeekToolbar({
  start,
  shown,
  data,
  companyId,
  first,
  stale,
  onWeek,
  onCompany,
  onCapture,
}: {
  start: string;
  shown: RevenueWeek | undefined;
  data: RevenueWeek | undefined;
  companyId: string;
  first: { vehicle: RevenueVehicle; date: string } | null;
  stale: boolean;
  onWeek: (weekStart: string) => void;
  onCompany: (companyId: string) => void;
  onCapture: (
    target: { vehicle: RevenueVehicle; date: string },
    from: HTMLElement,
  ) => void;
}) {
  const formats = useFormats();
  return (
    <Toolbar>
      <div className="flex items-center gap-1">
        <IconButton
          aria-label="Previous week"
          disabled={!start}
          onClick={() => onWeek(shiftDate(start, -7))}
        >
          <ChevronIcon size={20} className="rotate-90" />
        </IconButton>
        <strong
          aria-live="polite"
          className="min-w-44 text-center text-[15px] max-[600px]:min-w-0"
        >
          {start ? (
            formats.formatDateRange(start, shiftDate(start, 6))
          ) : (
            <Skeleton className="mx-auto w-36" />
          )}
        </strong>
        <IconButton
          aria-label="Next week"
          disabled={!shown || start >= shown.currentWeekStart}
          onClick={() => onWeek(shiftDate(start, 7))}
        >
          <ChevronIcon size={20} className="-rotate-90" />
        </IconButton>
      </div>
      {/* While a filter is set, All companies stays one choice away even when this week lists a single company. */}
      {shown && (shown.companies.length > 1 || companyId) && (
        <SelectInput
          aria-label="Company"
          density="compact"
          inline
          value={companyId}
          onChange={(event) => onCompany(event.target.value)}
        >
          <option value="">All companies</option>
          {shown.companies.map((company) => (
            <option key={company.id} value={company.id}>
              {company.name}
            </option>
          ))}
        </SelectInput>
      )}
      <Spacer />
      {first && (
        <Button
          disabled={stale}
          aria-busy={stale ? true : undefined}
          onClick={(event) => onCapture(first, event.currentTarget)}
        >
          Capture revenue
        </Button>
      )}
      <div className="flex flex-col items-end leading-[1.3]">
        <small className="text-xs text-grey">Week to date</small>
        {data ? (
          <>
            <strong className="text-xl tabular-nums">
              {formats.kes(data.totalAmount)}
            </strong>
            <small className="text-xs text-grey">
              {`of ${formats.kes(data.totalExpected)} expected${data.percent === null ? "" : `, ${percentText(data.percent)}`}`}
            </small>
          </>
        ) : (
          <Skeleton className="mt-1 h-6 w-24" />
        )}
      </div>
    </Toolbar>
  );
}
