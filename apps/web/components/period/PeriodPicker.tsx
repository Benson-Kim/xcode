"use client";

import { useCallback, useId, useRef, useState } from "react";

import { EXPENSE_MAX_DAYS } from "@xcode/shared/expenses";
import {
  PERIOD_PRESETS,
  canMoveNext,
  customPeriod,
  matchingPreset,
  periodDays,
  presetPeriod,
  shiftPeriod,
  type Period,
  type PeriodUnit,
} from "@xcode/shared/periods";

import { useFormats } from "../../lib/formats";
import { Button, ChevronIcon, ErrorText, cn, useDismiss } from "../ui";

const UNIT_NAMES: Record<PeriodUnit, string> = {
  day: "day",
  week: "week",
  fourWeeks: "4 weeks",
  month: "month",
  custom: "period",
};

const MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

const STEP_BUTTON =
  "grid h-[34px] w-[30px] place-items-center rounded-[9px] text-ink hover:enabled:bg-paper-2 disabled:cursor-default disabled:opacity-30 [.hero_&]:text-white [.hero_&]:hover:enabled:bg-glass-2";

const SMALL_LABEL = "text-xs font-bold tracking-[.07em] text-slate uppercase";

// The message for a custom span that cannot be used, or "" when it can.
export function customRangeProblem(
  from: string,
  to: string,
  businessDate: string,
) {
  if (!from || !to) return "Enter both dates.";
  if (from > to) return "From cannot be after To.";
  if (to > businessDate) return "The dates cannot be after today.";
  if (periodDays({ from, to }) > EXPENSE_MAX_DAYS)
    return `A period can cover at most ${EXPENSE_MAX_DAYS} days.`;
  return "";
}

// Steps through periods of the same kind with the arrows, and opens a panel under the period to pick a preset or
// two dates. Presets count from the business date.
export function PeriodPicker({
  period,
  businessDate,
  firstDayOfWeek,
  onChange,
}: {
  period: Period;
  businessDate: string;
  firstDayOfWeek: number;
  onChange: (period: Period) => void;
}) {
  const formats = useFormats();
  const [open, setOpen] = useState(false);
  const wrapper = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const panelId = useId();
  const unit = UNIT_NAMES[period.unit];
  const label =
    period.unit === "day"
      ? formats.formatWeekdayDate(period.from)
      : formats.formatDateRange(period.from, period.to);

  const close = useCallback((returnFocus: boolean) => {
    setOpen(false);
    if (returnFocus) trigger.current?.focus();
  }, []);
  useDismiss(open, wrapper, close);

  function choose(next: Period) {
    onChange(next);
    close(true);
  }

  return (
    <div
      ref={wrapper}
      className="relative inline-flex items-center rounded-xl border border-line bg-surface p-[3px] [.hero_&]:border-glass-line [.hero_&]:bg-glass"
    >
      <button
        type="button"
        aria-label={`Previous ${unit}`}
        className={STEP_BUTTON}
        onClick={() => onChange(shiftPeriod(period, -1))}
      >
        <ChevronIcon size={20} className="rotate-90" />
      </button>
      <button
        ref={trigger}
        type="button"
        aria-label={`Period, ${label}`}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        onClick={() => setOpen((current) => !current)}
        className={cn(
          "flex h-[34px] items-center justify-center gap-[3px] rounded-[9px] pr-1 pl-2.5 text-[15px] font-bold whitespace-nowrap text-ink hover:bg-paper-2 [.hero_&]:text-white [.hero_&]:hover:bg-glass-2 max-[600px]:min-w-0",
          period.unit === "day" ? "min-w-[150px]" : "min-w-[222px]",
        )}
      >
        <span aria-live="polite">{label}</span>
        <ChevronIcon
          size={15}
          className={cn(
            "shrink-0 opacity-80 transition-transform motion-reduce:transition-none",
            open && "rotate-180",
          )}
        />
      </button>
      <button
        type="button"
        aria-label={`Next ${unit}`}
        disabled={!canMoveNext(period, businessDate)}
        className={STEP_BUTTON}
        onClick={() => onChange(shiftPeriod(period, 1))}
      >
        <ChevronIcon size={20} className="-rotate-90" />
      </button>
      {open && (
        <PeriodPanel
          id={panelId}
          period={period}
          businessDate={businessDate}
          firstDayOfWeek={firstDayOfWeek}
          onChoose={choose}
        />
      )}
    </div>
  );
}

