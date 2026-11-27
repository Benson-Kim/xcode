"use client";

import { mondayFirstIndex, weekdaysFrom } from "@xcode/shared/dates";

import { useFormats } from "../../lib/formats";
import { FormTotal, LinkButton } from "../ui";

// The seven day figures are kept Monday first, the order the API reads and serves them in; they are shown from the
// first day of the organization's week (Sunday, v2.41).
const DAY_COUNT = 7;

export const EMPTY_TARGETS: string[] = Array<string>(DAY_COUNT).fill("");

export const targetFigure = (text: string) => Number(text) || 0;

export const targetFigures = (values: string[]) => values.map(targetFigure);

export const hasEveryTarget = (values: string[]) =>
  targetFigures(values).every((figure) => figure > 0);

export const targetsToText = (days: number[] | null | undefined) =>
  days && days.length === DAY_COUNT
    ? days.map((figure) => String(figure))
    : EMPTY_TARGETS;

export function sameTargets(left: number[], right: number[]) {
  return (
    left.length === right.length &&
    left.every((figure, index) => figure === right[index])
  );
}

// The low revenue figure as typed: null while empty, so 0 (a reason only when nothing came in) stays a figure.
export const lowFigure = (text: string): number | null =>
  text === "" ? null : Number(text);

export const LOW_FIGURE_MISSING = "Enter the low revenue figure.";

// Below this figure a day's revenue needs a reason (v2.34); it sits under the seven day figures.
export function LowRevenueField({
  id,
  value,
  onChange,
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="f">
      <label htmlFor={id}>Low revenue below, KES</label>
      <input
        id={id}
        className="inp num"
        inputMode="numeric"
        autoComplete="off"
        value={value}
        onChange={(event) =>
          onChange(event.target.value.replace(/[^0-9]/g, ""))
        }
      />
    </div>
  );
}

export function DayTargetGrid({
  idPrefix,
  values,
  onChange,
}: {
  idPrefix: string;
  values: string[];
  onChange: (values: string[]) => void;
}) {
  const { formatNumber, firstDayOfWeek } = useFormats();
  const shown = weekdaysFrom(firstDayOfWeek()).map((day) => ({
    name: day.label,
    at: mondayFirstIndex(day.value),
  }));
  const total = targetFigures(values).reduce((sum, figure) => sum + figure, 0);
  // Copies the first figure typed, looking from the first day shown onwards.
  function sameEveryDay() {
    const first = shown
      .map(({ at }) => values[at] ?? "")
      .find((text) => targetFigure(text) > 0);
    if (!first) return document.getElementById(`${idPrefix}-0`)?.focus();
    onChange(values.map(() => first));
  }
  return (
    <>
      <div className="f">
        <div className="flabrow">
          <span className="flab">Target per day, KES</span>
          <LinkButton compact onClick={sameEveryDay}>
            Same every day
          </LinkButton>
        </div>
        <div className="tgrid">
          {shown.map(({ name, at: index }, position) => (
            <label key={name} className="tcell">
              <span>{name.slice(0, 3)}</span>
              <input
                id={`${idPrefix}-${position}`}
                className="inp num"
                inputMode="numeric"
                autoComplete="off"
                aria-label={`Target, ${name}`}
                value={values[index] ?? ""}
                onChange={(event) =>
                  onChange(
                    values.map((text, at) =>
                      at === index
                        ? event.target.value.replace(/[^0-9]/g, "")
                        : text,
                    ),
                  )
                }
              />
            </label>
          ))}
        </div>
      </div>
      <FormTotal label="Target for the week" value={formatNumber(total)} />
    </>
  );
}
