import { cn } from "./cn";

// Mutually exclusive filters shown as a pill track (.seg).
export function SegmentedControl<T extends string>({
  label,
  options,
  value,
  onChange,
  className,
}: {
  label: string;
  options: { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
  className?: string;
}) {
  return (
    <div role="group" aria-label={label} className={cn("inline-flex gap-0.5 rounded-full bg-divider p-1", className)}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={value === option.value}
          onClick={() => onChange(option.value)}
          className="min-h-10 rounded-full px-4 text-sm font-semibold text-grey aria-pressed:bg-white aria-pressed:text-navy aria-pressed:shadow-seg"
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
