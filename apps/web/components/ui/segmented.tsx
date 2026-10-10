import type { ReactNode } from "react";

import { cn } from "./cn";

// Mutually exclusive filters shown as a pill track (.pills). On the hero band the design turns it to glass.
// A count beside a label is gold when it asks for attention (.q), plain slate when it only counts (.q.n).
export function SegmentedControl<T extends string>({
  label,
  options,
  value,
  onChange,
  className,
}: {
  label: string;
  options: {
    value: T;
    label: string;
    count?: ReactNode;
    countTone?: "attention" | "plain";
  }[];
  value: T;
  onChange: (value: T) => void;
  className?: string;
}) {
  return (
    <div role="group" aria-label={label} className={cn("pills", className)}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={value === option.value}
          onClick={() => onChange(option.value)}
        >
          {option.label}
          {option.count !== undefined && (
            <span className={cn("q", option.countTone === "plain" && "n")}>
              {option.count}
            </span>
          )}
        </button>
      ))}
    </div>
  );
}