function PeriodPanel({
  id,
  period,
  businessDate,
  firstDayOfWeek,
  onChoose,
}: {
  id: string;
  period: Period;
  businessDate: string;
  firstDayOfWeek: number;
  onChoose: (period: Period) => void;
}) {
  const current = matchingPreset(period, businessDate, firstDayOfWeek);
  const [from, setFrom] = useState(period.from);
  const [to, setTo] = useState(period.to);
  const [problem, setProblem] = useState("");
  const startYear = Math.min(
    Number(businessDate.slice(0, 4)) - 4,
    Number(period.from.slice(0, 4)),
  );

  function show() {
    const found = customRangeProblem(from, to, businessDate);
    setProblem(found);
    if (!found) onChoose(customPeriod(from, to));
  }

  return (
    <div
      id={id}
      role="dialog"
      aria-label="Choose a period"
      className="absolute top-full left-0 z-40 mt-2 flex w-[min(308px,calc(100vw-2rem))] flex-col gap-1.5 rounded-2xl border border-line bg-surface p-2 text-ink shadow-[0_18px_44px_rgba(4,32,47,.24)]"
    >
      <ul className="m-0 grid list-none grid-cols-2 gap-0.5 p-0">
        {PERIOD_PRESETS.map((preset) => (
          <li key={preset.id}>
            <button
              type="button"
              autoFocus={preset.id === (current ?? PERIOD_PRESETS[0].id)}
              aria-current={preset.id === current ? "true" : undefined}
              onClick={() =>
                onChoose(presetPeriod(preset.id, businessDate, firstDayOfWeek))
              }
              className="flex w-full items-center justify-between gap-2.5 rounded-[9px] px-3 py-[9px] text-left text-[14.5px] font-semibold whitespace-nowrap text-ink hover:bg-paper aria-[current=true]:bg-teal-wash aria-[current=true]:font-bold aria-[current=true]:text-teal aria-[current=true]:after:font-extrabold aria-[current=true]:after:content-['\2713']"
            >
              {preset.label}
            </button>
          </li>
        ))}
      </ul>
      <div className="flex flex-col gap-2.5 border-t border-divider px-1.5 pt-3 pb-1">
        <span className={SMALL_LABEL}>Custom dates</span>
        <DateField
          label="From"
          value={from}
          max={businessDate}
          startYear={startYear}
          invalid={Boolean(problem)}
          onChange={setFrom}
        />
        <DateField
          label="To"
          value={to}
          max={businessDate}
          startYear={startYear}
          invalid={Boolean(problem)}
          onChange={setTo}
        />
        {problem && <ErrorText>{problem}</ErrorText>}
        <Button tone="ok" onClick={show}>
          Show these dates
        </Button>
      </div>
    </div>
  );
}

const SELECT =
  "w-full min-w-0 rounded-[10px] border border-line bg-surface px-1.5 py-2 text-sm text-ink focus:border-teal focus:outline-3 focus:outline-offset-1 focus:outline-teal/30 aria-invalid:border-clay aria-invalid:bg-clay-wash";

// Day, month and year lists over one ISO date. The date input beside them holds the same value for keyboards
// and assistive technology that prefer it.
function DateField({
  label,
  value,
  max,
  startYear,
  invalid,
  onChange,
}: {
  label: string;
  value: string;
  max: string;
  startYear: number;
  invalid: boolean;
  onChange: (value: string) => void;
}) {
  const parsed = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  const year = parsed ? Number(parsed[1]) : null;
  const month = parsed ? Number(parsed[2]) - 1 : null;
  const day = parsed ? Number(parsed[3]) : null;
  const endYear = Number(max.slice(0, 4));
  const first = Math.min(startYear, year ?? startYear);
  const years = Array.from(
    { length: Math.max(endYear, year ?? endYear) - first + 1 },
    (_, index) => first + index,
  );

  function pick(next: { year?: number; month?: number; day?: number }) {
    const y = next.year ?? year ?? endYear;
    const m = next.month ?? month ?? 0;
    const length = new Date(Date.UTC(y, m + 1, 0)).getUTCDate();
    const d = Math.min(next.day ?? day ?? 1, length);
    onChange(
      `${String(y).padStart(4, "0")}-${String(m + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`,
    );
  }

  const invalidFlag = invalid ? true : undefined;
  return (
    <div className="flex flex-col gap-1.5">
      <span className={SMALL_LABEL}>{label}</span>
      <div className="grid grid-cols-[62px_minmax(0,1fr)_76px] gap-1.5">
        <select
          aria-label={`${label} day`}
          aria-invalid={invalidFlag}
          className={SELECT}
          value={day ?? ""}
          onChange={(event) => pick({ day: Number(event.target.value) })}
        >
          {day === null && <option value="" />}
          {Array.from({ length: 31 }, (_, index) => (
            <option key={index} value={index + 1}>
              {index + 1}
            </option>
          ))}
        </select>
        <select
          aria-label={`${label} month`}
          aria-invalid={invalidFlag}
          className={SELECT}
          value={month ?? ""}
          onChange={(event) => pick({ month: Number(event.target.value) })}
        >
          {month === null && <option value="" />}
          {MONTHS.map((name, index) => (
            <option key={name} value={index}>
              {name}
            </option>
          ))}
        </select>
        <select
          aria-label={`${label} year`}
          aria-invalid={invalidFlag}
          className={SELECT}
          value={year ?? ""}
          onChange={(event) => pick({ year: Number(event.target.value) })}
        >
          {year === null && <option value="" />}
          {years.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </div>
      <input
        type="date"
        aria-label={label}
        aria-invalid={invalidFlag}
        aria-hidden="true"
        tabIndex={-1}
        max={max}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="sr-only"
      />
    </div>
  );
}
