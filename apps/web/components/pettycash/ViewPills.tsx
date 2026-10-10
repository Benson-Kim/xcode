"use client";

import type { KeyboardEvent } from "react";

// Mutually exclusive views as a pill track that behaves as tabs: arrow keys, Home and End move between them.
// `count` shows beside the chosen view's name, which stays the tab's accessible name.
export function ViewPills<T extends string>({
  id,
  label,
  options,
  value,
  onChange,
  count,
}: {
  id: string;
  label: string;
  options: { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
  count?: number;
}) {
  function move(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const last = options.length - 1;
    const next =
      event.key === "ArrowRight"
        ? index === last
          ? 0
          : index + 1
        : event.key === "ArrowLeft"
          ? index === 0
            ? last
            : index - 1
          : event.key === "Home"
            ? 0
            : event.key === "End"
              ? last
              : null;
    if (next === null) return;
    event.preventDefault();
    onChange(options[next].value);
    document.getElementById(`${id}-tab-${options[next].value}`)?.focus();
  }
  return (
    <div
      role="tablist"
      aria-label={label}
      className="inline-flex flex-wrap gap-1 rounded-xl border border-line bg-surface p-1"
    >
      {options.map((option, index) => (
        <button
          key={option.value}
          id={`${id}-tab-${option.value}`}
          type="button"
          role="tab"
          aria-label={option.label}
          aria-selected={option.value === value}
          aria-controls={`${id}-panel`}
          tabIndex={option.value === value ? 0 : -1}
          onClick={() => onChange(option.value)}
          onKeyDown={(event) => move(event, index)}
          className="flex items-center gap-[7px] rounded-[9px] px-2.5 py-[7px] text-sm font-semibold whitespace-nowrap text-slate hover:bg-paper aria-selected:bg-ink aria-selected:text-on-fill"
        >
          {option.label}
          {option.value === value && count !== undefined && (
            <span
              aria-hidden="true"
              className="text-[13px] font-semibold text-on-fill/55"
            >
              {count}
            </span>
          )}
        </button>
      ))}
    </div>
  );
}
