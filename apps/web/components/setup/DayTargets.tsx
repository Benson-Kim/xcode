"use client";

import { useFormats } from "../../lib/formats";
import { FormTotal, LinkButton } from "../ui";

const DAYS = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
] as const;

export const EMPTY_TARGETS: string[] = DAYS.map(() => "");

export const targetFigure = (text: string) => Number(text) || 0;

export const targetFigures = (values: string[]) => values.map(targetFigure);

export const hasEveryTarget = (values: string[]) =>
  targetFigures(values).every((figure) => figure > 0);

export const targetsToText = (days: number[] | null | undefined) =>
  days && days.length === DAYS.length
    ? days.map((figure) => String(figure))
    : EMPTY_TARGETS;

export function sameTargets(left: number[], right: number[]) {
  return (
    left.length === right.length &&
    left.every((figure, index) => figure === right[index])
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
  const { formatNumber } = useFormats();
  const total = targetFigures(values).reduce((sum, figure) => sum + figure, 0);
  function sameEveryDay() {
    const first = values.find((text) => targetFigure(text) > 0);
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
          {DAYS.map((day, index) => (
            <label key={day} className="tcell">
              <span>{day.slice(0, 3)}</span>
              <input
                id={`${idPrefix}-${index}`}
                className="inp num"
                inputMode="numeric"
                autoComplete="off"
                aria-label={`Target, ${day}`}
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
