"use client";

import type { KeyboardEvent } from "react";

// Mutually exclusive views as a pill track that behaves as tabs: arrow keys, Home and End move between them.
// `count` shows beside the chosen view's name, which stays the tab's accessible name.
export function ViewPills<T extends string>({
  id,
  panelId = `${id}-panel`,
  label,
  options,
  value,
  onChange,
  count,
}: {
  id: string;
  // The tab panel the views control.
  panelId?: string;
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
    <div role="tablist" aria-label={label} className="pills">
      {options.map((option, index) => (
        <button
          key={option.value}
          id={`${id}-tab-${option.value}`}
          type="button"
          role="tab"
          aria-label={option.label}
          aria-selected={option.value === value}
          aria-controls={panelId}
          tabIndex={option.value === value ? 0 : -1}
          onClick={() => onChange(option.value)}
          onKeyDown={(event) => move(event, index)}
        >
          {option.label}
          {option.value === value && count !== undefined && (
            <span aria-hidden="true" className="q n">
              {count}
            </span>
          )}
        </button>
      ))}
    </div>
  );
}
