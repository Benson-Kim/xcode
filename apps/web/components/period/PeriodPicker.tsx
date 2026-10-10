"use client";

import {
  useCallback,
  useId,
  useRef,
  useState,
  type KeyboardEvent,
  type RefObject,
} from "react";

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
  cn,
  controlClass,
  useAnchoredPosition,
  useDismiss,
} from "../ui";

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

// The design's date control (.step): ‹ and › step through periods of the same kind, and the period itself (.d) opens
// a pop over (.pop.date) with the presets (.plist.two) and two custom dates (.pcustom). Presets count from the
// business date.
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
  const panel = useRef<HTMLDivElement>(null);
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
  useAnchoredPosition(open, wrapper, panel);

  function choose(next: Period) {
    onChange(next);
    close(true);
  }

  return (
    <div ref={wrapper} className={cn("step", period.unit === "day" && "day")}>
      <button
        type="button"
        aria-label={`Previous ${unit}`}
        onClick={() => onChange(shiftPeriod(period, -1))}
      >
        ‹
      </button>
      <button
        ref={trigger}
        type="button"
        aria-label={`Period, ${label}`}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        title="Choose dates"
        onClick={() => setOpen((current) => !current)}
        className="d"
      >
        <span aria-live="polite">{label}</span>
        <ChevronIcon />
      </button>
      <button
        type="button"
        aria-label={`Next ${unit}`}
        disabled={!canMoveNext(period, businessDate)}
        onClick={() => onChange(shiftPeriod(period, 1))}
      >
        ›
      </button>
      {open && (
        <PeriodPanel
          panelRef={panel}
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

// Up and down (or left and right) move between the presets, as in a menu.
function moveInMenu(event: KeyboardEvent<HTMLDivElement>) {
  const step =
    event.key === "ArrowDown" || event.key === "ArrowRight"
      ? 1
      : event.key === "ArrowUp" || event.key === "ArrowLeft"
        ? -1
        : 0;
  if (!step) return;
  event.preventDefault();
  const items = [
    ...event.currentTarget.querySelectorAll<HTMLElement>('[role^="menuitem"]'),
  ];
  const at = items.indexOf(document.activeElement as HTMLElement);
  items[(at + step + items.length) % items.length]?.focus();
}

function PeriodPanel({
  panelRef,
  id,
  period,
  businessDate,
  firstDayOfWeek,
  onChoose,
}: {
  panelRef: RefObject<HTMLDivElement | null>;
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
      ref={panelRef}
      id={id}
      role="dialog"
      aria-label="Choose a period"
      className="pop date max-w-[calc(100vw-16px)]"
    >
      <div
        className="plist two"
        role="menu"
        aria-label="Periods"
        onKeyDown={moveInMenu}
      >
        {PERIOD_PRESETS.map((preset) => (
          <button
            key={preset.id}
            type="button"
            role="menuitemradio"
            autoFocus={preset.id === (current ?? PERIOD_PRESETS[0].id)}
            aria-checked={preset.id === current}
            onClick={() =>
              onChoose(presetPeriod(preset.id, businessDate, firstDayOfWeek))
            }
          >
            {preset.label}
          </button>
        ))}
      </div>
      <div className="pcustom">
        <span className="flab">Custom dates</span>
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
    <div className="f">
      <span className="flab">{label}</span>
      <div className="dsel">
        <select
          aria-label={`${label} day`}
          aria-invalid={invalidFlag}
          className={controlClass(invalidFlag)}
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
          className={controlClass(invalidFlag)}
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
          className={controlClass(invalidFlag)}
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
