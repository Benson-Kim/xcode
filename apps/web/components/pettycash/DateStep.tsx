"use client";

import { useRef } from "react";

import { shiftDate } from "@xcode/shared/dates";

import { useFormats } from "../../lib/formats";

// The date of a pop up, first in it: previous, the date, next (.mstep). Previous stops at the earliest day this person
// may change (none when null); next stops at the latest day, today.
export function DateStep({
  date,
  earliest,
  latest,
  onChange,
}: {
  date: string;
  earliest: string | null;
  latest: string;
  onChange: (date: string) => void;
}) {
  const formats = useFormats();
  const previous = useRef<HTMLButtonElement>(null);
  const next = useRef<HTMLButtonElement>(null);
  const blocked = (day: string) => ({
    before: earliest !== null && shiftDate(day, -1) < earliest,
    after: day >= latest,
  });
  const now = blocked(date);

  function move(days: -1 | 1) {
    const target = shiftDate(date, days);
    const reached = blocked(target);
    onChange(target);
    if (days < 0 && reached.before) next.current?.focus();
    if (days > 0 && reached.after) previous.current?.focus();
  }

  return (
    <div className="mstep">
      <div className="step day">
        <button
          ref={previous}
          type="button"
          aria-label="Previous day"
          disabled={now.before}
          onClick={() => move(-1)}
        >
          ‹
        </button>
        <span className="d" aria-live="polite">
          {formats.formatWeekdayDate(date)}
        </span>
        <button
          ref={next}
          type="button"
          aria-label="Next day"
          disabled={now.after}
          onClick={() => move(1)}
        >
          ›
        </button>
      </div>
    </div>
  );
}
