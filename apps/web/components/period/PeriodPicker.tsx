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
import {
  Button,
  ChevronIcon,
  ErrorText,
  IconButton,
  SubHeading,
  TextInput,
  cn,
  useDismiss,
} from "../ui";

const UNIT_NAMES: Record<PeriodUnit, string> = {
  day: "day",
  week: "week",
  fourWeeks: "4 weeks",
  month: "month",
  custom: "period",
};

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
    <div ref={wrapper} className="relative flex items-center gap-1">
      <IconButton
        aria-label={`Previous ${unit}`}
        onClick={() => onChange(shiftPeriod(period, -1))}
      >
        <ChevronIcon size={20} className="rotate-90" />
      </IconButton>
      <button
        ref={trigger}
        type="button"
        aria-label={`Period, ${label}`}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        onClick={() => setOpen((current) => !current)}
        className="flex h-11 min-w-44 items-center justify-center gap-2 rounded-[10px] border border-line bg-surface px-3 text-[15px] font-semibold text-navy hover:border-blue max-[600px]:min-w-0"
      >
        <span aria-live="polite">{label}</span>
        <ChevronIcon
          className={cn(
            "shrink-0 text-grey transition-transform motion-reduce:transition-none",
            open && "rotate-180",
          )}
        />
      </button>
      <IconButton
        aria-label={`Next ${unit}`}
        disabled={!canMoveNext(period, businessDate)}
        onClick={() => onChange(shiftPeriod(period, 1))}
      >
        <ChevronIcon size={20} className="-rotate-90" />
      </IconButton>
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
      className="absolute top-full left-0 z-40 mt-2 flex w-[min(20rem,calc(100vw-2rem))] flex-col gap-1 rounded-xl border border-card-line bg-surface p-2 shadow-menu"
    >
      <ul className="m-0 flex list-none flex-col gap-0.5 p-0">
        {PERIOD_PRESETS.map((preset) => (
          <li key={preset.id}>
            <button
              type="button"
              autoFocus={preset.id === (current ?? PERIOD_PRESETS[0].id)}
              aria-current={preset.id === current ? "true" : undefined}
              onClick={() =>
                onChoose(presetPeriod(preset.id, businessDate, firstDayOfWeek))
              }
              className="flex min-h-10 w-full items-center rounded-lg px-3 text-left text-[15px] hover:bg-hover aria-[current=true]:bg-blue-soft aria-[current=true]:font-bold aria-[current=true]:text-blue-dark"
            >
              {preset.label}
            </button>
          </li>
        ))}
      </ul>
      <div className="mt-1 flex flex-col gap-2 border-t border-divider px-1 pt-1 pb-1">
        <SubHeading className="mt-1 mb-0">Custom dates</SubHeading>
        <div className="grid grid-cols-2 gap-2">
          <label className="flex flex-col gap-1 text-[13px] font-semibold text-grey">
            From
            <TextInput
              type="date"
              density="compact"
              max={businessDate}
              value={from}
              aria-invalid={problem ? true : undefined}
              onChange={(event) => setFrom(event.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1 text-[13px] font-semibold text-grey">
            To
            <TextInput
              type="date"
              density="compact"
              max={businessDate}
              value={to}
              aria-invalid={problem ? true : undefined}
              onChange={(event) => setTo(event.target.value)}
            />
          </label>
        </div>
        {problem && <ErrorText>{problem}</ErrorText>}
        <Button tone="outline" onClick={show}>
          Show these dates
        </Button>
      </div>
    </div>
  );
}
