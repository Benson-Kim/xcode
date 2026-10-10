import { cn } from "./cn";

// Mutually exclusive filters shown as a pill track (.pills). On the hero band it turns to glass.
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
    <div
      role="group"
      aria-label={label}
      className={cn(
        "inline-flex flex-wrap gap-1 rounded-xl border border-line bg-surface p-1 [.hero_&]:border-glass-line [.hero_&]:bg-glass",
        className,
      )}
    >
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={value === option.value}
          onClick={() => onChange(option.value)}
          className="flex items-center gap-[7px] rounded-[9px] px-2.5 py-[7px] text-sm font-semibold whitespace-nowrap text-slate hover:bg-paper aria-pressed:bg-ink aria-pressed:text-on-fill [.hero_&]:text-on-deep [.hero_&]:hover:bg-glass-2 [.hero_&]:aria-pressed:bg-white [.hero_&]:aria-pressed:text-deep"
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
